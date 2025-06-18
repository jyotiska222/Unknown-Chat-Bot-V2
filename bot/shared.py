from flask_socketio import SocketIO
from flask import Flask

# Create Flask app instance
app = Flask(__name__)

# Initialize SocketIO instance with threading mode and other required settings
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='threading',
    engineio_logger=True,
    logger=True,
    ping_timeout=60
)
