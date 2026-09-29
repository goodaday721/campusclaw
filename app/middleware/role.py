"""Role-based authorization middleware: role_required decorator."""
from flask import g, jsonify
from functools import wraps


def role_required(*roles):
    """Decorator that requires the current user to have one of the given roles.

    Returns 403 if the role doesn't match. Must be used after auth_required.
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user_role = getattr(g, "current_user", {}).get("role")
            if user_role not in roles:
                return jsonify({"error": "forbidden"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator
