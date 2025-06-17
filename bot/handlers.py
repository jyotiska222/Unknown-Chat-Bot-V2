import logging
from datetime import datetime
import time
from .utils import TelegramAPI, UserManager, ChatManager
from .shared import socketio

logger = logging.getLogger(__name__)

telegram = TelegramAPI()
user_manager = UserManager()
chat_manager = ChatManager()

def handle_start_command(user_id, username):
    """Handle /start command"""
    user = user_manager.get_user(user_id)
    
    if not user:
        # New user registration
        user_data = {
            'username': username,
            'status': 'new',
            'joined_at': time.time(),
            'partner': None,
            'gender': None,
            'interest': None,
            'banned': False
        }
        user_manager.save_user(user_id, user_data)
        
        # Send welcome message with gender selection
        keyboard = {
            'inline_keyboard': [
                [{'text': '👨 Male', 'callback_data': 'gender_M'}],
                [{'text': '👩 Female', 'callback_data': 'gender_F'}],
                [{'text': '⭐ Other', 'callback_data': 'gender_O'}]
            ]
        }
        telegram.send_message(
            user_id,
            "👋 Welcome to Anonymous Chat!\n\n"
            "Please select your gender:",
            reply_markup=keyboard
        )
    else:
        # Returning user
        telegram.send_message(
            user_id,
            "👋 Welcome back!\n\n"
            "Available commands:\n"
            "/chat - Find someone to chat with\n"
            "/leave - End current chat\n"
            "/help - Show help message"
        )

def handle_gender_selection(user_id, gender):
    """Handle gender selection callback"""
    user = user_manager.get_user(user_id)
    logger.info(f"Gender selection - User {user_id} before: {user}")
    if user:  # Remove status check to allow re-selection
        user['gender'] = gender
        user['status'] = 'gender_set'
        user_manager.save_user(user_id, user)
        logger.info(f"Gender selection - User {user_id} after: {user}")
        
        # Ask for chat interest
        keyboard = {
            'inline_keyboard': [
                [{'text': '👨 Male', 'callback_data': 'interest_M'}],
                [{'text': '👩 Female', 'callback_data': 'interest_F'}],
                [{'text': '👥 Both', 'callback_data': 'interest_B'}]
            ]
        }
        telegram.send_message(
            user_id,
            "Great! Now, who would you like to chat with?",
            reply_markup=keyboard
        )

def handle_interest_selection(user_id, interest):
    """Handle interest selection callback"""
    user = user_manager.get_user(user_id)
    logger.info(f"Interest selection - User {user_id} before: {user}")
    if user:  # Remove status check to allow re-selection
        user['interest'] = interest
        user['status'] = 'ready'
        user_manager.save_user(user_id, user)
        logger.info(f"Interest selection - User {user_id} after: {user}")
        
        telegram.send_message(
            user_id,
            "✅ Profile setup complete!\n\n"
            "Use /chat to start finding chat partners!"
        )

def find_chat_partner(user_id):
    """Find a suitable chat partner randomly"""
    user = user_manager.get_user(user_id)
    if not user or user.get('banned'):
        return None
    
    waiting_users = user_manager.get_waiting_users()
    logger.info(f"Finding partner for user {user_id}")
    logger.info(f"Available waiting users: {waiting_users}")
    
    # Simply find the first waiting user that isn't the current user
    for wait_id, wait_user in waiting_users.items():
        if wait_id != str(user_id):
            logger.info(f"Found random partner: {wait_id}")
            return wait_id
    
    return None

