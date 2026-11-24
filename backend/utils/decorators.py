from functools import wraps
from flask import request, jsonify
from utils import decode_token


def _authenticate():
    """解析 Authorization，返回用户 payload 或 None。

    支持两种凭证：

    - 登录 JWT（Web 前端）；
    - ``pk_`` 访问令牌（插件、脚本等长期客户端）。

    访问令牌只发给管理员（token_service 内部校验绑定用户 role=admin），
    因此解析成功后角色直接记为 admin，与 Web 管理员权限等价。
    """
    header = request.headers.get('Authorization')
    if not header:
        return None

    token = header[7:] if header.startswith('Bearer ') else header

    payload = decode_token(token)
    if payload:
        return payload

    from services import token_service
    row = token_service.verify_value(token)
    if row is None:
        return None

    from models import User, db
    user = db.session.get(User, row.user_id)
    return {
        'user_id': row.user_id,
        'username': user.username if user else None,
        'role': 'admin',
        'token_id': row.id,
    }


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        payload = _authenticate()
        if payload is None:
            message = '未提供认证令牌' if not request.headers.get('Authorization') else '无效的认证令牌'
            return jsonify({'code': 401, 'message': message, 'data': None}), 401

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
