from flask_socketio import SocketIO
from flask import Flask

# Create Flask app instance
app = Flask(__name__)
app.config['SECRET_KEY'] = '85d1d239f67b5c8a0b1e7c2d3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2'

# Initialize SocketIO instance with eventlet
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*")
