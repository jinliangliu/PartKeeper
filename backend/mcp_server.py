"""PartKeeper MCP Server —— 对外通信层（Streamable HTTP + Bearer 认证）。

以独立进程运行，与 Flask Web Server 共享同一个 SQLite 数据库与业务逻辑层。
供 WorkBuddy 自定义连接器（Connector）通过 MCP 协议访问 PartKeeper 的物料数据。

启动：
    python mcp_server.py

认证：
    客户端请求需携带 ``Authorization: Bearer <token>``。
    token 支持三种：
      1. Web 端「访问令牌」页面发放的 ``pk_`` 令牌（推荐：可命名、可设有效期、
         可随时撤销，撤销后下一次请求即失效，无需重启服务）；
      2. 在 .env 配置的 MCP_API_KEY（静态密钥，全局共用，改一次要重启）；
      3. 用 SECRET_KEY 签发的、role=admin 的 JWT（与 Web 端同一套密钥，短期有效）。

环境变量（见 .env.example）：
    MCP_HOST / MCP_PORT    监听地址，默认 0.0.0.0:8000
    MCP_PATH               Streamable HTTP 路径，默认 /mcp
    MCP_API_KEY            连接器静态密钥；留空则仅接受 admin JWT
"""
import os
import sys
from datetime import datetime
from typing import Optional

# 保证从任意工作目录运行都能导入 backend 内的模块
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, '.env'))

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP

from config import Config

# ---------------------------------------------------------------------------
# 认证：Bearer Token 校验（静态 API Key 或 admin JWT）
# ---------------------------------------------------------------------------

_MCP_API_KEY = os.getenv('MCP_API_KEY', '').strip()


def _lookup_issued_token(token):
    """查库校验 Web 端发放的令牌（pk_ 前缀）。

    MCP 进程独立于 Flask 运行，但共用同一个 SQLite 库——Web 上点「撤销」后
    下一次请求就会失败，不需要重启 MCP 服务。

    **必须在这里把字段取成普通 dict**：app_context 退出时 SQLAlchemy 会 remove
    session，ORM 实例随即 detached/expired，之后再读 row.id 会抛
    DetachedInstanceError（线上踩过，表现为鉴权通过后 500）。
    """
    from app import app as flask_app          # 延迟导入：避免循环依赖
    from services import token_service

    with flask_app.app_context():
        row = token_service.verify_value(token)
        if row is None:
            return None
        return {
            'id': row.id,
            'user_id': row.user_id,
            'scopes': row.scopes,
        }


class PartKeeperTokenVerifier(TokenVerifier):
    """校验连接器使用的 Bearer Token。"""

    async def verify_token(self, token: str) -> Optional[AccessToken]:
        # 1) 静态 API Key（常量时间比较，避免时序侧信道）
        if _MCP_API_KEY:
            import hmac
            if hmac.compare_digest(token, _MCP_API_KEY):
                return AccessToken(token=token, client_id='workbuddy-connector', scopes=['mcp:admin'])

        # 2) Web 端发放的访问令牌（库里只有 SHA-256 摘要，校验时同样比对摘要）
        try:
            row = _lookup_issued_token(token)
        except Exception as exc:          # 库被锁/未初始化不应表现为 500
            print(f'[PartKeeper MCP] issued-token lookup failed: {exc}', file=sys.stderr)
            row = None
        if row is not None:
            return AccessToken(
                token=token,
                client_id=f"pat-{row['id']}",
                scopes=[s for s in (row['scopes'] or 'mcp:admin').split(',') if s],
            )

        # 3) 复用 Web 端 JWT：仅放行 admin
        try:
            import jwt
            payload = jwt.decode(token, Config.SECRET_KEY, algorithms=['HS256'])
        except Exception:
            return None
        if payload.get('role') != 'admin':
            return None
        return AccessToken(
            token=token,
            client_id=str(payload.get('user_id', 'jwt-admin')),
            scopes=['mcp:admin'],
        )


# ---------------------------------------------------------------------------
# FastMCP 实例
# ---------------------------------------------------------------------------

MCP_HOST = os.getenv('MCP_HOST', '0.0.0.0')
MCP_PORT = int(os.getenv('MCP_PORT', '8000'))
MCP_PATH = os.getenv('MCP_PATH', '/mcp')

mcp = FastMCP(
    'PartKeeper',
    instructions=(
        'PartKeeper 物品与库存管理系统的 MCP 接口。'
        '可查询物料、库存、分类、供应商、库位、库存流水与统计；'
        '可新建物品档案、执行入库/出库操作。'
        '家庭场景：可查询消耗品补货建议、保修与维护到期提醒、采购支出看板；'
        '可批量录入支付宝/微信/银行等各渠道生活缴费截图中的水/电/燃气账单（自动去重），并统计缴费支出；'
        '可批量录入教育/培训/旅行/娱乐/购物/医疗/餐饮/交通/居住/数码等各类开支（自动去重，'
        '支持登记凭证图片：自动剥离 EXIF 与 GPS、按内容哈希去重，attach_expense_receipt 可给已有开支补挂凭证），'
        '并按类型汇总；可用 get_household_spend_overview 查看家庭总支出看板。'
        '注意：水费电费燃气费等请用 record_utility_bills，不要重复记入 record_expenses。'
        '所有数据读写均作用于同一 SQLite 数据库。'
    ),
    host=MCP_HOST,
    port=MCP_PORT,
    streamable_http_path=MCP_PATH,
    stateless_http=True,
    auth=AuthSettings(
        # 静态 Bearer Token 校验无需真实 OAuth 发现端点，URL 仅用于构造响应头
        issuer_url=f'http://{MCP_HOST}:{MCP_PORT}{MCP_PATH}',
        resource_server_url=f'http://{MCP_HOST}:{MCP_PORT}{MCP_PATH}',
    ),
    token_verifier=PartKeeperTokenVerifier(),
)


# ---------------------------------------------------------------------------
# 工具函数：进入 Flask app context 后复用现有 models / services
# ---------------------------------------------------------------------------

def _app():
    """延迟导入 Flask app（工厂内会建表/补种，重复调用安全）。"""
    from app import app as flask_app
    return flask_app


# --- 通用解析：时间与渠道（供账单与开支共用，避免两处各写一套别名表） ---

def _parse_datetime(value):
    """把 'YYYY-MM-DD'、'YYYY-MM-DD HH:MM'、'YYYY/MM/DD' 等解析为 datetime，失败返回 None。"""
    if not value:
        return None
    text = str(value).strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d', '%Y/%m/%d'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


# 渠道别名与归一化统一由 utils.ledger 维护，Web 与 MCP 共用一套，避免标签漂移
from utils.ledger import CHANNEL_ALIASES as _CHANNEL_ALIASES  # noqa: E402
from utils.ledger import UTILITY_CHANNELS as _UTILITY_CHANNELS  # noqa: E402
from utils.ledger import UTILITY_LABELS as _UTILITY_LABELS  # noqa: E402
from utils.ledger import normalize_channel as _normalize_channel  # noqa: E402


def _resolve_receipt_path(raw_path):
    """解析凭证文件路径，返回 (绝对路径, 相对 instance/ 的存储路径)；不存在则返回 (None, None)。

    相对路径优先按 ``backend/instance/`` 解析，其次按 ``backend/``——与用户实际放文件的位置对齐。
    仅用于「先确认文件存在」，真正的落盘与哈希由 ``services.receipt_service`` 处理。
    """
    raw = str(raw_path or '').strip().strip('"').strip("'")
    if not raw:
        return None, None
    base = os.path.dirname(os.path.abspath(__file__))
    instance_dir = os.path.join(base, 'instance')
    if os.path.isabs(raw):
        abs_path = raw
    else:
        candidate = os.path.join(instance_dir, raw)
        abs_path = candidate if os.path.exists(candidate) else os.path.join(base, raw)
    if not os.path.isfile(abs_path):
        return None, None
    abs_path = os.path.abspath(abs_path)
    try:
        store_path = os.path.relpath(abs_path, instance_dir).replace('\\', '/')
        if store_path.startswith('../'):
            store_path = abs_path.replace('\\', '/')
    except ValueError:
        store_path = abs_path.replace('\\', '/')
    return abs_path, store_path


