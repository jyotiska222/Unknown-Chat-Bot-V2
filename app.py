from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, g
from flask_socketio import SocketIO, emit
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import os
import time
from datetime import datetime
import logging
from werkzeug.security import generate_password_hash, check_password_hash
import threading
import traceback
import requests
from socket import gethostname
from functools import wraps

from config import Config
from bot.handlers import (
    handle_start_command,
    handle_chat_command,
    handle_leave_command,
    handle_message,
    handle_callback_query
)
from bot.utils import TelegramAPI, UserManager, ChatManager, TelegramError
from admin.routes import admin
from error_handlers import init_error_handlers, APIError

# Configure logging with more detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)
Config.init_app(app)

# Initialize error handlers
init_error_handlers(app)

# Initialize SocketIO
socketio = SocketIO(
    app,
    async_mode='threading',
    cors_allowed_origins='*',
    transport=['polling'],
    ping_timeout=10,
    ping_interval=5,
    logger=True,
    engineio_logger=True
)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Initialize managers
telegram = TelegramAPI()
user_manager = UserManager()
chat_manager = ChatManager()

# Add datetime filter
@app.template_filter('datetime')
def format_datetime(value):
    if not value:
        return ''
    return datetime.fromtimestamp(value).strftime('%Y-%m-%d %H:%M:%S')

# Message deduplication cache
message_cache = set()

# Admin User class
class AdminUser(UserMixin):
    def __init__(self, username):
        self.username = username
        self.id = username  # Use username as ID

@login_manager.user_loader
def load_user(username):
    if username == Config.ADMIN_USERNAME:
        return AdminUser(username)
    return None

# Register admin blueprint
app.register_blueprint(admin, url_prefix='/admin')

