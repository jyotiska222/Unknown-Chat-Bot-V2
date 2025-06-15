import json
import time
import logging
from datetime import datetime
import requests
from requests.adapters import HTTPAdapter, Retry
import os
from config import Config
from collections import defaultdict
from functools import wraps

logger = logging.getLogger(__name__)

def rate_limit(func):
    """Rate limiting decorator"""
    last_calls = defaultdict(list)
    
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        current_time = time.time()
        user_id = str(kwargs.get('chat_id', args[0] if args else 'global'))
        
        # Clean old calls
        last_calls[user_id] = [t for t in last_calls[user_id] 
                              if current_time - t < Config.RATE_LIMIT_WINDOW]
        
        # Check rate limit
        if len(last_calls[user_id]) >= Config.RATE_LIMIT_MESSAGES:
            logger.warning(f"Rate limit exceeded for user {user_id}")
            return None
        
        last_calls[user_id].append(current_time)
        return func(self, *args, **kwargs)
    return wrapper

class TelegramError(Exception):
    """Base class for Telegram API errors"""
    pass

class TelegramAPI:
    def __init__(self):
        self.token = Config.BOT_TOKEN
        self.api_url = f"https://api.telegram.org/bot{Config.BOT_TOKEN}"
        self.file_url = f"https://api.telegram.org/file/bot{Config.BOT_TOKEN}"
        self._command_timestamps = defaultdict(list)
        
        # Initialize session with retries and timeouts
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,  # number of retries
            backoff_factor=0.5,  # wait 0.5, 1, 2 seconds between retries
            status_forcelist=[429, 500, 502, 503, 504]  # HTTP status codes to retry on
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
    
    def _check_command_rate_limit(self, user_id):
        """Check command rate limit for a user"""
        current_time = time.time()
        self._command_timestamps[user_id] = [
            t for t in self._command_timestamps[user_id]
            if current_time - t < Config.RATE_LIMIT_COMMAND_WINDOW
        ]
        return len(self._command_timestamps[user_id]) < Config.RATE_LIMIT_COMMANDS
    
    @rate_limit
    def send_message(self, chat_id, text, reply_markup=None, parse_mode='HTML'):
        """Send text message with rate limiting"""
        data = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': parse_mode
        }
        if reply_markup:
            data['reply_markup'] = json.dumps(reply_markup)
        
        return self._make_request('sendMessage', data)
    
    @rate_limit
    def send_photo(self, chat_id, photo, caption=None):
        """Send photo with rate limiting"""
        data = {
            'chat_id': chat_id,
            'photo': photo
        }
        if caption:
            data['caption'] = caption
        return self._make_request('sendPhoto', data)
    
    @rate_limit
    def send_video(self, chat_id, video, caption=None):
        """Send video with rate limiting"""
        data = {
            'chat_id': chat_id,
            'video': video
        }
        if caption:
            data['caption'] = caption
        return self._make_request('sendVideo', data)
    
    @rate_limit
    def send_voice(self, chat_id, voice):
        """Send voice message with rate limiting"""
        data = {
            'chat_id': chat_id,
            'voice': voice
        }
        return self._make_request('sendVoice', data)
    
    @rate_limit
    def send_sticker(self, chat_id, sticker):
        """Send sticker with rate limiting"""
        data = {
            'chat_id': chat_id,
            'sticker': sticker
        }
        return self._make_request('sendSticker', data)
    
    @rate_limit
    def send_document(self, chat_id, document, caption=None):
        """Send document with rate limiting"""
        data = {
            'chat_id': chat_id,
            'document': document
        }
        if caption:
            data['caption'] = caption
        return self._make_request('sendDocument', data)
    
    @rate_limit
    def send_audio(self, chat_id, audio, caption=None):
        """Send audio with rate limiting"""
        data = {
            'chat_id': chat_id,
            'audio': audio
        }
        if caption:
            data['caption'] = caption
        return self._make_request('sendAudio', data)
    
    @rate_limit
    def send_video_note(self, chat_id, video_note):
        """Send video note (round video) with rate limiting"""
        data = {
            'chat_id': chat_id,
            'video_note': video_note
        }
        return self._make_request('sendVideoNote', data)
    
    @rate_limit
    def forward_message(self, chat_id, from_chat_id, message_id):
        """Forward message with rate limiting"""
        data = {
            'chat_id': chat_id,
            'from_chat_id': from_chat_id,
            'message_id': message_id
        }
        return self._make_request('forwardMessage', data)
    
    def get_updates(self, offset=None, timeout=30):
        """Get updates from Telegram"""
        data = {
            'timeout': timeout,
            'allowed_updates': ['message', 'callback_query']  # Only get updates we handle
        }
        if offset is not None:
            data['offset'] = offset
        return self._make_request('getUpdates', data, timeout=timeout+10)  # Add buffer to timeout
    
    def answer_callback_query(self, callback_query_id, text=None):
        """Answer callback query"""
        data = {
            'callback_query_id': callback_query_id
        }
        if text:
            data['text'] = text
        return self._make_request('answerCallbackQuery', data)
    
    def set_webhook(self, url):
        """Set webhook URL"""
        data = {'url': url}
        return self._make_request('setWebhook', data)
    
    def get_file(self, file_id):
        """Get file info and download URL from file_id"""
        data = {
            'file_id': file_id
        }
        response = self._make_request('getFile', data)
        if response and response.get('ok') and response.get('result'):
            file_info = response['result']
            if file_info.get('file_path'):
                # Construct the direct download URL
                download_url = f"{self.file_url}/{file_info['file_path']}"
                return {
                    'file_info': file_info,
                    'download_url': download_url
                }
        return None

    def get_file_url(self, file_id):
        """Get direct download URL for a file"""
        file_data = self.get_file(file_id)
        if file_data:
            return file_data['download_url']
        return None
    
    def _make_request(self, method, data, timeout=20):
        """Make API request with retries and error handling"""
        for attempt in range(Config.MAX_RETRIES):
            try:
                url = f"{self.api_url}/{method}"
                # Use connect timeout of 10 seconds, read timeout as specified
                response = self.session.post(url, json=data, timeout=(10, timeout))
                response_data = response.json()
                
                if not response_data.get('ok'):
                    error_msg = response_data.get('description', 'Unknown error')
                    logger.error(f"Telegram API error: {error_msg}")
                    if 'retry_after' in response_data:
                        retry_after = int(response_data['retry_after'])
                        logger.info(f"Rate limited, waiting {retry_after} seconds")
                        time.sleep(retry_after)
                        continue
                    raise TelegramError(error_msg)
                
                return response_data
                
            except requests.Timeout as e:
                logger.warning(f"Timeout on attempt {attempt + 1} for {method}: {e}")
                if attempt == Config.MAX_RETRIES - 1:
                    raise TelegramError(f"Request timed out after {Config.MAX_RETRIES} attempts")
                time.sleep(Config.RETRY_DELAY * (attempt + 1))
                
            except requests.RequestException as e:
                logger.error(f"Request error on attempt {attempt + 1} for {method}: {e}")
                if attempt == Config.MAX_RETRIES - 1:
                    raise TelegramError(f"Failed after {Config.MAX_RETRIES} retries: {e}")
                time.sleep(Config.RETRY_DELAY * (attempt + 1))
            
            except Exception as e:
                logger.error(f"Unexpected error on attempt {attempt + 1} for {method}: {e}")
                raise TelegramError(f"Unexpected error: {e}")
        
        return None