def _store_receipt(expense_id, raw_path):
    """把一张凭证图片规范化落盘（剥离 EXIF、按哈希命名）并登记到指定开支。

    返回 ``(attachment, warning)``：成功时 warning 为 None；失败或重复时 attachment 为 None。
    与 Web 上传接口共用 ``services.receipt_service``，两条通道的安全策略完全一致。
    """
    from models import db, ExpenseAttachment
    from services import receipt_service

    abs_path, _ = _resolve_receipt_path(raw_path)
    if not abs_path:
        return None, f'凭证文件不存在或不可读，已跳过：{raw_path}'
    try:
        meta = receipt_service.save_receipt(abs_path, Config.UPLOAD_DIR)
    except receipt_service.ReceiptError as exc:
        return None, f'凭证被拒绝（{raw_path}）：{exc}'

    existing = ExpenseAttachment.query.filter_by(
        expense_id=expense_id, sha256=meta['sha256']
    ).first()
    if existing:
        return None, f'同一凭证重复提交，已跳过：{raw_path}'

    att = ExpenseAttachment(
        expense_id=expense_id,
        file_path=meta['rel_path'],
        sha256=meta['sha256'],
        size_bytes=meta['size_bytes'],
        mime=meta['mime'],
    )
    db.session.add(att)
    return att, None


def _component_dict(c):
    d = {
        'id': c.id,
        'kind': c.kind,
        'name': c.name,
        'value': c.value,
        'package': c.package,
        'tolerance': c.tolerance,
        'brand': c.brand,
        'datasheet_url': c.datasheet_url,
        'min_stock': c.min_stock,
        'current_stock': c.current_stock,
        'unit': c.unit,
        'category': c.category.name if c.category else None,
        'location': c.location.name if c.location else None,
        'supplier': c.supplier.name if c.supplier else None,
        'low_stock': (c.current_stock or 0) <= (c.min_stock or 0),
        'is_consumable': bool(c.is_consumable),
        'consumption_rate': c.consumption_rate,
        'warranty_expiry': c.warranty_expiry.isoformat() if c.warranty_expiry else None,
        'maintenance_cycle_days': c.maintenance_cycle_days,
        'last_maintenance_date': c.last_maintenance_date.isoformat() if c.last_maintenance_date else None,
    }
    if c.last_maintenance_date and c.maintenance_cycle_days:
        from datetime import timedelta
        d['next_maintenance_date'] = (
            c.last_maintenance_date + timedelta(days=c.maintenance_cycle_days)
        ).isoformat()
    else:
        d['next_maintenance_date'] = None
    return d


@mcp.tool()
def list_components(keyword: str = '', category: str = '', only_low_stock: bool = False,
                    limit: int = 50) -> dict:
    """查询物料列表。可按名称/参数值/封装/品牌关键词模糊搜索，按分类名过滤，或只看低库存。"""
    from models import Item, ItemSpec, Category
    with _app().app_context():
        query = Item.query
        if keyword:
            from sqlalchemy import or_
            kw = f'%{keyword}%'
            # value/package 在 item_specs 扩展表，必须显式 join 才能下推到 SQL
            query = query.outerjoin(ItemSpec, ItemSpec.item_id == Item.id).filter(or_(
                Item.name.like(kw), Item.brand.like(kw),
                ItemSpec.spec_value.like(kw), ItemSpec.spec_package.like(kw),
            ))
        if category:
            cat = Category.query.filter(Category.name.like(f'%{category}%')).first()
            if cat:
                query = query.filter(Item.category_id == cat.id)
            else:
                return {'total': 0, 'items': [], 'note': f'未找到分类：{category}'}
        items = query.order_by(Item.id.desc()).limit(max(1, min(limit, 200))).all()
        data = [_component_dict(c) for c in items]
        if only_low_stock:
            data = [d for d in data if d['low_stock']]
        return {'total': len(data), 'items': data}


@mcp.tool()
def get_component(item_id: int) -> dict:
    """按 ID 查询单个物料的完整详情。"""
    from models import Item
    with _app().app_context():
        c = Item.query.get(item_id)
        if not c:
            return {'error': f'物料 ID {item_id} 不存在'}
        return _component_dict(c)


@mcp.tool()
def create_component(name: str, value: str = '', package: str = '', tolerance: str = '',
                     brand: str = '', datasheet_url: str = '', min_stock: int = 0,
                     current_stock: int = 0, unit: str = '个', category: str = '',
                     location: str = '', supplier: str = '', is_consumable: bool = False,
                     consumption_rate: float | None = None, warranty_expiry: str = '',
                     maintenance_cycle_days: int | None = None,
                     last_maintenance_date: str = '', kind: str = 'electronic') -> dict:
    """新建物品档案（电子元器件、家电、家具、车辆等通用）。name 必填；
    category/location/supplier 传名称即可自动关联（也可留空）。

    kind 为物品类型：electronic（电子元器件，默认）/appliance（家电）/furniture（家具）/
    vehicle（车辆）/other（其他）。value/package/tolerance/datasheet_url 仅电子元器件有意义，
    其他类型留空即可。

    家庭属性可选：is_consumable 标记消耗品；consumption_rate 消耗速率（单位/天，留空自动推算）；
    warranty_expiry / last_maintenance_date 传 YYYY-MM-DD，maintenance_cycle_days 为维护周期天数。
    关联名称找不到时不会阻断建档，会在 warnings 中说明。返回新物品 ID 与完整信息。"""
    from models import db, Item, Category, Location, Supplier
    name = (name or '').strip()
    if not name:
        return {'error': '物品名称不能为空'}

    kind_key = str(kind or 'electronic').strip().lower()
    if kind_key not in Item.VALID_KINDS:
        return {'error': f'物品类型无效：{kind}，可选 {"/".join(Item.VALID_KINDS)}'}

    def _parse_date(text, label, warnings):
        if not text:
            return None
        try:
            return datetime.strptime(text.strip(), '%Y-%m-%d').date()
        except ValueError:
            warnings.append(f'{label}「{text}」格式无效（应为 YYYY-MM-DD），已留空')
            return None

    with _app().app_context():
        warnings = []

        def resolve(model, text, label):
            """按名称模糊匹配关联记录，找不到返回 None 并记警告。"""
            if not text:
                return None
            row = model.query.filter(model.name.like(f'%{text.strip()}%')).first()
            if row is None:
                warnings.append(f'{label}「{text}」未找到，已留空')
            return row

        cat = resolve(Category, category, '分类')
        loc = resolve(Location, location, '库位')
        sup = resolve(Supplier, supplier, '供应商')

        component = Item(
            kind=kind_key,
            name=name,
            value=value or None,
            package=package or None,
            tolerance=tolerance or None,
            brand=brand or None,
            datasheet_url=datasheet_url or None,
            min_stock=max(0, int(min_stock)),
            current_stock=max(0, int(current_stock)),
            unit=unit or '个',
            category_id=cat.id if cat else None,
            location_id=loc.id if loc else None,
            supplier_id=sup.id if sup else None,
            is_consumable=bool(is_consumable),
            consumption_rate=float(consumption_rate) if consumption_rate and consumption_rate > 0 else None,
            warranty_expiry=_parse_date(warranty_expiry, '保修到期日', warnings),
            maintenance_cycle_days=int(maintenance_cycle_days) if maintenance_cycle_days and maintenance_cycle_days > 0 else None,
            last_maintenance_date=_parse_date(last_maintenance_date, '上次维护日期', warnings),
        )
        try:
            db.session.add(component)
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            return {'error': f'建档失败：{exc}'}

        result = _component_dict(component)
        result['warnings'] = warnings
        return result