@app.route('/')
def landing_page():
    """Landing page route"""
    stats = {
        'total_users': len(user_manager.get_all_users()),
        'active_chats': len([u for u in user_manager.get_all_users().values() if u.get('status') == 'chatting']) // 2,
        'bot_name': Config.BOT_NAME if hasattr(Config, 'BOT_NAME') else 'Anonymous Chat Bot'
    }
    return render_template('landing.html', stats=stats, now=datetime.now())

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('admin.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == Config.ADMIN_USERNAME and password == Config.ADMIN_PASSWORD:
            user = AdminUser(username)
            login_user(user)
            return redirect(url_for('admin.dashboard'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('admin/login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

def cleanup_inactive_users():
    """Cleanup inactive users and dead chats"""
    while True:
        try:
            current_time = time.time()
            users = user_manager.get_all_users()
            
            for user_id, user_data in users.items():
                # Skip if user is active
                if current_time - user_data.get('last_active', 0) < Config.INACTIVE_TIMEOUT:
                    continue
                
                # Reset waiting status if user is inactive
                if user_data.get('status') == 'waiting':
                    user_data['status'] = 'ready'
                    user_manager.save_user(user_id, user_data)
                    logger.info(f"Reset inactive waiting user {user_id}")
                
                # End dead chats
                if user_data.get('status') == 'chatting':
                    partner_id = user_data.get('partner')
                    if partner_id:
                        partner = user_manager.get_user(partner_id)
                        if partner and current_time - partner.get('last_active', 0) > Config.INACTIVE_TIMEOUT:
                            handle_leave_command(user_id)
                            logger.info(f"Ended dead chat between {user_id} and {partner_id}")
            
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
            traceback.print_exc()
        
        time.sleep(Config.CLEANUP_INTERVAL)

def is_duplicate_message(update):
    """Check if message is a duplicate"""
    if 'message' in update:
        msg = update['message']
        key = f"{msg['message_id']}:{msg['from']['id']}"
        if key in message_cache:
            return True
        message_cache.add(key)
        # Keep cache size reasonable
        if len(message_cache) > 1000:
            message_cache.clear()
    return False

def handle_update(update):
    """Handle incoming update from Telegram."""
    try:
        if 'message' in update:
            message = update['message']
            user_id = str(message['from']['id'])
            username = message['from'].get('username', '')

            # Check if message is a duplicate
            if is_duplicate_message(update):
                return

            # Update user's last active time
            user_manager.update_last_active(user_id)
            
            if 'text' in message:
                text = message['text']
                
                # Check command rate limit
                if text.startswith('/') and not telegram._check_command_rate_limit(user_id):
                    telegram.send_message(user_id, "⚠️ Please wait a few seconds before using commands again.")
                    return
                
                try:
                    if text == '/start':
                        handle_start_command(user_id, username)
                    elif text == '/chat':
                        handle_chat_command(user_id)
                    elif text == '/leave':
                        handle_leave_command(user_id)
                    else:
                        handle_message(user_id, message)
                except TelegramError as e:
                    logger.error(f"Telegram API error for user {user_id}: {e}")
                    telegram.send_message(user_id, "⚠️ Sorry, there was an error processing your request. Please try again later.")
            else:
                # Handle media messages
                handle_message(user_id, message)
                
        elif 'callback_query' in update:
            callback = update['callback_query']
            handle_callback_query(callback)
    except Exception as e:
        logger.error(f"Update handling error: {e}")
        traceback.print_exc()

def polling_thread():
    """Thread function for long polling"""
    logger.info("Starting polling thread...")
    offset = None
    consecutive_errors = 0
    last_connection_time = time.time()
    
    while True:
        try:
            current_time = time.time()
            
            # If we've been running for more than 1 hour, restart the connection
            if current_time - last_connection_time > 3600:  # 1 hour
                logger.info("Periodic connection reset")
                telegram.session = requests.Session()  # Reset session
                last_connection_time = current_time
                consecutive_errors = 0
            
            # Use shorter polling timeout to avoid long waits
            updates = telegram.get_updates(offset, timeout=Config.POLLING_TIMEOUT)
            
            if updates and updates.get('ok') and updates.get('result'):
                consecutive_errors = 0  # Reset error counter on success
                for update in updates['result']:
                    try:
                        handle_update(update)
                    except Exception as e:
                        logger.error(f"Error handling update: {e}")
                        traceback.print_exc()
                    offset = update['update_id'] + 1
            else:
                # Small delay on empty updates
                time.sleep(0.5)
                
        except requests.Timeout as e:
            logger.warning(f"Timeout error in polling: {e}")
            consecutive_errors += 1
            if consecutive_errors >= Config.MAX_RETRIES:
                logger.error("Too many consecutive timeouts, resetting connection...")
                telegram.session = requests.Session()  # Reset session
                time.sleep(Config.RETRY_DELAY * 2)
                consecutive_errors = 0
            else:
                time.sleep(Config.RETRY_DELAY)
                
        except requests.ConnectionError as e:
            logger.error(f"Connection error in polling: {e}")
            consecutive_errors += 1
            if consecutive_errors >= Config.MAX_RETRIES:
                logger.error("Connection problems detected, waiting longer...")
                time.sleep(Config.RETRY_DELAY * 5)
                telegram.session = requests.Session()  # Reset session
                consecutive_errors = 0
            else:
                time.sleep(Config.RETRY_DELAY)
                
        except TelegramError as e:
            logger.error(f"Telegram API error in polling: {e}")
            if "429" in str(e):  # Rate limit error
                retry_after = 30  # Default retry after 30 seconds
                if "retry_after" in str(e):
                    try:
                        retry_after = int(str(e).split("retry_after=")[1].split()[0])
                    except:
                        pass
                logger.info(f"Rate limited, waiting {retry_after} seconds")
                time.sleep(retry_after)
            else:
                consecutive_errors += 1
                if consecutive_errors >= Config.MAX_RETRIES:
                    logger.error("Too many Telegram API errors, waiting longer...")
                    time.sleep(Config.RETRY_DELAY * 5)
                    consecutive_errors = 0
                else:
                    time.sleep(Config.RETRY_DELAY)
                
        except Exception as e:
            logger.error(f"Unexpected error in polling: {e}")
            traceback.print_exc()
            consecutive_errors += 1
            if consecutive_errors >= Config.MAX_RETRIES:
                logger.error("Too many unexpected errors, resetting connection...")
                telegram.session = requests.Session()  # Reset session
                time.sleep(Config.RETRY_DELAY * 5)
                consecutive_errors = 0
            else:
                time.sleep(Config.RETRY_DELAY)

# Socket.IO events
@socketio.on('connect', namespace='/admin')
def handle_admin_connect():
    """Handle admin panel WebSocket connection."""
    if not current_user or not current_user.is_authenticated:
        return False
    
    emit('connected', {'data': 'Connected to admin panel'})
    
    # Send initial data
    users = user_manager.get_all_users()
    total_users = len(users)
    active_users = len([u for u in users.values() if time.time() - u.get('last_active', 0) < 300])
    waiting_users = len([u for u in users.values() if u.get('status') == 'waiting'])
    active_chats = len([u for u in users.values() if u.get('status') == 'chatting'])
    
    # Calculate gender distribution
    gender_stats = {
        'M': len([u for u in users.values() if u.get('gender') == 'M']),
        'F': len([u for u in users.values() if u.get('gender') == 'F']),
        'O': len([u for u in users.values() if u.get('gender') == 'O'])
    }
    
    # Get active chats
    chat_list = []
    chatting_users = {str(uid): user for uid, user in users.items() if user.get('status') == 'chatting'}
    processed_pairs = set()
    
    for user_id, user in chatting_users.items():
        partner_id = str(user.get('partner'))  # Convert to string
        if partner_id and (user_id, partner_id) not in processed_pairs and (partner_id, user_id) not in processed_pairs:
            partner = users.get(partner_id)
            if partner:
                chat_id = f"{min(user_id, partner_id)}_{max(user_id, partner_id)}"
                chat_list.append({
                    'chat_id': chat_id,
                    'username1': user.get('username', 'Unknown'),
                    'username2': partner.get('username', 'Unknown'),
                    'gender1': user.get('gender', 'Unknown'),
                    'gender2': partner.get('gender', 'Unknown'),
                    'chat_start': user.get('chat_start', time.time()),
                    'message_count': chat_manager.get_chat_message_count(chat_id)
                })
                processed_pairs.add((user_id, partner_id))
    
    # Send initial stats
    emit('stats_update', {
        'total_users': total_users,
        'active_users': active_users,
        'waiting_users': waiting_users,
        'active_chats': active_chats // 2,  # Divide by 2 since each chat has 2 users
        'gender_stats': gender_stats,
        'hourly_activity': [0] * 24  # Initialize empty hourly activity
    })
    
    # Send active chats
    emit('active_chats', chat_list)
    return True

@socketio.on('disconnect', namespace='/admin')
def handle_admin_disconnect():
    """Handle admin panel WebSocket disconnection."""
    pass

def emit_stats_update():
    """Emit updated statistics to admin panel."""
    try:
        users = user_manager.get_all_users()
        total_users = len(users)
        active_users = len([u for u in users.values() if time.time() - u.get('last_active', 0) < 300])
        waiting_users = len([u for u in users.values() if u.get('status') == 'waiting'])
        active_chats = len([u for u in users.values() if u.get('status') == 'chatting'])
        
        # Calculate gender distribution
        gender_stats = {
            'M': len([u for u in users.values() if u.get('gender') == 'M']),
            'F': len([u for u in users.values() if u.get('gender') == 'F']),
            'O': len([u for u in users.values() if u.get('gender') == 'O'])
        }
        
        # Calculate user activity (last 24 hours)
        current_time = time.time()
        hourly_activity = [0] * 24
        for user in users.values():
            if user.get('last_active'):
                hours_ago = int((current_time - user.get('last_active')) / 3600)
                if 0 <= hours_ago < 24:
                    hourly_activity[hours_ago] += 1
        
        # Get active chats list
        chat_list = []
        chatting_users = {str(uid): user for uid, user in users.items() if user.get('status') == 'chatting'}
        processed_pairs = set()
        
        for user_id, user in chatting_users.items():
            partner_id = user.get('partner')
            if partner_id and (user_id, partner_id) not in processed_pairs and (partner_id, user_id) not in processed_pairs:
                partner = users.get(partner_id)
                if partner:
                    chat_id = f"{min(str(user_id), str(partner_id))}_{max(str(user_id), str(partner_id))}"
                    chat_list.append({
                        'chat_id': chat_id,
                        'username1': user.get('username', 'Unknown'),
                        'username2': partner.get('username', 'Unknown'),
                        'gender1': user.get('gender', 'Unknown'),
                        'gender2': partner.get('gender', 'Unknown'),
                        'chat_start': user.get('chat_start', time.time()),
                        'message_count': chat_manager.get_chat_message_count(chat_id)
                    })
                    processed_pairs.add((user_id, partner_id))
        
        # Emit stats update
        socketio.emit('stats_update', {
            'total_users': total_users,
            'active_users': active_users,
            'waiting_users': waiting_users,
            'active_chats': active_chats // 2,
            'gender_stats': gender_stats,
            'hourly_activity': hourly_activity
        }, namespace='/admin')
        
        # Emit active chats update
        socketio.emit('active_chats', chat_list, namespace='/admin')
        
    except Exception as e:
        logger.error(f"Error emitting stats update: {e}")
        traceback.print_exc()

def validate_json(*required_fields):
    """Decorator to validate JSON payload"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not request.is_json:
                raise APIError("Content-Type must be application/json", 400)
            
            data = request.get_json()
            if not data:
                raise APIError("No JSON data provided", 400)
            
            missing_fields = [field for field in required_fields if field not in data]
            if missing_fields:
                raise APIError(f"Missing required fields: {', '.join(missing_fields)}", 400)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.before_request
def before_request():
    """Log request details and set up request context"""
    g.start_time = time.time()
    logger.info(f"Request started: {request.method} {request.path}")
    logger.debug(f"Request headers: {dict(request.headers)}")
    if request.is_json:
        logger.debug(f"Request JSON: {request.get_json()}")

@app.after_request
def after_request(response):
    """Log response details"""
    duration = time.time() - g.start_time
    logger.info(f"Request completed: {request.method} {request.path} - Status: {response.status_code} - Duration: {duration:.2f}s")
    return response

@app.route('/health')
def health_check():
    """Health check endpoint"""
    try:
        # Check database/storage access
        user_manager.get_all_users()
        # Check Telegram API access
        telegram.get_me()
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'version': os.getenv('APP_VERSION', '1.0.0')
        })
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route(f'/{Config.BOT_TOKEN}', methods=['POST'])
@validate_json()
def webhook():
    """Handle incoming webhook updates from Telegram with validation"""
    try:
        update = request.get_json()
        handle_update(update)
        return 'ok'
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        logger.error(traceback.format_exc())
        # Don't expose internal errors to Telegram
        return 'ok'

def setup_webhook():
    """Set up the webhook with Telegram."""
    try:
        webhook_url = f"{Config.WEBHOOK_URL}/{Config.BOT_TOKEN}"
        response = requests.post(
            f"{Config.TELEGRAM_API_URL}/setWebhook",
            json={'url': webhook_url}
        )
        if response.status_code == 200 and response.json().get('ok'):
            logger.info(f"Webhook set up successfully at {webhook_url}")
        else:
            logger.error(f"Failed to set up webhook: {response.text}")
    except Exception as e:
        logger.error(f"Error setting up webhook: {e}")

if __name__ == '__main__':
    # Start cleanup thread
    cleanup_thread = threading.Thread(target=cleanup_inactive_users, daemon=True)
    cleanup_thread.start()
    
    # Set up webhook if running on PythonAnywhere
    if 'pythonanywhere' in gethostname():
        setup_webhook()
        application = app
    else:
        # Running locally - use polling
        polling_thread = threading.Thread(target=polling_thread, daemon=True)
        polling_thread.start()
        socketio.run(app, host='0.0.0.0', port=5000, debug=False) 