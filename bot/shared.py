"""Shared resources for the bot application"""
from flask_socketio import SocketIO

# Initialize Flask-SocketIO
socketio = SocketIO(cors_allowed_origins="*") 