@mcp.tool()
def list_low_stock() -> dict:
    """列出全部低库存物料（当前库存 <= 最低库存阈值），用于采购预警。"""
    from models import Item
    with _app().app_context():
        items = Item.query.filter(
            Item.current_stock <= Item.min_stock
        ).order_by(Item.current_stock.asc()).all()
        return {
            'total': len(items),
            'items': [
                {
                    'id': c.id, 'name': c.name, 'value': c.value,
                    'current_stock': c.current_stock, 'min_stock': c.min_stock,
                    'unit': c.unit,
                    'location': c.location.name if c.location else None,
                    'supplier': c.supplier.name if c.supplier else None,
                }
                for c in items
            ],
        }


@mcp.tool()
def get_replenishment_suggestions(days_ahead: int = 30, lookback_days: int = 90,
                                  include_non_consumables: bool = False) -> dict:
    """消耗品补货建议：按消耗速率估算还能用几天，列出即将耗尽的物品并给出建议补货量。
    消耗速率优先取物品上显式设置的 consumption_rate；未设置时从最近 lookback_days 天的出库流水推算。
    days_ahead 为关注的时间窗（默认 30 天）：仅返回预计在窗口内耗尽的物品。"""
    from datetime import timedelta
    from sqlalchemy import func
    from models import db, Item, Transaction
    days_ahead = max(1, min(int(days_ahead), 365))
    lookback_days = max(7, min(int(lookback_days), 730))
    cutoff = datetime.utcnow() - timedelta(days=lookback_days)

    with _app().app_context():
        # 一次性聚合窗口内各物品的出库总量，避免 N+1 查询
        out_rows = (
            db.session.query(Transaction.item_id, func.coalesce(func.sum(Transaction.quantity), 0))
            .filter(Transaction.type == 'out', Transaction.created_at >= cutoff)
            .group_by(Transaction.item_id).all()
        )
        out_by_id = {cid: float(qty or 0) for cid, qty in out_rows}

        query = Item.query
        if not include_non_consumables:
            query = query.filter(Item.is_consumable.is_(True))

        alerts = []
        tracked = 0
        unknown = []
        for c in query.all():
            tracked += 1
            stock = float(c.current_stock or 0)
            explicit = c.consumption_rate if c.consumption_rate and c.consumption_rate > 0 else None
            derived = out_by_id.get(c.id, 0.0) / lookback_days if out_by_id.get(c.id, 0.0) > 0 else None
            rate = explicit if explicit is not None else derived
            source = 'explicit' if explicit is not None else ('derived' if derived is not None else None)
            if not rate:
                unknown.append({'id': c.id, 'name': c.name, 'current_stock': c.current_stock,
                                'unit': c.unit, 'reason': '无显式消耗速率且窗口内无出库记录'})
                continue
            days_left = stock / rate
            if days_left > days_ahead:
                continue
            target = rate * (days_ahead + 15)  # 补到覆盖窗口 + 15 天缓冲
            suggest_qty = max(0, int(round(target - stock)))
            alerts.append({
                'id': c.id, 'name': c.name,
                'current_stock': c.current_stock, 'unit': c.unit,
                'consumption_rate_per_day': round(rate, 3), 'rate_source': source,
                'estimated_days_left': round(days_left, 1),
                'suggested_order_qty': suggest_qty,
                'supplier': c.supplier.name if c.supplier else None,
                'location': c.location.name if c.location else None,
                'urgency': 'critical' if days_left <= 7 else ('high' if days_left <= 15 else 'medium'),
            })

        alerts.sort(key=lambda x: x['estimated_days_left'])
        return {
            'days_ahead': days_ahead,
            'lookback_days': lookback_days,
            'tracked_items': tracked,
            'alert_count': len(alerts),
            'alerts': alerts,
            'unknown_rate_count': len(unknown),
            'unknown_rate_items': unknown,
        }


@mcp.tool()
def list_expiring_warranties(days_ahead: int = 30) -> dict:
    """扫描即将到期的保修与维护计划。保修看 warranty_expiry；维护看上次维护日 + 维护周期。
    days_ahead 为提前预警天数（默认 30）；已过期的单独归为 overdue。"""
    from datetime import timedelta
    from models import Item
    days_ahead = max(0, min(int(days_ahead), 365))
    today = datetime.utcnow().date()

    with _app().app_context():
        warranties = []
        maintenances = []
        for c in Item.query.all():
            base = {'id': c.id, 'name': c.name, 'location': c.location.name if c.location else None}
            if c.warranty_expiry:
                delta = (c.warranty_expiry - today).days
                if delta <= days_ahead:
                    warranties.append({
                        **base, 'expiry_date': c.warranty_expiry.isoformat(),
                        'days_remaining': delta,
                        'status': 'expired' if delta < 0 else ('today' if delta == 0 else 'expiring'),
                    })
            if c.last_maintenance_date and c.maintenance_cycle_days and c.maintenance_cycle_days > 0:
                next_due = c.last_maintenance_date + timedelta(days=c.maintenance_cycle_days)
                delta = (next_due - today).days
                if delta <= days_ahead:
                    maintenances.append({
                        **base,
                        'last_maintenance_date': c.last_maintenance_date.isoformat(),
                        'cycle_days': c.maintenance_cycle_days,
                        'next_due_date': next_due.isoformat(),
                        'days_remaining': delta,
                        'status': 'overdue' if delta < 0 else ('today' if delta == 0 else 'due'),
                    })
        warranties.sort(key=lambda x: x['days_remaining'])
        maintenances.sort(key=lambda x: x['days_remaining'])
        return {
            'days_ahead': days_ahead,
            'warranty_count': len(warranties), 'warranties': warranties,
            'maintenance_count': len(maintenances), 'maintenances': maintenances,
        }


@mcp.tool()
def get_purchase_spend(months: int = 6, group: str = 'category') -> dict:
    """家庭采购支出看板：按月统计采购金额，并按分类/供应商/物品汇总支出，指出最大开销项。"""
    from services import stats_service
    months = max(1, min(int(months), 36))
    with _app().app_context():
        trend = stats_service.monthly_trend(months=months)
        ranking = stats_service.purchases_by(group=group, limit=20) if group in ('component', 'supplier', 'category') else []
    monthly = [{'month': r['month'], 'cost': r['in_cost'], 'in_qty': r['in_qty']} for r in trend]
    total = round(sum(r['cost'] for r in monthly), 2)
    return {
        'months': months,
        'total_spend': total,
        'monthly': monthly,
        'group_by': group,
        'ranking': ranking,
        'peak_month': max(monthly, key=lambda x: x['cost'])['month'] if monthly and total > 0 else None,
    }


# ---------------------------------------------------------------------------
# 工具函数：生活缴费账单
# ---------------------------------------------------------------------------

def _bill_dict(b):
    return {
        'id': b.id,
        'category': b.category,
        'category_label': _UTILITY_LABELS.get(b.category, b.category),
        'amount': round(float(b.amount or 0), 2),
        'paid_at': b.paid_at.strftime('%Y-%m-%d') if b.paid_at else None,
        'period': b.period,
        'counterparty': b.counterparty,
        'channel': b.channel,
        'channel_label': _UTILITY_CHANNELS.get(b.channel, b.channel),
        'external_id': b.external_id,
        'note': b.note,
        'source': b.source,
    }