def handle_chat_command(user_id):
    """Handle /chat command"""
    user = user_manager.get_user(user_id)
    logger.info(f"Chat command - User {user_id} data: {user}")
    
    if not user:
        telegram.send_message(user_id, "Please use /start first!")
        return
    
    if user.get('banned'):
        telegram.send_message(user_id, "🚫 You are banned from using this service.")
        return
    
    # Check if profile is complete
    if not user.get('gender') or not user.get('interest'):
        logger.info(f"User {user_id} profile incomplete: gender={user.get('gender')}, interest={user.get('interest')}")
        telegram.send_message(user_id, "Please complete your profile setup first! Use /start to set up your profile.")
        return
    
    if user.get('status') == 'waiting':
        # Try to find a partner again for waiting users
        partner_id = find_chat_partner(user_id)
        if partner_id:
            partner = user_manager.get_user(partner_id)
            
            # Update both users
            user['status'] = 'chatting'
            user['partner'] = partner_id
            user['chat_start'] = time.time()
            user_manager.save_user(user_id, user)
            
            partner['status'] = 'chatting'
            partner['partner'] = str(user_id)
            partner['chat_start'] = time.time()
            user_manager.save_user(partner_id, partner)
            
            # Notify both users
            telegram.send_message(user_id, "✅ Chat partner found! You can start chatting now.\nUse /leave to end the chat.")
            telegram.send_message(partner_id, "✅ Chat partner found! You can start chatting now.\nUse /leave to end the chat.")
            
            # Emit chat started event
            chat_id = f"{min(str(user_id), str(partner_id))}_{max(str(user_id), str(partner_id))}"
            socketio.emit('chat_started', {
                'chat_id': chat_id,
                'username1': user.get('username', 'Unknown'),
                'username2': partner.get('username', 'Unknown'),
                'gender1': user.get('gender', 'Unknown'),
                'gender2': partner.get('gender', 'Unknown'),
                'chat_start': time.time(),
                'message_count': 0
            }, namespace='/admin')
        else:
            telegram.send_message(user_id, "⏳ Still looking for a chat partner... Please wait.")
        return
    
    # If already in chat, disconnect first
    if user.get('partner'):
        handle_leave_command(str(user_id))
    
    # Update user status to waiting
    user['status'] = 'waiting'
    user['wait_start'] = time.time()
    user_manager.save_user(user_id, user)
    
    # Try to find a partner
    partner_id = find_chat_partner(user_id)
    
    if partner_id:
        # Match found
        partner = user_manager.get_user(partner_id)
        
        # Update both users
        user['status'] = 'chatting'
        user['partner'] = partner_id
        user['chat_start'] = time.time()
        user_manager.save_user(user_id, user)
        
        partner['status'] = 'chatting'
        partner['partner'] = str(user_id)
        partner['chat_start'] = time.time()
        user_manager.save_user(partner_id, partner)
        
        # Notify both users
        telegram.send_message(user_id, "✅ Chat partner found! You can start chatting now.\nUse /leave to end the chat.")
        telegram.send_message(partner_id, "✅ Chat partner found! You can start chatting now.\nUse /leave to end the chat.")
        
        # Emit chat started event
        chat_id = f"{min(str(user_id), str(partner_id))}_{max(str(user_id), str(partner_id))}"
        socketio.emit('chat_started', {
            'chat_id': chat_id,
            'username1': user.get('username', 'Unknown'),
            'username2': partner.get('username', 'Unknown'),
            'gender1': user.get('gender', 'Unknown'),
            'gender2': partner.get('gender', 'Unknown'),
            'chat_start': time.time(),
            'message_count': 0
        }, namespace='/admin')
    else:
        telegram.send_message(user_id, "⏳ Looking for a chat partner... Please wait.\nI'll notify you when a match is found!")

def handle_leave_command(user_id: str) -> None:
    """Handle /leave command"""
    user = user_manager.get_user(user_id)
    if not user or not user.get('partner'):
        telegram.send_message(user_id, "You're not in a chat!")
        return
    
    partner_id = user.get('partner')
    partner = user_manager.get_user(partner_id)
    
    # Reset both users
    user['status'] = 'ready'
    user['partner'] = None
    user_manager.save_user(user_id, user)
    
    if partner:
        partner['status'] = 'ready'
        partner['partner'] = None
        user_manager.save_user(partner_id, partner)
        telegram.send_message(partner_id, "❌ Your chat partner has left the chat.\nUse /chat to find a new partner!")
    
    telegram.send_message(user_id, "❌ You've left the chat.\nUse /chat to find a new partner!")
    
    # Emit chat ended event only if socketio server is initialized
    try:
        if socketio and socketio.server:
            chat_id = f"{min(str(user_id), str(partner_id))}_{max(str(user_id), str(partner_id))}"
            socketio.emit('chat_ended', {
                'chat_id': chat_id,
                'username1': user.get('username', 'Unknown'),
                'username2': partner.get('username', 'Unknown') if partner else 'Unknown',
                'end_time': time.time()
            }, namespace='/admin')
    except Exception as e:
        logger.warning(f"Failed to emit chat_ended event: {e}")
        # Continue normally as this is not critical for the chat functionality

