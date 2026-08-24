from flask import Blueprint, request, jsonify
from models import db, User
from utils import hash_password, verify_password, generate_token, decode_token

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'code': 400, 'message': '用户名和密码不能为空', 'data': None}), 400
    
    user = User.query.filter_by(username=data['username']).first()
    if not user or not verify_password(user.password_hash, data['password']):
        return jsonify({'code': 401, 'message': '用户名或密码错误', 'data': None}), 401
    
    token = generate_token(user.id, user.username, user.role)
    return jsonify({
        'code': 200,
        'message': '登录成功',
        'data': {
            'token': token,
            'user': {
                'id': user.id,
                'username': user.username,
                'role': user.role
            }
        }
    })

@auth_bp.route('/me', methods=['GET'])
def get_current_user():
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({'code': 401, 'message': '未提供认证令牌', 'data': None}), 401
    
    token = token.replace('Bearer ', '')
    payload = decode_token(token)
    if not payload:
        return jsonify({'code': 401, 'message': '无效的认证令牌', 'data': None}), 401
    
    user = User.query.get(payload['user_id'])
    if not user:
        return jsonify({'code': 404, 'message': '用户不存在', 'data': None}), 404
    
    return jsonify({
        'code': 200,
        'message': 'success',
        'data': {
            'id': user.id,
            'username': user.username,
            'role': user.role,
            'email': user.email,
            'created_at': user.created_at.isoformat()
        }
    })


@auth_bp.route('/logout', methods=['POST'])
def logout():
    # JWT 无状态，登出由前端丢弃 token 完成
    return jsonify({'code': 200, 'message': '登出成功', 'data': None})