@mcp.tool()
def record_utility_bills(bills: list[dict]) -> dict:
    """批量录入生活缴费账单（水/电/燃气/宽带/话费等），支持支付宝、微信、银行代扣等任意渠道。

    bills 为账单字典列表，每条支持以下键：
      category（必填，water/electricity/gas/internet/phone/other）、
      amount（必填，金额）、paid_at（必填，YYYY-MM-DD 或 YYYY-MM-DD HH:MM）、
      channel（缴费渠道，alipay/wechat/bank/cash/other，默认 other）、
      period（账单所属期如 2026-10，可选）、counterparty（收款方，可选）、
      external_id（该渠道的交易单号，可选，填了可跨截图可靠去重）、
      source（录入来源，默认 screenshot）、note（可选）。

    自动去重：同一笔账单重复出现在多张截图时只保留一条；
    去重键带渠道区分——不同渠道的相同单号字符串视为不同交易，不会误合并。
    返回新增/重复/失败三类明细。
    """
    from models import db, UtilityBill
    if not isinstance(bills, list) or not bills:
        return {'error': 'bills 必须是非空列表'}
    allowed = set(_UTILITY_LABELS)
    channels = set(_UTILITY_CHANNELS)
    added, duplicates, failed = [], [], []

    with _app().app_context():
        for idx, item in enumerate(bills):
            if not isinstance(item, dict):
                failed.append({'index': idx, 'reason': '条目不是字典', 'data': str(item)[:100]})
                continue
            category = str(item.get('category', '')).strip().lower()
            if category not in allowed:
                failed.append({'index': idx, 'reason': f'category 无效：{item.get("category")}（可选 {sorted(allowed)}）'})
                continue
            try:
                amount = float(item.get('amount'))
            except (TypeError, ValueError):
                failed.append({'index': idx, 'reason': f'amount 无效：{item.get("amount")}'})
                continue
            if amount <= 0:
                failed.append({'index': idx, 'reason': 'amount 必须大于 0'})
                continue
            paid_at = _parse_datetime(item.get('paid_at'))
            if paid_at is None:
                failed.append({'index': idx, 'reason': f'paid_at 无效：{item.get("paid_at")}（应为 YYYY-MM-DD）'})
                continue
            external_id = str(item.get('external_id') or '').strip() or None
            counterparty = str(item.get('counterparty') or '').strip() or None
            channel = _normalize_channel(item.get('channel'), channels)
            key = UtilityBill.build_dedup_key(
                category, amount, paid_at, counterparty, external_id, channel
            )
            if UtilityBill.query.filter_by(dedup_key=key).first():
                duplicates.append({
                    'index': idx, 'category': category, 'amount': amount,
                    'paid_at': paid_at.strftime('%Y-%m-%d'), 'channel': channel,
                    'reason': '重复账单（同渠道同交易单号，或同渠道同日同类型同金额同收款方）',
                })
                continue
            bill = UtilityBill(
                category=category, amount=amount, paid_at=paid_at,
                period=str(item.get('period') or '').strip() or None,
                counterparty=counterparty,
                external_id=external_id,
                channel=channel,
                note=str(item.get('note') or '').strip() or None,
                source=str(item.get('source') or 'screenshot'),
                dedup_key=key,
            )
            db.session.add(bill)
            added.append(bill)
        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            return {'error': f'写入失败：{exc}', 'added_count': 0}
        return {
            'added_count': len(added),
            'duplicate_count': len(duplicates),
            'failed_count': len(failed),
            'added': [_bill_dict(b) for b in added],
            'duplicates': duplicates,
            'failed': failed,
        }


@mcp.tool()
def list_utility_bills(category: str = '', channel: str = '', start: str = '', end: str = '',
                       limit: int = 100) -> dict:
    """查询生活缴费账单明细。category 可填 water/electricity/gas 等；channel 可填 alipay/wechat/bank/cash/other；start/end 为 YYYY-MM-DD。"""
    from models import UtilityBill
    start_dt = datetime.strptime(start, '%Y-%m-%d') if start else None
    end_dt = datetime.strptime(end, '%Y-%m-%d').replace(hour=23, minute=59, second=59) if end else None
    with _app().app_context():
        query = UtilityBill.query
        if category and category.lower() in _UTILITY_LABELS:
            query = query.filter(UtilityBill.category == category.lower())
        if channel and channel.lower() in _UTILITY_CHANNELS:
            query = query.filter(UtilityBill.channel == channel.lower())
        if start_dt:
            query = query.filter(UtilityBill.paid_at >= start_dt)
        if end_dt:
            query = query.filter(UtilityBill.paid_at <= end_dt)
        rows = query.order_by(UtilityBill.paid_at.desc(), UtilityBill.id.desc()).limit(
            max(1, min(int(limit), 300))
        ).all()
        return {'total': len(rows), 'items': [_bill_dict(b) for b in rows]}


@mcp.tool()
def delete_utility_bill(bill_id: int) -> dict:
    """删除一条误录的缴费账单（纠错用）。返回删除结果。"""
    from models import db, UtilityBill
    with _app().app_context():
        bill = UtilityBill.query.get(bill_id)
        if not bill:
            return {'error': f'账单 ID {bill_id} 不存在'}
        snapshot = _bill_dict(bill)
        db.session.delete(bill)
        db.session.commit()
        return {'deleted': snapshot}


@mcp.tool()
def get_utility_spend(months: int = 6, group: str = 'category') -> dict:
    """生活缴费支出归总：按月趋势 + 按类型/收款方/渠道汇总，含总额与最大开销项。"""
    from models import UtilityBill
    months = max(1, min(int(months), 36))
    now = datetime.utcnow()
    # 从当前月第一天前推 months-1 个月
    year, month = now.year, now.month
    for _ in range(months - 1):
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    start_dt = datetime(year, month, 1)

    with _app().app_context():
        rows = (
            UtilityBill.query
            .filter(UtilityBill.paid_at >= start_dt, UtilityBill.paid_at <= now)
            .order_by(UtilityBill.paid_at.asc()).all()
        )
        monthly_map, group_map = {}, {}
        for b in rows:
            key = b.paid_at.strftime('%Y-%m')
            monthly_map.setdefault(key, {'month': key, 'amount': 0.0, 'count': 0})
            monthly_map[key]['amount'] += float(b.amount or 0)
            monthly_map[key]['count'] += 1
            if group == 'channel':
                gkey = b.channel or 'other'
                label = _UTILITY_CHANNELS.get(gkey, gkey)
            elif group == 'counterparty':
                gkey, label = b.counterparty or '未指定', b.counterparty or '未指定'
            else:
                gkey = b.category
                label = _UTILITY_LABELS.get(gkey, gkey)
            group_map.setdefault(gkey, {'name': gkey, 'label': label, 'amount': 0.0, 'count': 0})
            group_map[gkey]['amount'] += float(b.amount or 0)
            group_map[gkey]['count'] += 1

        monthly = [
            {'month': m, 'amount': round(monthly_map[m]['amount'], 2), 'count': monthly_map[m]['count']}
            for m in sorted(monthly_map)
        ]
        breakdown = sorted(
            [{'key': k, **{kk: (round(vv, 2) if kk == 'amount' else vv) for kk, vv in v.items()}}
             for k, v in group_map.items()],
            key=lambda x: x['amount'], reverse=True,
        )
        total = round(sum(float(b.amount or 0) for b in rows), 2)
        return {
            'months': months,
            'bill_count': len(rows),
            'total_spend': total,
            'monthly': monthly,
            'group_by': group if group in ('category', 'counterparty', 'channel') else 'category',
            'breakdown': breakdown,
            'peak_month': max(monthly, key=lambda x: x['amount'])['month'] if monthly else None,
            'top_item': breakdown[0] if breakdown else None,
        }


# ---------------------------------------------------------------------------
# 工具函数：家庭各类开支（教育/培训/旅行/娱乐/购物/医疗…）
# ---------------------------------------------------------------------------

from utils.ledger import EXPENSE_LABELS as _EXPENSE_LABELS  # noqa: E402
from utils.ledger import MAINTENANCE_ALIASES as _MAINTENANCE_ALIASES  # noqa: E402
from utils.ledger import MAINTENANCE_LABELS as _MAINTENANCE_LABELS  # noqa: E402

