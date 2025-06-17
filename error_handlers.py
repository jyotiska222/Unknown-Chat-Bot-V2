from flask import jsonify, render_template
from werkzeug.exceptions import HTTPException
import logging
import traceback
from typing import Union, Dict, Any

logger = logging.getLogger(__name__)

class APIError(Exception):
    """Base exception class for API errors"""
    def __init__(self, message: str, status_code: int = 400, payload: Dict[str, Any] = None):
        super().__init__()
        self.message = message
        self.status_code = status_code
        self.payload = payload or {}

    def to_dict(self) -> Dict[str, Any]:
        error_dict = dict(self.payload or {})
        error_dict['message'] = self.message
        error_dict['status'] = 'error'
        error_dict['code'] = self.status_code
        return error_dict

def init_error_handlers(app):
    """Initialize error handlers for the Flask app"""
    
    @app.errorhandler(APIError)
    def handle_api_error(error: APIError):
        """Handle custom API errors"""
        response = jsonify(error.to_dict())
        response.status_code = error.status_code
        return response

    @app.errorhandler(404)
    def not_found_error(error):
        """Handle 404 errors"""
        if request.path.startswith('/api/'):
            return jsonify({
                'status': 'error',
                'message': 'Resource not found',
                'code': 404
            }), 404
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 errors"""
        logger.error(f"Internal Server Error: {error}")
        logger.error(traceback.format_exc())
        if request.path.startswith('/api/'):
            return jsonify({
                'status': 'error',
                'message': 'Internal server error',
                'code': 500
            }), 500
        return render_template('errors/500.html'), 500

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        """Handle unexpected errors"""
        logger.error(f"Unexpected error: {error}")
        logger.error(traceback.format_exc())
        if request.path.startswith('/api/'):
            return jsonify({
                'status': 'error',
                'message': 'An unexpected error occurred',
                'code': 500
            }), 500
        return render_template('errors/500.html'), 500

    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        """Handle HTTP errors"""
        if request.path.startswith('/api/'):
            return jsonify({
                'status': 'error',
                'message': error.description,
                'code': error.code
            }), error.code
        return render_template(f'errors/{error.code}.html'), error.code 