class DataManager:
    @staticmethod
    def load_data(filepath):
        """Load JSON data from file"""
        try:
            if not os.path.exists(filepath):
                return {}
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading {filepath}: {e}")
            return {}
    
    @staticmethod
    def save_data(filepath, data):
        """Save JSON data to file"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Error saving {filepath}: {e}")
            return False

class UserManager:
    def __init__(self):
        self.users_file = Config.USERS_FILE
    
    def get_user(self, user_id):
        """Get user data"""
        users = DataManager.load_data(self.users_file)
        return users.get(str(user_id))
    
    def get_all_users(self):
        """Get all users"""
        return DataManager.load_data(self.users_file)
    
    def save_user(self, user_id, user_data):
        """Save user data"""
        users = DataManager.load_data(self.users_file)
        users[str(user_id)] = user_data
        return DataManager.save_data(self.users_file, users)
    
    def update_user(self, user_id, updates):
        """Update user data"""
        user = self.get_user(user_id)
        if user:
            user.update(updates)
            return self.save_user(user_id, user)
        return False
    
    def update_last_active(self, user_id):
        """Update user's last active time"""
        user = self.get_user(user_id)
        if user:
            user['last_active'] = time.time()
            return self.save_user(user_id, user)
        return False
    
    def get_waiting_users(self):
        """Get users waiting for chat"""
        users = DataManager.load_data(self.users_file)
        return {uid: data for uid, data in users.items() 
                if data.get('status') == 'waiting'}
    
    def get_active_users(self):
        """Get users in active chats"""
        users = DataManager.load_data(self.users_file)
        return {uid: data for uid, data in users.items() 
                if data.get('status') == 'chatting'}