_EXPENSE_ALIASES = {
    '教育': 'education', '学费': 'education', '学习': 'education', 'education': 'education',
    '培训': 'training', '课程': 'training', '课外班': 'training', 'training': 'training',
    '旅行': 'travel', '旅游': 'travel', '出行度假': 'travel', 'travel': 'travel',
    '娱乐': 'entertainment', '文娱': 'entertainment', '休闲': 'entertainment',
    '购物': 'shopping', '买东西': 'shopping', 'shopping': 'shopping',
    '医疗': 'medical', '看病': 'medical', '健康': 'medical', 'medical': 'medical',
    '餐饮': 'dining', '吃饭': 'dining', '餐费': 'dining', 'dining': 'dining',
    '交通': 'transport', '打车': 'transport', 'transport': 'transport',
    '居住': 'housing', '房租': 'housing', '物业': 'housing', 'housing': 'housing',
    '数码': 'digital', '电子': 'digital', 'digital': 'digital',
    '维修保养': 'maintenance', '维修': 'maintenance', '保养': 'maintenance',
    'maintenance': 'maintenance',
    '其他': 'other', 'other': 'other',
}


def _normalize_expense_category(value):
    """把中文/英文类型名归一化为内部枚举值；无法识别返回空串（由调用方判为失败）。"""
    raw = str(value or '').strip()
    if not raw:
        return ''
    key = _EXPENSE_ALIASES.get(raw, raw.lower())
    return key if key in _EXPENSE_LABELS else ''


def _resolve_component_ref(raw):
    """解析对话传入的物品引用，返回 (item_id 或 None, 错误说明或 None)。

    接受物品 ID（int 或纯数字字符串），也接受名称精确匹配——用户在对话里更像
    会说「吸尘器」而不是报 ID。重名时要求改用 ID，避免挂错物品。
    """
    from models import Item, db
    if raw in (None, '', 0, '0'):
        return None, None
    text = str(raw).strip()
    if text.isdigit():
        component = db.session.get(Item, int(text))
        if not component:
            return None, f'物品 ID {text} 不存在'
        return component.id, None
    matches = Item.query.filter(Item.name == text).limit(2).all()
    if not matches:
        matches = Item.query.filter(Item.name.ilike(f'%{text}%')).limit(2).all()
    if not matches:
        return None, f'未找到名为「{text}」的物品'
    if len(matches) > 1:
        names = '、'.join(f'{m.name}(id={m.id})' for m in matches)
        return None, f'「{text}」匹配到多个物品（{names}），请改用物品 ID'
    return matches[0].id, None


def _normalize_tags(value):
    """标签归一化为逗号分隔字符串，接受列表或「a,b / a、b」这类字符串。"""
    if not value:
        return None
    if isinstance(value, (list, tuple, set)):
        parts = [str(v).strip() for v in value]
    else:
        text = str(value).replace('，', ',').replace('、', ',').replace(';', ',')
        parts = [p.strip() for p in text.split(',')]
    cleaned = [p for p in parts if p]
    return ','.join(cleaned)[:200] if cleaned else None


def _months_window(months):
    """返回 (钳制后的月数, 窗口起始日, 当前时间)，供月度统计零填充用。"""
    months = max(1, min(int(months), 36))
    now = datetime.now()
    year, month = now.year, now.month
    for _ in range(months - 1):
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return months, datetime(year, month, 1), now


def _month_keys(start_dt, end_dt):
    """枚举窗口内的月份键（含两端），用于给趋势补零。"""
    keys = []
    year, month = start_dt.year, start_dt.month
    while (year, month) <= (end_dt.year, end_dt.month):
        keys.append(f'{year:04d}-{month:02d}')
        month += 1
        if month == 13:
            month, year = 1, year + 1
    return keys


def _attachment_dict(a):
    return {
        'id': a.id,
        'file_path': a.file_path,
        'sha256': a.sha256,
        'size_bytes': a.size_bytes,
        'mime': a.mime,
    }


def _expense_dict(e, attachments=None):
    d = {
        'id': e.id,
        'category': e.category,
        'category_label': _EXPENSE_LABELS.get(e.category, e.category),
        'subcategory': e.subcategory,
        'amount': round(float(e.amount or 0), 2),
        'occurred_at': e.occurred_at.strftime('%Y-%m-%d') if e.occurred_at else None,
        'merchant': e.merchant,
        'channel': e.channel,
        'channel_label': _UTILITY_CHANNELS.get(e.channel, e.channel),
        'external_id': e.external_id,
        'note': e.note,
        'tags': [t for t in (e.tags or '').split(',') if t],
        'currency': e.currency or 'CNY',
        'source': e.source,
        'item_id': e.item_id,
        'item_name': e.item.name if e.item else None,
    }
    if attachments is not None:
        d['attachments'] = attachments
    return d


@mcp.tool()
def record_expenses(expenses: list[dict]) -> dict:
    """批量录入家庭各类开支（教育/培训/旅行/娱乐/购物/医疗/餐饮/交通/居住/数码/维修保养/其他）。

    注意：水费、电费、燃气费、宽带费、话费请用 ``record_utility_bills``，
    不要记到这里，否则家庭总支出会重复计算。
    修东西、保养家电请优先用 ``record_maintenance``——它会同时生成维修开支并挂到物品上。

    expenses 为开支字典列表，每条支持以下键：
      category（必填，可用中文或英文：教育/培训/旅行/娱乐/购物/医疗/餐饮/交通/居住/数码/维修保养/其他，
        或 education/training/travel/entertainment/shopping/medical/dining/transport/housing/digital/maintenance/other）、
      amount（必填，金额，大于 0）、
      occurred_at（必填，消费发生时间，YYYY-MM-DD 或 YYYY-MM-DD HH:MM）、
      subcategory（可选，自由文本细分，如「英语培训」「机票」「电影」）、
      merchant（商户/机构/平台，可选）、
      channel（支付渠道：alipay/wechat/bank/cash/other，也接受中文「支付宝/微信/银行/现金」）、
      external_id（该渠道交易单号，可选；填了可跨截图可靠去重）、
      note（备注，可选）、tags（标签，列表或逗号分隔字符串，可选）、
      source（录入来源，默认 manual；截图录入可填 screenshot）、
      item_id（可选，关联物品：填物品 ID 或物品名称，如「吸尘器」。买了家电、
        家具、数码产品时建议填上，之后用 get_component_ledger 就能看到这台机器总共花了多少）、
      receipt_path（凭证图片路径，可选；文件已存在于磁盘时登记其 SHA-256 与大小，
        不存在只记 warning 不阻断录入。文件上传接口尚未提供，路径需指向已有文件）。

    自动去重：同一笔开支重复出现在多张截图/多次说及时只保留一条。
    去重键带渠道区分——不同渠道的相同单号字符串视为不同交易。
    返回新增/重复/失败三类明细，失败项说明具体原因。
    """
    from models import db, Expense, ExpenseAttachment
    if not isinstance(expenses, list) or not expenses:
        return {'error': 'expenses 必须是非空列表'}

    added_pairs, duplicates, failed = [], [], []

    with _app().app_context():
        for idx, item in enumerate(expenses):
            if not isinstance(item, dict):
                failed.append({'index': idx, 'reason': '条目不是字典', 'data': str(item)[:100]})
                continue

            category = _normalize_expense_category(item.get('category'))
            if not category:
                failed.append({
                    'index': idx,
                    'reason': f'category 无效：{item.get("category")}'
                              f'（可选 {sorted(_EXPENSE_LABELS)} 或对应中文名）',
                })
                continue

            try:
                amount = float(item.get('amount'))
            except (TypeError, ValueError):
                failed.append({'index': idx, 'reason': f'amount 无效：{item.get("amount")}'})
                continue
            if amount <= 0:
                failed.append({'index': idx, 'reason': 'amount 必须大于 0'})
                continue

            occurred_at = _parse_datetime(item.get('occurred_at') or item.get('paid_at'))
            if occurred_at is None:
                failed.append({
                    'index': idx,
                    'reason': f'occurred_at 无效：{item.get("occurred_at")}（应为 YYYY-MM-DD）',
                })
                continue

            channel = _normalize_channel(item.get('channel'), Expense.VALID_CHANNELS)
            external_id = str(item.get('external_id') or '').strip() or None
            merchant = str(item.get('merchant') or '').strip() or None
            item_id, comp_error = _resolve_component_ref(item.get('item_id'))
            if comp_error:
                failed.append({'index': idx, 'reason': comp_error})
                continue
            key = Expense.build_dedup_key(
                category, amount, occurred_at, merchant, external_id, channel
            )
            if Expense.query.filter_by(dedup_key=key).first():
                duplicates.append({
                    'index': idx,
                    'category': category,
                    'category_label': _EXPENSE_LABELS.get(category, category),
                    'amount': amount,
                    'occurred_at': occurred_at.strftime('%Y-%m-%d'),
                    'channel': channel,
                    'reason': '重复开支（同渠道同交易单号，或同渠道同日同类型同金额同商户）',
                })
                continue

            expense = Expense(
                category=category,
                subcategory=str(item.get('subcategory') or '').strip() or None,
                amount=amount,
                occurred_at=occurred_at,
                merchant=merchant,
                channel=channel,
                external_id=external_id,
                note=str(item.get('note') or '').strip() or None,
                tags=_normalize_tags(item.get('tags')),
                currency=str(item.get('currency') or 'CNY').strip().upper()[:8],
                source=str(item.get('source') or 'manual').strip(),
                dedup_key=key,
                item_id=item_id,
            )
            db.session.add(expense)
            db.session.flush()  # 先拿到 id，便于挂凭证

            warnings = []
            raw_receipts = item.get('receipt_path')
            if raw_receipts:
                receipts = raw_receipts if isinstance(raw_receipts, list) else [raw_receipts]
                for raw_path in receipts:
                    _, warning = _store_receipt(expense.id, raw_path)
                    if warning:
                        warnings.append(warning)
            added_pairs.append((expense, warnings))

        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            return {'error': f'写入失败：{exc}', 'added_count': 0}

        added = []
        for expense, warnings in added_pairs:
            atts = [
                _attachment_dict(a) for a in
                ExpenseAttachment.query.filter_by(expense_id=expense.id).all()
            ]
            row = _expense_dict(expense, atts)
            if warnings:
                row['warnings'] = warnings
            added.append(row)

        return {
            'added_count': len(added),
            'duplicate_count': len(duplicates),
            'failed_count': len(failed),
            'added': added,
            'duplicates': duplicates,
            'failed': failed,
        }


