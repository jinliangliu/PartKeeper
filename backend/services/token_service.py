"""访问令牌的生成与校验。

Web 端发放、MCP Server 消费，共用这一份实现——否则「生成时怎么拼、校验时怎么比」
两处各写一套，改了格式必然有一边先坏。
"""
import hashlib
import secrets
from datetime import datetime, timedelta

from models import db, ApiToken, User

TOKEN_PREFIX = 'pk_'
BODY_BYTES = 32          # 43 字符 urlsafe base64 ≈ 256 bit 熵，暴力猜解不可行
PREFIX_KEEP = 8          # 展示前缀保留的明文字符数（pk_ + 8）
MAX_NAME_LEN = 60
MAX_ACTIVE_TOKENS = 20   # 单用户活跃令牌上限，防止误点生成塞满列表
VALID_SCOPES = ('mcp:admin',)
LAST_USED_THROTTLE_SECONDS = 300  # 使用记录 5 分钟内不重复写库


def generate_value():
    """生成明文令牌（只在创建时出现这一次）。"""
    return TOKEN_PREFIX + secrets.token_urlsafe(BODY_BYTES)


def hash_value(value):
    """令牌入库存摘要，明文不落库。"""
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def display_prefix(value):
    return value[:len(TOKEN_PREFIX) + PREFIX_KEEP]


def looks_like_token(value):
    return bool(value) and value.startswith(TOKEN_PREFIX)


def create_token(user_id, name, expires_in_days=None, scopes='mcp:admin'):
    """创建令牌，返回 (记录, 明文)。明文调用方必须当场返回给用户，之后无法再取回。"""
    name = (name or '').strip()
    if not name:
        raise ValueError('令牌名称不能为空')
    if len(name) > MAX_NAME_LEN:
        raise ValueError(f'令牌名称不能超过 {MAX_NAME_LEN} 个字符')
    if scopes not in VALID_SCOPES:
        raise ValueError('无效的令牌权限范围')

    active = ApiToken.query.filter(
        ApiToken.user_id == user_id,
        ApiToken.revoked_at.is_(None),
    ).count()
    if active >= MAX_ACTIVE_TOKENS:
        raise ValueError(f'活跃令牌已达上限 {MAX_ACTIVE_TOKENS} 个，请先撤销不用的')

    expires_at = None
    if expires_in_days:
        expires_at = datetime.utcnow() + timedelta(days=int(expires_in_days))

    plain = generate_value()
    row = ApiToken(
        user_id=user_id,
        name=name,
        prefix=display_prefix(plain),
        token_hash=hash_value(plain),
        scopes=scopes,
        expires_at=expires_at,
    )
    db.session.add(row)
    db.session.commit()
    return row, plain


def verify_value(value, touch=True):
    """校验明文令牌，有效则返回记录（含 user），否则返回 None。

    touch=True 时顺带更新 last_used_at，但做了节流：5 分钟内只写一次库，
    避免 MCP 每次工具调用都产生一次 SQLite 写事务。
    """
    if not looks_like_token(value):
        return None

    digest = hash_value(value)
    row = ApiToken.query.filter_by(token_hash=digest).first()
    if row is None:
        return None

    now = datetime.utcnow()
    if not row.is_active(now):
        return None

    # 令牌绑定用户：角色被降级后令牌立即失效，不必等管理员手动撤销
    user = db.session.get(User, row.user_id)
    if user is None or user.role != 'admin':
        return None

    if touch and (row.last_used_at is None
                  or (now - row.last_used_at).total_seconds() >= LAST_USED_THROTTLE_SECONDS):
        row.last_used_at = now
        try:
            db.session.commit()
        except Exception:
            # 只是使用记录的旁支信息，写失败（SQLite 忙）不能连带把鉴权判成失败
            db.session.rollback()

    return row


def revoke_token(row):
    """撤销（软删除）：保留记录用于审计，令牌立即失效。"""
    if row.revoked_at is None:
        row.revoked_at = datetime.utcnow()
        db.session.commit()
    return row


def serialize(row, include_owner=False):
    data = {
        'id': row.id,
        'name': row.name,
        'prefix': row.prefix,
        'scopes': [s for s in (row.scopes or '').split(',') if s],
        'status': row.status,
        'expires_at': row.expires_at.isoformat() if row.expires_at else None,
        'last_used_at': row.last_used_at.isoformat() if row.last_used_at else None,
        'revoked_at': row.revoked_at.isoformat() if row.revoked_at else None,
        'created_at': row.created_at.isoformat() if row.created_at else None,
    }
    if include_owner:
        data['user_id'] = row.user_id
        data['username'] = row.user.username if row.user else None
    return data
