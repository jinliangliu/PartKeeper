from functools import wraps
from flask import request, jsonify
from utils import decode_token

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'code': 401, 'message': '未提供认证令牌', 'data': None}), 401
        
        token = token.replace('Bearer ', '')
        payload = decode_token(token)
        if not payload:
            return jsonify({'code': 401, 'message': '无效的认证令牌', 'data': None}), 401
        
        request.current_user = payload
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if request.current_user.get('role') != 'admin':
            return jsonify({'code': 403, 'message': '需要管理员权限', 'data': None}), 403
        return f(*args, **kwargs)
    return decorated