@mcp.tool()
def attach_expense_receipt(expense_id: int, file_path: str) -> dict:
    """给已录入的开支补挂一张凭证图片（票据/截图）。

    file_path 指向磁盘上已存在的图片文件（绝对路径，或相对 backend/instance、backend 的路径）。
    支持 JPG / PNG / WEBP，单张上限 10MB。图片会被重新编码以**剥离 EXIF（含 GPS 定位）**，
    并以内容 SHA-256 命名存到 instance/uploads/ —— 同一张图重复挂到同一笔开支会被跳过。

    注意：本工具只能读取磁盘上已有的文件，无法接收对话中直接发送的图片。
    若图片尚未落盘，请通过 Web 端「家庭开支」页面上传。
    返回登记的凭证元信息（哈希/大小/MIME）或失败原因。
    """
    from models import db, Expense, ExpenseAttachment
    with _app().app_context():
        expense = Expense.query.get(expense_id)
        if not expense:
            return {'error': f'开支 ID {expense_id} 不存在'}
        att, warning = _store_receipt(expense_id, file_path)
        if warning:
            return {'error': warning}
        db.session.commit()
        return {
            'expense_id': expense_id,
            'attachment': _attachment_dict(att),
            'note': '已剥离 EXIF 并按内容哈希存储',
        }


@mcp.tool()
def list_expenses(category: str = '', subcategory: str = '', merchant: str = '',
                  channel: str = '', start: str = '', end: str = '',
                  keyword: str = '', item_id: str = '', limit: int = 100) -> dict:
    """查询家庭开支明细。

    category 可填中文或英文类型名；subcategory/merchant 为模糊匹配；
    channel 可填 alipay/wechat/bank/cash/other；start/end 为 YYYY-MM-DD；
    keyword 在备注、商户、子类、标签中模糊搜索。
    item_id 填物品 ID 或名称，只看挂在某个物品上的开支（如「吸尘器花了多少」）。
    每条记录附带已登记的凭证附件（路径/哈希/大小/MIME）与关联物品。
    """
    from sqlalchemy import or_
    from models import Expense, ExpenseAttachment
    start_dt = datetime.strptime(start, '%Y-%m-%d') if start else None
    end_dt = datetime.strptime(end, '%Y-%m-%d').replace(hour=23, minute=59, second=59) if end else None
    category_key = _normalize_expense_category(category) if category else ''

    with _app().app_context():
        query = Expense.query
        if item_id:
            ref_id, ref_error = _resolve_component_ref(item_id)
            if ref_error:
                return {'error': ref_error}
            query = query.filter(Expense.item_id == ref_id)
        if category_key:
            query = query.filter(Expense.category == category_key)
        if subcategory:
            query = query.filter(Expense.subcategory.ilike(f'%{subcategory}%'))
        if merchant:
            query = query.filter(Expense.merchant.ilike(f'%{merchant}%'))
        if channel:
            query = query.filter(
                Expense.channel == _normalize_channel(channel, Expense.VALID_CHANNELS)
            )
        if start_dt:
            query = query.filter(Expense.occurred_at >= start_dt)
        if end_dt:
            query = query.filter(Expense.occurred_at <= end_dt)
        if keyword:
            like = f'%{keyword}%'
            query = query.filter(or_(
                Expense.note.ilike(like),
                Expense.merchant.ilike(like),
                Expense.subcategory.ilike(like),
                Expense.tags.ilike(like),
            ))

        total = query.count()
        rows = query.order_by(
            Expense.occurred_at.desc(), Expense.id.desc()
        ).limit(max(1, min(int(limit), 500))).all()

        ids = [e.id for e in rows]
        att_map = {}
        if ids:
            for a in ExpenseAttachment.query.filter(ExpenseAttachment.expense_id.in_(ids)).all():
                att_map.setdefault(a.expense_id, []).append(_attachment_dict(a))

        items = [_expense_dict(e, att_map.get(e.id, [])) for e in rows]
        return {
            'total': total,
            'returned': len(items),
            'sum_amount': round(sum(i['amount'] for i in items), 2),
            'items': items,
        }


@mcp.tool()
def delete_expense(expense_id: int) -> dict:
    """删除一条误录的开支（纠错用）。

    同时删除其凭证数据库记录，但**不删除磁盘上的文件**——文件可能被其他记录引用，
    且误删不可恢复，留待人工清理。返回被删除的记录快照。
    """
    from models import db, Expense, ExpenseAttachment
    with _app().app_context():
        expense = Expense.query.get(expense_id)
        if not expense:
            return {'error': f'开支 ID {expense_id} 不存在'}
        atts = [_attachment_dict(a) for a in
                ExpenseAttachment.query.filter_by(expense_id=expense_id).all()]
        snapshot = _expense_dict(expense, atts)
        db.session.delete(expense)
        db.session.commit()
        return {
            'deleted': snapshot,
            'attachment_rows_removed': len(atts),
            'note': '磁盘文件保留未删除' if atts else None,
        }


