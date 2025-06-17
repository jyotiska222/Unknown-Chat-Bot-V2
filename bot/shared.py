"""Shared resources for the bot application"""
from flask_socketio import SocketIO

# Initialize Flask-SocketIO without immediate Flask app binding
socketio = SocketIO(
    cors_allowed_origins="*",
    async_mode='threading',
    logger=True,
    engineio_logger=True
) 