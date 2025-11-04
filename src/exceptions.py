"""
Custom exceptions for the trading bot.
"""

class TradingBotException(Exception):
    """Base exception class for the trading bot."""
    pass

class APIError(TradingBotException):
    """Base class for API-related errors."""
    def __init__(self, message="An unspecified API error occurred.", status_code=None):
        self.status_code = status_code
        super().__init__(f"API Error (Status: {status_code}): {message}" if status_code else message)

class RateLimitError(APIError):
    """Raised for HTTP 429 rate limit errors."""
    def __init__(self, message="Rate limit exceeded."):
        super().__init__(message, status_code=429)

class AuthenticationError(APIError):
    """Raised for authentication failures (401, 403)."""
    def __init__(self, message="API authentication failed."):
        super().__init__(message, status_code=401)

class InvalidRequestError(APIError):
    """Raised for invalid requests (400, 404)."""
    def __init__(self, message="Invalid API request."):
        super().__init__(message, status_code=400)

class APINetworkError(APIError):
    """Raised for network-related issues when communicating with the API."""
    def __init__(self, message="A network error occurred while communicating with the API."):
        super().__init__(message)

class PortfolioError(APIError):
    """Raised for errors related to portfolio management."""
    pass

class OrderError(APIError):
    """Raised for errors related to order placement, cancellation, or status checks."""
    pass

class InsufficientFundsError(OrderError):
    """Raised when an order fails due to insufficient funds."""
    pass