@mcp.tool()
def get_expense_spend(months: int = 6, group: str = 'category') -> dict:
    """开支支出归总：按月趋势（零填充）+ 按类型/子类/商户/渠道汇总，含总额与最大开销项。

    group 可选 category（默认）/subcategory/merchant/channel。
    """
    from models import Expense
    months, start_dt, now = _months_window(months)

    with _app().app_context():
        rows = (
            Expense.query
            .filter(Expense.occurred_at >= start_dt, Expense.occurred_at <= now)
            .order_by(Expense.occurred_at.asc()).all()
        )
        monthly_map, group_map = {}, {}
        for e in rows:
            month = e.occurred_at.strftime('%Y-%m')
            monthly_map[month] = monthly_map.get(month, 0.0) + float(e.amount or 0)

            if group == 'subcategory':
                gkey = e.subcategory or '未细分'
                label = gkey
            elif group == 'merchant':
                gkey = e.merchant or '未指定'
                label = gkey
            elif group == 'channel':
                gkey = e.channel or 'other'
                label = _UTILITY_CHANNELS.get(gkey, gkey)
            else:
                gkey = e.category
                label = _EXPENSE_LABELS.get(gkey, gkey)
            group_map.setdefault(gkey, {'name': gkey, 'label': label, 'amount': 0.0, 'count': 0})
            group_map[gkey]['amount'] += float(e.amount or 0)
            group_map[gkey]['count'] += 1

        keys = _month_keys(start_dt, now)
        monthly = [
            {'month': k, 'amount': round(monthly_map.get(k, 0.0), 2),
             'count': sum(1 for e in rows if e.occurred_at.strftime('%Y-%m') == k)}
            for k in keys
        ]
        breakdown = sorted(
            [{'key': k, **{kk: (round(vv, 2) if kk == 'amount' else vv) for kk, vv in v.items()}}
             for k, v in group_map.items()],
            key=lambda x: x['amount'], reverse=True,
        )
        total = round(sum(float(e.amount or 0) for e in rows), 2)
        return {
            'months': months,
            'expense_count': len(rows),
            'total_spend': total,
            'monthly': monthly,
            'group_by': group if group in ('category', 'subcategory', 'merchant', 'channel') else 'category',
            'breakdown': breakdown,
            'peak_month': max(monthly, key=lambda x: x['amount'])['month'] if total > 0 else None,
            'top_item': breakdown[0] if breakdown else None,
            'avg_per_month': round(total / months, 2) if months else 0.0,
        }


@mcp.tool()
def get_household_spend_overview(months: int = 6) -> dict:
    """家庭总支出看板：合并生活缴费（水电煤等）与各类开支，给出总额、月度趋势与分类排行。

    两张表物理分开、统计时归一。注意：同一笔支出若既记入 ``record_utility_bills``
    又记入 ``record_expenses``，会被重复计算——每笔只记一处。
    """
    from models import Expense, UtilityBill
    months, start_dt, now = _months_window(months)
    currency = 'CNY'

    with _app().app_context():
        expenses = (
            Expense.query
            .filter(Expense.occurred_at >= start_dt, Expense.occurred_at <= now).all()
        )
        bills = (
            UtilityBill.query
            .filter(UtilityBill.paid_at >= start_dt, UtilityBill.paid_at <= now).all()
        )

        monthly_map = {k: {'expense': 0.0, 'utility': 0.0} for k in _month_keys(start_dt, now)}
        cat_map = {}

        for e in expenses:
            month = e.occurred_at.strftime('%Y-%m')
            monthly_map.setdefault(month, {'expense': 0.0, 'utility': 0.0})['expense'] += float(e.amount or 0)
            cat_map.setdefault(
                ('expense', e.category),
                {'source': 'expense', 'key': e.category,
                 'label': _EXPENSE_LABELS.get(e.category, e.category), 'amount': 0.0, 'count': 0},
            )
            node = cat_map[('expense', e.category)]
            node['amount'] += float(e.amount or 0)
            node['count'] += 1

        for b in bills:
            month = b.paid_at.strftime('%Y-%m')
            monthly_map.setdefault(month, {'expense': 0.0, 'utility': 0.0})['utility'] += float(b.amount or 0)
            cat_map.setdefault(
                ('utility', b.category),
                {'source': 'utility', 'key': b.category,
                 'label': _UTILITY_LABELS.get(b.category, b.category), 'amount': 0.0, 'count': 0},
            )
            node = cat_map[('utility', b.category)]
            node['amount'] += float(b.amount or 0)
            node['count'] += 1

        expense_total = round(sum(float(e.amount or 0) for e in expenses), 2)
        utility_total = round(sum(float(b.amount or 0) for b in bills), 2)
        monthly = [
            {'month': k,
             'expense': round(v['expense'], 2),
             'utility': round(v['utility'], 2),
             'total': round(v['expense'] + v['utility'], 2)}
            for k, v in sorted(monthly_map.items())
        ]
        by_category = sorted(
            [{'source': v['source'], 'key': v['key'], 'label': v['label'],
              'amount': round(v['amount'], 2), 'count': v['count']}
             for v in cat_map.values()],
            key=lambda x: x['amount'], reverse=True,
        )
        grand_total = round(expense_total + utility_total, 2)
        return {
            'months': months,
            'currency': currency,
            'grand_total': grand_total,
            'expense_total': expense_total,
            'utility_total': utility_total,
            'expense_count': len(expenses),
            'utility_count': len(bills),
            'monthly': monthly,
            'by_category': by_category,
            'top_categories': by_category[:5],
            'peak_month': max(monthly, key=lambda x: x['total'])['month'] if grand_total > 0 else None,
            'avg_per_month': round(grand_total / months, 2) if months else 0.0,
            'note': '同一笔支出若同时记入缴费与开支，会重复计算；每笔只记一处。',
        }


@mcp.tool()
def record_maintenance(item_id: str, title: str, performed_at: str = '',
                       type: str = '', vendor: str = '', cost: float = 0,
                       channel: str = '', note: str = '') -> dict:
    """记录一次物品维护（清洁保养 / 维修 / 更换耗材 / 巡检）。

    item_id 填物品 ID 或名称（如「吸尘器」）；
    title 说明做了什么（如「更换 HEPA 滤芯」「清洗冷凝器」「主板维修」）；
    performed_at 为 YYYY-MM-DD，留空则记为今天；
    type 可选 cleaning/repair/replacement/inspection/other，
      也接受中文「清洁/保养/维修/更换/巡检」；
    cost 为本次花费，大于 0 时会自动生成一笔「维修保养」开支并挂到该物品上
      （同渠道同日同金额已存在时不重复记账，返回 warnings 说明）；
    channel 为付款渠道，默认 other。

    记录后会自动把该物品的「上次维护日期」推到本次，维护提醒随之顺延。
    查某件东西总共花了多少、修过几次，用 get_component_ledger。
    """
    from models import Item, db
    from services import maintenance_service
    with _app().app_context():
        ref_id, ref_error = _resolve_component_ref(item_id)
        if ref_error:
            return {'error': ref_error}
        if not ref_id:
            return {'error': '请提供物品 ID 或名称'}
        component = db.session.get(Item, ref_id)
        if not component:
            return {'error': f'物品 ID {ref_id} 不存在'}
        try:
            record, warnings = maintenance_service.create_record(
                component,
                title=title,
                performed_at=performed_at or datetime.now().strftime('%Y-%m-%d'),
                mtype=type,
                vendor=vendor,
                note=note,
                cost=cost,
                channel=channel,
            )
        except maintenance_service.MaintenanceError as exc:
            return {'error': str(exc)}

        data = maintenance_service.serialize(record, with_component=True)
        data['warnings'] = warnings
        data['last_maintenance_date'] = (
            component.last_maintenance_date.strftime('%Y-%m-%d')
            if component.last_maintenance_date else None
        )
        return data


