from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from datetime import datetime, timedelta
import time
from bot.utils import UserManager, ChatManager, TelegramAPI
from config import Config

admin = Blueprint('admin', __name__)
user_manager = UserManager()
chat_manager = ChatManager()
telegram = TelegramAPI()

@admin.route('/dashboard')
@login_required
def dashboard():
    """Admin dashboard"""
    users = user_manager.get_all_users()
    
    # Calculate statistics
    total_users = len(users)
    active_chats = len([u for u in users.values() if u.get('status') == 'chatting'])
    online_users = len([u for u in users.values() 
                       if time.time() - u.get('last_active', 0) < 300])  # 5 minutes
    waiting_users = len([u for u in users.values() if u.get('status') == 'waiting'])
    
    stats = {
        'total_users': total_users,
        'active_chats': active_chats // 2,  # Divide by 2 since each chat has 2 users
        'online_users': online_users,
        'waiting_users': waiting_users
    }
    
    return render_template('admin/dashboard.html', stats=stats)

@admin.route('/users')
@login_required
def users():
    """Users management page"""
    users = user_manager.get_all_users()
    return render_template('admin/users.html', users=users)

@admin.route('/monitoring')
@login_required
def monitoring():
    """Real-time monitoring page"""
    return render_template('admin/monitoring.html')

@admin.route('/broadcast', methods=['GET', 'POST'])
@login_required
def broadcast():
    """Broadcast management page"""
    if request.method == 'POST':
        message = request.form.get('message')
        target = request.form.get('target', 'all')
        
        users = user_manager.get_all_users()
        sent_count = 0
        
        for user_id, user in users.items():
            if user.get('banned'):
                continue
                
            if target == 'all' or \
               (target == 'active' and user.get('status') == 'chatting') or \
               (target == 'waiting' and user.get('status') == 'waiting'):
                if telegram.send_message(user_id, f"📢 Announcement:\n\n{message}"):
                    sent_count += 1
        
        flash(f'Broadcast sent to {sent_count} users.', 'success')
        return redirect(url_for('admin.broadcast'))
    
    return render_template('admin/broadcast.html')

@admin.route('/api/ban_user', methods=['POST'])
@login_required
def ban_user():
    """Ban a user"""
    user_id = request.form.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'User ID required'})
    
    user = user_manager.get_user(user_id)
    if not user:
        return jsonify({'success': False, 'error': 'User not found'})
    
    # If user is in chat, disconnect them
    if user.get('partner'):
        partner_id = user['partner']
        partner = user_manager.get_user(partner_id)
        
        user['status'] = 'banned'
        user['partner'] = None
        user_manager.save_user(user_id, user)
        
        if partner:
            partner['status'] = 'ready'
            partner['partner'] = None
            user_manager.save_user(partner_id, partner)
            telegram.send_message(partner_id, "❌ Your chat partner has been disconnected.")
    
    # Ban the user
    user['banned'] = True
    user['ban_time'] = time.time()
    user_manager.save_user(user_id, user)
    
    # Notify the user
    telegram.send_message(user_id, "🚫 You have been banned from using this service.")
    
    return jsonify({'success': True})

@admin.route('/api/unban_user', methods=['POST'])
@login_required
def unban_user():
    """Unban a user"""
    user_id = request.form.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'User ID required'})
    
    user = user_manager.get_user(user_id)
    if not user:
        return jsonify({'success': False, 'error': 'User not found'})
    
    user['banned'] = False
    user['status'] = 'ready'
    user_manager.save_user(user_id, user)
    
    # Notify the user
    telegram.send_message(user_id, "✅ Your ban has been lifted. You can now use the service again.")
    
    return jsonify({'success': True})

@admin.route('/chat-history')
@login_required
def chat_history():
    """Chat history page with media viewing and filtering"""
    return render_template('admin/chat_history.html')

