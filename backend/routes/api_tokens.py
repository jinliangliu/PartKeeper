"""访问令牌（Bearer Token）发放与管理。

Web 端在这里签发令牌，客户端拿它去连 MCP Server（或任何 bearer 鉴权的 API）。
签发需要管理员权限——令牌等同一把长期钥匙，不应该普通账号随手造。
"""
import os

from flask import Blueprint, jsonify, request

from models import ApiToken, db
from services import token_service
from utils.decorators import admin_required

tokens_bp = Blueprint('tokens', __name__, url_prefix='/api/tokens')


def _mcp_public_url():
    """MCP 端点对外地址：优先读 MCP_PUBLIC_URL，否则用当前访问的主机名 + MCP 端口推断。"""
    explicit = (os.getenv('MCP_PUBLIC_URL') or '').strip()
    if explicit:
        return explicit
    port = os.getenv('MCP_PORT', '8000')
    path = os.getenv('MCP_PATH', '/mcp')
    host = (request.host or '').split(':')[0] or 'localhost'
    return f'http://{host}:{port}{path}'


@tokens_bp.route('/meta', methods=['GET'])
@admin_required
def get_meta():
    """连接器配置所需信息（前端直接拼出「复制到 WorkBuddy」的样子）。"""
    return jsonify({
        'code': 200,
        'message': 'success',
        'data': {
            'mcp_endpoint': _mcp_public_url(),
            'token_prefix': token_service.TOKEN_PREFIX,
            'max_active': token_service.MAX_ACTIVE_TOKENS,
            # .env 里若还配着静态 MCP_API_KEY，提示用户它同样有效（便于逐步过渡）
            'static_key_configured': bool((os.getenv('MCP_API_KEY') or '').strip()),
        },
    })


@tokens_bp.route('', methods=['GET'])
@admin_required
def list_tokens():
    """列出全部令牌（含已撤销/已过期），最新在前。"""
    rows = ApiToken.query.order_by(ApiToken.created_at.desc(), ApiToken.id.desc()).all()
    items = [token_service.serialize(r, include_owner=True) for r in rows]
    stats = {
        'total': len(items),
        'active': sum(1 for i in items if i['status'] == 'active'),
        'revoked': sum(1 for i in items if i['status'] == 'revoked'),
        'expired': sum(1 for i in items if i['status'] == 'expired'),
    }
    return jsonify({'code': 200, 'message': 'success',
                    'data': {'items': items, 'stats': stats}})


@tokens_bp.route('', methods=['POST'])
@admin_required
def create_token():
    """生成令牌。**明文只在这一次响应里返回**，前端必须提示用户当场复制。"""
    data = request.get_json(silent=True) or {}
    name = data.get('name')
    expires_in_days = data.get('expires_in_days')

    if expires_in_days in ('', None, 0, '0'):
        expires_in_days = None
    else:
        try:
            expires_in_days = int(expires_in_days)
        except (TypeError, ValueError):
            return jsonify({'code': 400, 'message': '有效期必须是天数', 'data': None}), 400
        if expires_in_days < 1 or expires_in_days > 3650:
            return jsonify({'code': 400, 'message': '有效期需在 1–3650 天之间',
                            'data': None}), 400

    try:
        row, plain = token_service.create_token(
            user_id=request.current_user['user_id'],
            name=name,
            expires_in_days=expires_in_days,
        )
    except ValueError as exc:
        return jsonify({'code': 400, 'message': str(exc), 'data': None}), 400

    return jsonify({
        'code': 200,
        'message': '令牌已生成，请立即复制保存',
        'data': {
            'token': plain,           # 仅此一次
            'item': token_service.serialize(row, include_owner=True),
            'mcp_endpoint': _mcp_public_url(),
        },
    })


@tokens_bp.route('/<int:token_id>', methods=['DELETE'])
@admin_required
def revoke_token(token_id):
    """撤销令牌（软删除，保留审计痕迹）。"""
    row = db.session.get(ApiToken, token_id)
    if row is None:
        return jsonify({'code': 404, 'message': '令牌不存在', 'data': None}), 404
    if row.revoked_at is not None:
        return jsonify({'code': 400, 'message': '该令牌已撤销', 'data': None}), 400

    token_service.revoke_token(row)
    return jsonify({'code': 200, 'message': '令牌已撤销，客户端将立即失效',
                    'data': token_service.serialize(row, include_owner=True)})
