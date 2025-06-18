from flask_socketio import SocketIO
from flask import Flask

# Create Flask app instance
app = Flask(__name__)

# Initialize SocketIO instance to be shared across modules
socketio = SocketIO(app, cors_allowed_origins="*")
