"""PartKeeper MCP Server —— 对外通信层（Streamable HTTP + Bearer 认证）。

以独立进程运行，与 Flask Web Server 共享同一个 SQLite 数据库与业务逻辑层。
供 WorkBuddy 自定义连接器（Connector）通过 MCP 协议访问 PartKeeper 的物料数据。

启动：
    python mcp_server.py

认证：
    客户端请求需携带 ``Authorization: Bearer <token>``。
    token 支持两种：
      1. 在 .env 配置的 MCP_API_KEY（静态密钥，推荐用于连接器）；
      2. 用 SECRET_KEY 签发的、role=admin 的 JWT（与 Web 端同一套密钥）。

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


class PartKeeperTokenVerifier(TokenVerifier):
    """校验连接器使用的 Bearer Token。"""

    async def verify_token(self, token: str) -> Optional[AccessToken]:
        # 1) 静态 API Key（常量时间比较，避免时序侧信道）
        if _MCP_API_KEY:
            import hmac
            if hmac.compare_digest(token, _MCP_API_KEY):
                return AccessToken(token=token, client_id='workbuddy-connector', scopes=['mcp:admin'])

        # 2) 复用 Web 端 JWT：仅放行 admin
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
        'PartKeeper 电子元器件物料管理系统的 MCP 接口。'
        '可查询物料、库存、分类、供应商、库位、库存流水与统计；'
        '可新建物料档案、执行入库/出库操作。所有数据读写均作用于同一 SQLite 数据库。'
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


def _component_dict(c):
    return {
        'id': c.id,
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
    }


@mcp.tool()
def list_components(keyword: str = '', category: str = '', only_low_stock: bool = False,
                    limit: int = 50) -> dict:
    """查询物料列表。可按名称/参数值/封装/品牌关键词模糊搜索，按分类名过滤，或只看低库存。"""
    from models import Component, Category
    with _app().app_context():
        query = Component.query
        if keyword:
            from sqlalchemy import or_
            kw = f'%{keyword}%'
            query = query.filter(or_(
                Component.name.like(kw), Component.value.like(kw),
                Component.package.like(kw), Component.brand.like(kw),
            ))
        if category:
            cat = Category.query.filter(Category.name.like(f'%{category}%')).first()
            if cat:
                query = query.filter(Component.category_id == cat.id)
            else:
                return {'total': 0, 'items': [], 'note': f'未找到分类：{category}'}
        items = query.order_by(Component.id.desc()).limit(max(1, min(limit, 200))).all()
        data = [_component_dict(c) for c in items]
        if only_low_stock:
            data = [d for d in data if d['low_stock']]
        return {'total': len(data), 'items': data}


@mcp.tool()
def get_component(component_id: int) -> dict:
    """按 ID 查询单个物料的完整详情。"""
    from models import Component
    with _app().app_context():
        c = Component.query.get(component_id)
        if not c:
            return {'error': f'物料 ID {component_id} 不存在'}
        return _component_dict(c)


@mcp.tool()
def create_component(name: str, value: str = '', package: str = '', tolerance: str = '',
                     brand: str = '', datasheet_url: str = '', min_stock: int = 0,
                     current_stock: int = 0, unit: str = '个', category: str = '',
                     location: str = '', supplier: str = '') -> dict:
    """新建物料档案。name 必填；category/location/supplier 传名称即可自动关联（也可留空）。
    关联名称找不到时不会阻断建档，会在 warnings 中说明。返回新物料 ID 与完整信息。"""
    from models import db, Component, Category, Location, Supplier
    name = (name or '').strip()
    if not name:
        return {'error': '物料名称不能为空'}
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

        component = Component(
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
    from models import Component
    with _app().app_context():
        items = Component.query.filter(
            Component.current_stock <= Component.min_stock
        ).order_by(Component.current_stock.asc()).all()
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
def list_transactions(component_id: int | None = None, tx_type: str = '',
                      start: str = '', end: str = '', limit: int = 50) -> dict:
    """查询库存流水。tx_type 为 'in'(入库) / 'out'(出库)；start/end 为 YYYY-MM-DD。"""
    from services.transaction_service import list_transactions as svc_list
    start_dt = datetime.strptime(start, '%Y-%m-%d') if start else None
    end_dt = datetime.strptime(end, '%Y-%m-%d').replace(hour=23, minute=59, second=59) if end else None
    with _app().app_context():
        return svc_list(
            component_id=component_id,
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
def stock_in(component_id: int, quantity: int, unit_price: float | None = None,
             note: str = '') -> dict:
    """对物料执行入库（增加库存并记录流水）。unit_price 为采购单价（元），可选。"""
    from services.transaction_service import post_stock_movement, StockError
    operator_id = int(os.getenv('MCP_OPERATOR_ID', '1'))
    try:
        with _app().app_context():
            return post_stock_movement(
                component_id=component_id, movement_type='in', quantity=quantity,
                operator_id=operator_id, note=note, unit_price=unit_price,
            )
    except StockError as exc:
        return {'error': str(exc)}


@mcp.tool()
def stock_out(component_id: int, quantity: int, note: str = '') -> dict:
    """对物料执行出库（扣减库存并记录流水），库存不足时返回错误。"""
    from services.transaction_service import post_stock_movement, StockError
    operator_id = int(os.getenv('MCP_OPERATOR_ID', '1'))
    try:
        with _app().app_context():
            return post_stock_movement(
                component_id=component_id, movement_type='out', quantity=quantity,
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
    print(f'[PartKeeper MCP] Auth     : Bearer token (MCP_API_KEY or admin JWT)', file=sys.stderr)
    mcp.run(transport='streamable-http')