@admin.route('/api/chat-history')
@login_required
def get_chat_history():
    """Get filtered chat history data"""
    user_id = request.args.get('user_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))  # Show 10 chats per page
    
    # Load chat history from file
    chats = chat_manager.get_all_chats()
    
    # Apply filters
    filtered_chats = []
    for chat_id, chat_data in chats.items():
        # Filter by user ID if specified
        if user_id and user_id not in chat_id:
            continue
            
        # Filter by date range if specified
        if start_date:
            start_timestamp = datetime.strptime(start_date, '%Y-%m-%d').timestamp()
            if chat_data['start_time'] < start_timestamp:
                continue
                
        if end_date:
            end_timestamp = datetime.strptime(end_date, '%Y-%m-%d').timestamp()
            if chat_data['end_time'] > end_timestamp:
                continue
        
        # Get user details
        user_ids = chat_id.split('_')
        user1 = user_manager.get_user(user_ids[0])
        user2 = user_manager.get_user(user_ids[1])
        
        # Format chat data
        formatted_chat = {
            'chat_id': chat_id,
            'user1': {
                'id': user_ids[0],
                'username': user1.get('username', 'Unknown') if user1 else 'Unknown'
            },
            'user2': {
                'id': user_ids[1],
                'username': user2.get('username', 'Unknown') if user2 else 'Unknown'
            },
            'start_time': chat_data['start_time'],
            'end_time': chat_data.get('end_time', chat_data['start_time']),
            'messages': []
        }
        
        # Format messages with media info
        for msg in chat_data.get('messages', []):
            formatted_msg = {
                'sender_id': msg['sender_id'],
                'sender_username': (user1.get('username') if msg['sender_id'] == user_ids[0] 
                                  else user2.get('username')) if user1 and user2 else 'Unknown',
                'content': msg['content'],
                'timestamp': msg['timestamp'],
                'type': msg.get('type', 'text')
            }
            
            # Add media info if present
            if 'media_info' in msg:
                formatted_msg['media_info'] = msg['media_info']
                # Get file URL if it's a media message
                if msg['media_info'].get('file_id'):
                    try:
                        file_url = telegram.get_file_url(msg['media_info']['file_id'])
                        formatted_msg['media_info']['file_url'] = file_url
                    except Exception as e:
                        logger.error(f"Error getting file URL: {e}")
            
            formatted_chat['messages'].append(formatted_msg)
        
        filtered_chats.append(formatted_chat)
    
    # Sort by start time, newest first
    filtered_chats.sort(key=lambda x: x['start_time'], reverse=True)
    
    # Calculate pagination
    total_chats = len(filtered_chats)
    total_pages = (total_chats + per_page - 1) // per_page
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    
    return jsonify({
        'chats': filtered_chats[start_idx:end_idx],
        'pagination': {
            'current_page': page,
            'total_pages': total_pages,
            'total_chats': total_chats,
            'per_page': per_page
        }
    })

@admin.route('/api/active_users')
@login_required
def get_active_users():
    """Get currently active users"""
    users = user_manager.get_all_users()
    active_users = []
    
    for user_id, user in users.items():
        if user.get('status') == 'chatting':
            active_users.append({
                'user_id': user_id,
                'username': user.get('username', 'Unknown'),
                'partner_id': user.get('partner'),
                'chat_start': user.get('chat_start'),
                'gender': user.get('gender'),
                'interest': user.get('interest')
            })
    
    return jsonify(active_users)

@admin.route('/api/user_stats')
@login_required
def get_user_stats():
    """Get user statistics"""
    users = user_manager.get_all_users()
    
    # Calculate gender distribution
    gender_stats = {
        'M': len([u for u in users.values() if u.get('gender') == 'M']),
        'F': len([u for u in users.values() if u.get('gender') == 'F']),
        'O': len([u for u in users.values() if u.get('gender') == 'O'])
    }
    
    # Calculate status distribution
    status_stats = {
        'chatting': len([u for u in users.values() if u.get('status') == 'chatting']),
        'waiting': len([u for u in users.values() if u.get('status') == 'waiting']),
        'ready': len([u for u in users.values() if u.get('status') == 'ready']),
        'banned': len([u for u in users.values() if u.get('banned', False)])
    }
    
    return jsonify({
        'gender_stats': gender_stats,
        'status_stats': status_stats,
        'total_users': len(users)
    })

@admin.route('/api/chat_messages/<chat_id>')
@login_required
def get_chat_messages(chat_id):
    """Get recent messages for a specific chat"""
    try:
        # Load chat data
        chats = chat_manager.get_all_chats()
        chat_data = chats.get(chat_id, {})
        
        # Get last 10 messages
        messages = chat_data.get('messages', [])[-10:]
        
        # Format messages with usernames
        formatted_messages = []
        for msg in messages:
            user = user_manager.get_user(msg['sender_id'])
            formatted_messages.append({
                'username': user.get('username', 'Unknown') if user else 'Unknown',
                'content': msg.get('content', ''),
                'type': msg.get('type', 'text'),
                'timestamp': msg.get('timestamp'),
                'media_info': msg.get('media_info')
            })
        
        return jsonify(formatted_messages)
        
    except Exception as e:
        logger.error(f"Error getting chat messages: {e}")
        return jsonify([]), 500 