@mcp.tool()
def list_maintenances(item_id: str = '', type: str = '', start: str = '',
                      end: str = '', keyword: str = '', limit: int = 100) -> dict:
    """查询维护记录。

    item_id 可填物品 ID 或名称，只看某个物品的维护历史；
    type 可选 cleaning/repair/replacement/inspection/other（也接受中文）；
    start/end 为 YYYY-MM-DD；keyword 在维护内容、服务商、备注中模糊搜索。
    """
    from models import Maintenance
    from utils.ledger import MAINTENANCE_LABELS
    with _app().app_context():
        query = Maintenance.query
        if item_id:
            ref_id, ref_error = _resolve_component_ref(item_id)
            if ref_error:
                return {'error': ref_error}
            query = query.filter(Maintenance.item_id == ref_id)
        if type:
            want = _MAINTENANCE_ALIASES.get(type.strip(), type.strip().lower())
            query = query.filter(Maintenance.type == want)
        start_dt = _parse_datetime(start) if start else None
        end_dt = _parse_datetime(end) if end else None
        if end_dt:
            end_dt = end_dt.replace(hour=23, minute=59, second=59)
        if start_dt:
            query = query.filter(Maintenance.performed_at >= start_dt)
        if end_dt:
            query = query.filter(Maintenance.performed_at <= end_dt)
        if keyword:
            like = f'%{keyword}%'
            from sqlalchemy import or_
            query = query.filter(or_(
                Maintenance.title.ilike(like),
                Maintenance.vendor.ilike(like),
                Maintenance.note.ilike(like),
            ))

        total = query.count()
        rows = query.order_by(
            Maintenance.performed_at.desc(), Maintenance.id.desc()
        ).limit(max(1, min(int(limit), 500))).all()

        from services.maintenance_service import serialize
        items = []
        for m in rows:
            row = serialize(m, with_component=True)
            row['type_label'] = MAINTENANCE_LABELS.get(m.type, m.type)
            items.append(row)
        return {
            'total': total,
            'count': len(items),
            'type_labels': MAINTENANCE_LABELS,
            'items': items,
        }


@mcp.tool()
def get_component_ledger(item_id: str) -> dict:
    """查看某个物品的持有账本：买它花了多少、修它花了多少、修过几次、年均成本、保修还剩多久。

    item_id 可填物品 ID 或名称。购置成本取该物品名下非维修类开支，
    维修成本取维修类开支，两者同源于开支表，不会重复计算。
    没有登记过开支的物品只会显示维护次数与保修状态。
    """
    from models import Item, db
    from services.maintenance_service import build_ledger
    with _app().app_context():
        ref_id, ref_error = _resolve_component_ref(item_id)
        if ref_error:
            return {'error': ref_error}
        if not ref_id:
            return {'error': '请提供物品 ID 或名称'}
        component = db.session.get(Item, ref_id)
        if not component:
            return {'error': f'物品 ID {ref_id} 不存在'}
        return build_ledger(component)


@mcp.tool()
def list_categories() -> list:
    """返回完整的分类树（多级嵌套）。"""
    from models import Category

    def serialize(c):
        return {
            'id': c.id, 'name': c.name, 'parent_id': c.parent_id,
            'children': [serialize(ch) for ch in c.children],
        }

    with _app().app_context():
        roots = Category.query.filter_by(parent_id=None).order_by(Category.id.asc()).all()
        return [serialize(c) for c in roots]


@mcp.tool()
def list_suppliers() -> list:
    """列出所有供应商及其联系方式。"""
    from models import Supplier
    with _app().app_context():
        return [
            {'id': s.id, 'name': s.name, 'contact': s.contact, 'phone': s.phone,
             'email': None, 'address': s.address, 'website': s.website}
            for s in Supplier.query.order_by(Supplier.id.asc()).all()
        ]


@mcp.tool()
def list_locations() -> list:
    """列出所有库位及其说明。"""
    from models import Location
    with _app().app_context():
        return [
            {'id': loc.id, 'name': loc.name, 'description': loc.description}
            for loc in Location.query.order_by(Location.id.asc()).all()
        ]


@mcp.tool()
def list_transactions(item_id: int | None = None, tx_type: str = '',
                      start: str = '', end: str = '', limit: int = 50) -> dict:
    """查询库存流水。tx_type 为 'in'(入库) / 'out'(出库)；start/end 为 YYYY-MM-DD。"""
    from services.transaction_service import list_transactions as svc_list
    start_dt = datetime.strptime(start, '%Y-%m-%d') if start else None
    end_dt = datetime.strptime(end, '%Y-%m-%d').replace(hour=23, minute=59, second=59) if end else None
    with _app().app_context():
        return svc_list(
            item_id=item_id,
            tx_type=tx_type if tx_type in ('in', 'out') else None,
            start=start_dt, end=end_dt, page=1, per_page=max(1, min(limit, 200)),
        )


@mcp.tool()
def get_stats_overview(start: str = '', end: str = '') -> dict:
    """获取库存与采购/消耗总览：物料数、低库存数、入库/出库量、采购金额、库存估值等。"""
    from services import stats_service
    start_dt = datetime.strptime(start, '%Y-%m-%d') if start else None
    end_dt = datetime.strptime(end, '%Y-%m-%d').replace(hour=23, minute=59, second=59) if end else None
    with _app().app_context():
        return stats_service.overview(start_dt, end_dt)


@mcp.tool()
def get_purchase_ranking(group: str = 'component', limit: int = 10,
                         start: str = '', end: str = '') -> list:
    """采购排行。group 取 'component' / 'supplier' / 'category'。"""
    from services import stats_service
    start_dt = datetime.strptime(start, '%Y-%m-%d') if start else None
    end_dt = datetime.strptime(end, '%Y-%m-%d').replace(hour=23, minute=59, second=59) if end else None
    with _app().app_context():
        return stats_service.purchases_by(group=group, limit=limit, start=start_dt, end=end_dt)


@mcp.tool()
def get_consumption_ranking(group: str = 'component', limit: int = 10,
                            start: str = '', end: str = '') -> list:
    """消耗排行。group 取 'component' / 'category'。"""
    from services import stats_service
    start_dt = datetime.strptime(start, '%Y-%m-%d') if start else None
    end_dt = datetime.strptime(end, '%Y-%m-%d').replace(hour=23, minute=59, second=59) if end else None
    with _app().app_context():
        return stats_service.consumption_by(group=group, limit=limit, start=start_dt, end=end_dt)


@mcp.tool()
def get_monthly_trend(months: int = 12) -> list:
    """获取最近 N 个月（<=36）的采购/消耗月度趋势。"""
    from services import stats_service
    with _app().app_context():
        return stats_service.monthly_trend(months=months)


@mcp.tool()
def stock_in(item_id: int, quantity: int, unit_price: float | None = None,
             note: str = '') -> dict:
    """对物料执行入库（增加库存并记录流水）。unit_price 为采购单价（元），可选。"""
    from services.transaction_service import post_stock_movement, StockError
    operator_id = int(os.getenv('MCP_OPERATOR_ID', '1'))
    try:
        with _app().app_context():
            return post_stock_movement(
                item_id=item_id, movement_type='in', quantity=quantity,
                operator_id=operator_id, note=note, unit_price=unit_price,
            )
    except StockError as exc:
        return {'error': str(exc)}


@mcp.tool()
def stock_out(item_id: int, quantity: int, note: str = '') -> dict:
    """对物料执行出库（扣减库存并记录流水），库存不足时返回错误。"""
    from services.transaction_service import post_stock_movement, StockError
    operator_id = int(os.getenv('MCP_OPERATOR_ID', '1'))
    try:
        with _app().app_context():
            return post_stock_movement(
                item_id=item_id, movement_type='out', quantity=quantity,
                operator_id=operator_id, note=note,
            )
    except StockError as exc:
        return {'error': str(exc)}


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    print(f'[PartKeeper MCP] Transport: Streamable HTTP', file=sys.stderr)
    print(f'[PartKeeper MCP] Endpoint : http://{MCP_HOST}:{MCP_PORT}{MCP_PATH}', file=sys.stderr)
    print(f'[PartKeeper MCP] Auth     : Bearer token (Web-issued pk_ token / MCP_API_KEY / admin JWT)', file=sys.stderr)
    mcp.run(transport='streamable-http')