def handle_message(user_id, message_data):
    """Handle regular chat messages"""
    user = user_manager.get_user(user_id)
    
    if not user or user.get('banned'):
        return
        
    if not user.get('partner'):
        telegram.send_message(user_id, "You're not in a chat. Use /chat to find a partner!")
        return
    
    partner_id = user['partner']
    
    try:
        message_type = 'text'
        message_content = message_data.get('text', '')
        media_info = None

        if 'text' in message_data:
            # Text message
            telegram.send_message(partner_id, message_data['text'])
            
        elif 'photo' in message_data:
            # Photo message
            photo = message_data['photo'][-1]  # Get the highest quality photo
            caption = message_data.get('caption', '')
            file_id = photo['file_id']
            logger.info(f"Sending photo from {user_id} to {partner_id}, file_id: {file_id}")
            telegram.send_photo(partner_id, file_id, caption)
            message_type = 'photo'
            media_info = {
                'file_id': file_id,
                'caption': caption,
                'file_size': photo.get('file_size'),
                'width': photo.get('width'),
                'height': photo.get('height')
            }
            
        elif 'video' in message_data:
            # Video message
            video = message_data['video']
            caption = message_data.get('caption', '')
            file_id = video['file_id']
            logger.info(f"Sending video from {user_id} to {partner_id}, file_id: {file_id}")
            telegram.send_video(partner_id, file_id, caption)
            message_type = 'video'
            media_info = {
                'file_id': file_id,
                'caption': caption,
                'file_size': video.get('file_size'),
                'duration': video.get('duration'),
                'width': video.get('width'),
                'height': video.get('height')
            }
            
        elif 'voice' in message_data:
            # Voice message
            voice = message_data['voice']
            file_id = voice['file_id']
            logger.info(f"Sending voice from {user_id} to {partner_id}, file_id: {file_id}")
            telegram.send_voice(partner_id, file_id)
            message_type = 'voice'
            media_info = {
                'file_id': file_id,
                'duration': voice.get('duration'),
                'file_size': voice.get('file_size')
            }
            
        elif 'sticker' in message_data:
            # Sticker
            sticker = message_data['sticker']
            file_id = sticker['file_id']
            logger.info(f"Sending sticker from {user_id} to {partner_id}, file_id: {file_id}")
            telegram.send_sticker(partner_id, file_id)
            message_type = 'sticker'
            media_info = {
                'file_id': file_id,
                'emoji': sticker.get('emoji'),
                'set_name': sticker.get('set_name')
            }
            
        elif 'document' in message_data:
            # Document
            document = message_data['document']
            caption = message_data.get('caption', '')
            file_id = document['file_id']
            logger.info(f"Sending document from {user_id} to {partner_id}, file_id: {file_id}")
            telegram.send_document(partner_id, file_id, caption)
            message_type = 'document'
            media_info = {
                'file_id': file_id,
                'caption': caption,
                'file_name': document.get('file_name'),
                'mime_type': document.get('mime_type'),
                'file_size': document.get('file_size')
            }
            
        elif 'audio' in message_data:
            # Audio
            audio = message_data['audio']
            caption = message_data.get('caption', '')
            file_id = audio['file_id']
            logger.info(f"Sending audio from {user_id} to {partner_id}, file_id: {file_id}")
            telegram.send_audio(partner_id, file_id, caption)
            message_type = 'audio'
            media_info = {
                'file_id': file_id,
                'caption': caption,
                'duration': audio.get('duration'),
                'performer': audio.get('performer'),
                'title': audio.get('title'),
                'file_size': audio.get('file_size')
            }
            
        elif 'video_note' in message_data:
            # Video note (round video)
            video_note = message_data['video_note']
            file_id = video_note['file_id']
            logger.info(f"Sending video note from {user_id} to {partner_id}, file_id: {file_id}")
            telegram.send_video_note(partner_id, file_id)
            message_type = 'video_note'
            media_info = {
                'file_id': file_id,
                'duration': video_note.get('duration'),
                'length': video_note.get('length'),
                'file_size': video_note.get('file_size')
            }
            
        else:
            # Unsupported message type
            logger.warning(f"Unsupported message type from user {user_id}: {message_data.keys()}")
            telegram.send_message(user_id, "⚠️ This type of message is not supported.")
            return
        
        # Log the message with media information if present
        chat_manager.log_message(
            f"{user_id}_{partner_id}",
            user_id,
            message_content,
            message_type=message_type,
            media_info=media_info
        )
        
    except Exception as e:
        logger.error(f"Error handling message from {user_id} to {partner_id}: {e}")
        logger.error(f"Message data: {message_data}")
        logger.error(f"Stack trace:", exc_info=True)
        telegram.send_message(user_id, "⚠️ Failed to send your message. Please try again.")

def handle_callback_query(callback_data):
    """Handle callback queries from inline keyboards"""
    user_id = callback_data['from']['id']
    data = callback_data['data']
    callback_id = callback_data['id']
    
    if data.startswith('gender_'):
        handle_gender_selection(user_id, data.split('_')[1])
    elif data.startswith('interest_'):
        handle_interest_selection(user_id, data.split('_')[1])
    
    # Answer the callback query to remove the loading state
    telegram.answer_callback_query(callback_id) 