class ChatManager:
    def __init__(self):
        self.chats_file = Config.CHATS_FILE
    
    def get_all_chats(self):
        """Get all chats"""
        chats_by_date = DataManager.load_data(self.chats_file)
        # Convert date-based structure to chat_id based structure
        all_chats = {}
        for date, chats in chats_by_date.items():
            for chat_id, messages in chats.items():
                if chat_id not in all_chats:
                    all_chats[chat_id] = {
                        'start_time': messages[0]['timestamp'] if messages else time.time(),
                        'end_time': messages[-1]['timestamp'] if messages else time.time(),
                        'messages': [{
                            'sender_id': msg['user_id'],
                            'content': msg['message'],
                            'timestamp': msg['timestamp'],
                            'type': msg.get('type', 'text'),
                            'media_info': msg.get('media_info')
                        } for msg in messages]
                    }
                else:
                    # Merge messages from different dates
                    all_chats[chat_id]['messages'].extend([{
                        'sender_id': msg['user_id'],
                        'content': msg['message'],
                        'timestamp': msg['timestamp'],
                        'type': msg.get('type', 'text'),
                        'media_info': msg.get('media_info')
                    } for msg in messages])
                    # Update start/end times
                    if messages:
                        all_chats[chat_id]['start_time'] = min(all_chats[chat_id]['start_time'], messages[0]['timestamp'])
                        all_chats[chat_id]['end_time'] = max(all_chats[chat_id]['end_time'], messages[-1]['timestamp'])
        return all_chats
    
    def get_chat_message_count(self, chat_id):
        """Get message count for a specific chat"""
        chats = self.get_all_chats()
        chat_data = chats.get(chat_id, {})
        return len(chat_data.get('messages', []))
    
    def log_message(self, chat_id, sender_id, content, message_type='text', media_info=None):
        """Log a chat message"""
        chats = DataManager.load_data(self.chats_file)
        current_date = datetime.now().strftime('%Y-%m-%d')
        
        if current_date not in chats:
            chats[current_date] = {}
            
        if chat_id not in chats[current_date]:
            chats[current_date][chat_id] = []
        
        message = {
            'user_id': sender_id,
            'message': content,
            'timestamp': time.time(),
            'type': message_type
        }
        
        if media_info:
            message['media_info'] = media_info
        
        chats[current_date][chat_id].append(message)
        DataManager.save_data(self.chats_file, chats)
    
    def get_chat_history(self, date):
        """Get chat history for a specific date"""
        chats = DataManager.load_data(self.chats_file)
        return chats.get(date, {}) 