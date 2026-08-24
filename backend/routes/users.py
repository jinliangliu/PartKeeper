from flask import Blueprint, request, jsonify

from models import db, User
from utils import hash_password
from utils.decorators import admin_required

users_bp = Blueprint('users', __name__, url_prefix='/api/users')


def _serialize(user):
    return {
        'id': user.id,
        'username': user.username,
        'role': user.role,
        'email': user.email,
        'created_at': user.created_at.isoformat() if user.created_at else None,
    }


@users_bp.route('', methods=['GET'])
@admin_required
def get_users():
    users = User.query.order_by(User.id.asc()).all()
    return jsonify({'code': 200, 'message': 'success', 'data': [_serialize(u) for u in users]})


@users_bp.route('', methods=['POST'])
@admin_required
def create_user():
    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    role = data.get('role', 'user')

    if not username:
        return jsonify({'code': 400, 'message': '用户名不能为空', 'data': None}), 400
    if len(password) < 6:
        return jsonify({'code': 400, 'message': '密码长度不能少于 6 位', 'data': None}), 400
    if role not in ('admin', 'user'):
        return jsonify({'code': 400, 'message': '无效的角色', 'data': None}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({'code': 400, 'message': '用户名已存在', 'data': None}), 400

    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
        email=data.get('email'),
    )
    db.session.add(user)
    db.session.commit()
    return jsonify({'code': 200, 'message': '创建成功', 'data': {'id': user.id}}), 201


@users_bp.route('/<int:user_id>', methods=['PUT'])
@admin_required
def update_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'code': 404, 'message': '用户不存在', 'data': None}), 404

    data = request.get_json() or {}
    if 'email' in data:
        user.email = data.get('email')
    if 'role' in data:
        if data.get('role') not in ('admin', 'user'):
            return jsonify({'code': 400, 'message': '无效的角色', 'data': None}), 400
        if user.id == request.current_user.get('user_id') and data.get('role') != 'admin':
            return jsonify({'code': 400, 'message': '不能取消自己的管理员角色', 'data': None}), 400
        user.role = data.get('role')
    if data.get('password'):
        if len(data.get('password')) < 6:
            return jsonify({'code': 400, 'message': '密码长度不能少于 6 位', 'data': None}), 400
        user.password_hash = hash_password(data.get('password'))

    db.session.commit()
    return jsonify({'code': 200, 'message': '更新成功', 'data': None})


@users_bp.route('/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'code': 404, 'message': '用户不存在', 'data': None}), 404
    if user.id == request.current_user.get('user_id'):
        return jsonify({'code': 400, 'message': '不能删除自己', 'data': None}), 400

    db.session.delete(user)
    db.session.commit()
    return jsonify({'code': 200, 'message': '删除成功', 'data': None})
