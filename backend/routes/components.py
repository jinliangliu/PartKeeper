from flask import Blueprint, request, jsonify
from models import db, Item, ItemSpec, Category, Expense, Maintenance, Supplier, Location, Transaction
from utils.decorators import login_required, admin_required
from datetime import datetime

components_bp = Blueprint('components', __name__, url_prefix='/api/components')


def _parse_date(value, field='日期'):
    """把 YYYY-MM-DD 解析为 date；空值返回 None，格式错误抛 ValueError。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == 'null':
        return None
    try:
        return datetime.strptime(text[:10], '%Y-%m-%d').date()
    except ValueError:
        raise ValueError(f'{field}格式无效，应为 YYYY-MM-DD')


def _date_out(value):
    return value.isoformat() if value else None


def _parse_kind(value):
    """物品类型：空值默认电子元器件，非法值抛 ValueError。

    不静默归一到默认值——用户明确填了不存在的类型，应当告知而不是改写。
    """
    if value in (None, ''):
        return 'electronic'
    raw = str(value).strip().lower()
    if raw not in Item.VALID_KINDS:
        raise ValueError(f'物品类型无效，可选：{"、".join(Item.VALID_KINDS)}')
    return raw


KIND_LABELS = {
    'electronic': '电子元器件',
    'appliance': '家电',
    'furniture': '家具',
    'vehicle': '车辆',
    'other': '其他',
}


def _kind_label(kind):
    return KIND_LABELS.get(kind, kind)


def _float_or_none(value):
    if value in (None, ''):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value):
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _home_fields(item):
    """家庭生命周期属性：与物品类型无关，Web 与 MCP 共用同一批字段。"""
    return {
        'is_consumable': bool(item.is_consumable),
        'consumption_rate': item.consumption_rate,
        'warranty_expiry': _date_out(item.warranty_expiry),
        'maintenance_cycle_days': item.maintenance_cycle_days,
        'last_maintenance_date': _date_out(item.last_maintenance_date),
    }


@components_bp.route('', methods=['GET'])
@login_required
def get_components():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    keyword = request.args.get('keyword', '')
    category_id = request.args.get('category_id', type=int)
    
    query = Item.query

    if keyword:
        # value / package 已迁到 item_specs，走代理属性无法下推到 SQL，必须显式 join
        like = f'%{keyword}%'
        query = query.outerjoin(ItemSpec, ItemSpec.item_id == Item.id).filter(
            db.or_(
                Item.name.like(like),
                Item.brand.like(like),
                ItemSpec.spec_value.like(like),
                ItemSpec.spec_package.like(like),
            )
        )
    
    if category_id:
        query = query.filter(Item.category_id == category_id)
    
    pagination = query.order_by(Item.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    components = []
    for item in pagination.items:
        components.append({
            'id': item.id,
            'kind': item.kind,
            'name': item.name,
            'value': item.value,
            'package': item.package,
            'tolerance': item.tolerance,
            'brand': item.brand,
            'current_stock': item.current_stock,
            'min_stock': item.min_stock,
            'unit': item.unit,
            'category': item.category.name if item.category else None,
            'location': item.location.name if item.location else None,
            'supplier': item.supplier.name if item.supplier else None,
            'created_at': item.created_at.isoformat(),
            **_home_fields(item)
        })
    
    return jsonify({
        'code': 200,
        'message': 'success',
        'data': {
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'items': components
        }
    })

@components_bp.route('/low-stock', methods=['GET'])
@login_required
def get_low_stock():
    components = Item.query.filter(
        Item.current_stock <= Item.min_stock
    ).all()
    
    result = []
    for item in components:
        result.append({
            'id': item.id,
            'name': item.name,
            'value': item.value,
            'current_stock': item.current_stock,
            'min_stock': item.min_stock,
            'unit': item.unit,
            'location': item.location.name if item.location else None
        })
    
    return jsonify({
        'code': 200,
        'message': 'success',
        'data': result
    })

@components_bp.route('/<int:item_id>', methods=['GET'])
@login_required
def get_component(item_id):
    component = Item.query.get(item_id)
    if not component:
        return jsonify({'code': 404, 'message': '物料不存在', 'data': None}), 404
    
    return jsonify({
        'code': 200,
        'message': 'success',
        'data': {
            'id': component.id,
            'kind': component.kind,
            'name': component.name,
            'value': component.value,
            'package': component.package,
            'tolerance': component.tolerance,
            'brand': component.brand,
            'datasheet_url': component.datasheet_url,
            'min_stock': component.min_stock,
            'current_stock': component.current_stock,
            'unit': component.unit,
            'category_id': component.category_id,
            'location_id': component.location_id,
            'supplier_id': component.supplier_id,
            'created_at': component.created_at.isoformat(),
            **_home_fields(component)
        }
    })

@components_bp.route('', methods=['POST'])
@admin_required
def create_component():
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'code': 400, 'message': '物料名称不能为空', 'data': None}), 400

    try:
        warranty_expiry = _parse_date(data.get('warranty_expiry'), '保修到期')
        last_maintenance = _parse_date(data.get('last_maintenance_date'), '上次维护日期')
        kind = _parse_kind(data.get('kind'))
    except ValueError as exc:
        return jsonify({'code': 400, 'message': str(exc), 'data': None}), 400

    component = Item(
        kind=kind,
        name=data['name'],
        value=data.get('value'),
        package=data.get('package'),
        tolerance=data.get('tolerance'),
        brand=data.get('brand'),
        datasheet_url=data.get('datasheet_url'),
        min_stock=data.get('min_stock', 0),
        current_stock=data.get('current_stock', 0),
        unit=data.get('unit', '个'),
        category_id=data.get('category_id'),
        location_id=data.get('location_id'),
        supplier_id=data.get('supplier_id'),
        is_consumable=bool(data.get('is_consumable')),
        consumption_rate=_float_or_none(data.get('consumption_rate')),
        warranty_expiry=warranty_expiry,
        maintenance_cycle_days=_int_or_none(data.get('maintenance_cycle_days')),
        last_maintenance_date=last_maintenance,
    )
    
    db.session.add(component)
    db.session.commit()
    
    return jsonify({
        'code': 200,
        'message': '创建成功',
        'data': {'id': component.id}
    }), 201

@components_bp.route('/<int:item_id>', methods=['PUT'])
@admin_required
def update_component(item_id):
    component = Item.query.get(item_id)
    if not component:
        return jsonify({'code': 404, 'message': '物料不存在', 'data': None}), 404
    
    data = request.get_json()
    if not data:
        return jsonify({'code': 400, 'message': '请求数据不能为空', 'data': None}), 400

    if 'warranty_expiry' in data or 'last_maintenance_date' in data:
        try:
            if 'warranty_expiry' in data:
                component.warranty_expiry = _parse_date(data['warranty_expiry'], '保修到期')
            if 'last_maintenance_date' in data:
                component.last_maintenance_date = _parse_date(
                    data['last_maintenance_date'], '上次维护日期'
                )
        except ValueError as exc:
            return jsonify({'code': 400, 'message': str(exc), 'data': None}), 400

    if 'is_consumable' in data:
        component.is_consumable = bool(data['is_consumable'])
    if 'consumption_rate' in data:
        component.consumption_rate = _float_or_none(data['consumption_rate'])
    if 'maintenance_cycle_days' in data:
        component.maintenance_cycle_days = _int_or_none(data['maintenance_cycle_days'])

    if 'kind' in data:
        try:
            component.kind = _parse_kind(data['kind'])
        except ValueError as exc:
            return jsonify({'code': 400, 'message': str(exc), 'data': None}), 400

    if 'name' in data:
        component.name = data['name']
    if 'value' in data:
        component.value = data['value']
    if 'package' in data:
        component.package = data['package']
    if 'tolerance' in data:
        component.tolerance = data['tolerance']
    if 'brand' in data:
        component.brand = data['brand']
    if 'datasheet_url' in data:
        component.datasheet_url = data['datasheet_url']
    if 'min_stock' in data:
        component.min_stock = data['min_stock']
    if 'unit' in data:
        component.unit = data['unit']
    if 'category_id' in data:
        component.category_id = data['category_id']
    if 'location_id' in data:
        component.location_id = data['location_id']
    if 'supplier_id' in data:
        component.supplier_id = data['supplier_id']
    
    db.session.commit()
    
    return jsonify({
        'code': 200,
        'message': '更新成功',
        'data': None
    })

@components_bp.route('/<int:item_id>', methods=['DELETE'])
@admin_required
def delete_component(item_id):
    component = Item.query.get(item_id)
    if not component:
        return jsonify({'code': 404, 'message': '物料不存在', 'data': None}), 404

    # 有出入库流水时不允许直接删：流水是历史凭证，删物料会让记录失去归属
    txn_count = Transaction.query.filter_by(item_id=item_id).count()
    if txn_count:
        return jsonify({
            'code': 400,
            'message': f'该物品有 {txn_count} 条出入库流水，不能直接删除；请改用停用或先清理流水',
            'data': None,
        }), 400

    # 维护记录随物品一起删除（脱离物品没有意义）；
    # 开支是真花掉的钱，保留但解除关联
    Maintenance.query.filter_by(item_id=item_id).delete()
    Expense.query.filter_by(item_id=item_id).update(
        {'item_id': None}, synchronize_session=False
    )
    db.session.expire(component)
    db.session.delete(component)
    db.session.commit()
    
    return jsonify({
        'code': 200,
        'message': '删除成功',
        'data': None
    })


@components_bp.route('/batch-kind', methods=['POST'])
@admin_required
def batch_update_kind():
    """批量修改物品类型。

    只改 kind，不动扩展表——把电子元器件改成家电时，原 值/封装 信息仍保留在
    item_specs 里，改回 electronic 就能看到。不在这里清空，避免一次误操作把
    手工录入的规格数据抹掉。
    """
    data = request.get_json(silent=True) or {}
    raw_ids = data.get('ids')
    if not isinstance(raw_ids, list) or not raw_ids:
        return jsonify({'code': 400, 'message': '请先选择要修改的物品', 'data': None}), 400
    if len(raw_ids) > 500:
        return jsonify({'code': 400, 'message': '一次最多修改 500 项', 'data': None}), 400

    try:
        kind = _parse_kind(data.get('kind'))
    except ValueError as exc:
        return jsonify({'code': 400, 'message': str(exc), 'data': None}), 400

    ids = []
    for raw in raw_ids:
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            return jsonify({'code': 400, 'message': f'物品 ID 无效：{raw}', 'data': None}), 400

    items = Item.query.filter(Item.id.in_(ids)).all()
    if not items:
        return jsonify({'code': 404, 'message': '选中的物品都不存在', 'data': None}), 404

    changed = 0
    for item in items:
        if item.kind != kind:
            item.kind = kind
            changed += 1
    db.session.commit()

    return jsonify({
        'code': 200,
        'message': f'已将 {len(items)} 项设为{_kind_label(kind)}',
        'data': {
            'kind': kind,
            'matched': len(items),
            'changed': changed,
            'missing': sorted(set(ids) - {item.id for item in items}),
        },
    })