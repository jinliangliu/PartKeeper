from flask import Blueprint, request, jsonify

from models import db, Bom, BomItem, Component
from utils.decorators import login_required, admin_required

boms_bp = Blueprint('boms', __name__, url_prefix='/api/boms')


def _serialize_bom(bom, with_items=False):
    data = {
        'id': bom.id,
        'name': bom.name,
        'description': bom.description,
        'item_count': len(bom.items),
        'created_at': bom.created_at.isoformat() if bom.created_at else None,
    }
    if with_items:
        data['items'] = [_serialize_item(item) for item in bom.items]
    return data


def _serialize_item(item):
    component = item.component
    return {
        'id': item.id,
        'component_id': item.component_id,
        'component_name': component.name if component else None,
        'value': component.value if component else None,
        'package': component.package if component else None,
        'current_stock': component.current_stock if component else 0,
        'unit': component.unit if component else '个',
        'quantity': item.quantity,
    }


def _validate_items(items):
    """校验并返回 BomItem 对象列表；失败抛出 ValueError。"""
    if not isinstance(items, list):
        raise ValueError('明细格式不正确')
    result = []
    for it in items:
        component_id = it.get('component_id')
        quantity = it.get('quantity', 1)
        component = db.session.get(Component, component_id)
        if not component:
            raise ValueError('存在不存在的物料')
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError(f'物料「{component.name}」数量必须为正整数')
        result.append(BomItem(component_id=component_id, quantity=quantity))
    return result


@boms_bp.route('', methods=['GET'])
@login_required
def get_boms():
    boms = Bom.query.order_by(Bom.id.desc()).all()
    return jsonify({'code': 200, 'message': 'success', 'data': [_serialize_bom(b) for b in boms]})


@boms_bp.route('', methods=['POST'])
@admin_required
def create_bom():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'code': 400, 'message': 'BOM 名称不能为空', 'data': None}), 400

    bom = Bom(name=name, description=(data.get('description') or '').strip() or None)
    try:
        bom.items = _validate_items(data.get('items', []))
    except ValueError as exc:
        return jsonify({'code': 400, 'message': str(exc), 'data': None}), 400

    db.session.add(bom)
    db.session.commit()
    return jsonify({'code': 200, 'message': '创建成功', 'data': {'id': bom.id}}), 201


@boms_bp.route('/<int:bom_id>', methods=['GET'])
@login_required
def get_bom(bom_id):
    bom = db.session.get(Bom, bom_id)
    if not bom:
        return jsonify({'code': 404, 'message': 'BOM 不存在', 'data': None}), 404
    return jsonify({'code': 200, 'message': 'success', 'data': _serialize_bom(bom, with_items=True)})


@boms_bp.route('/<int:bom_id>', methods=['PUT'])
@admin_required
def update_bom(bom_id):
    bom = db.session.get(Bom, bom_id)
    if not bom:
        return jsonify({'code': 404, 'message': 'BOM 不存在', 'data': None}), 404

    data = request.get_json() or {}
    if 'name' in data:
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'code': 400, 'message': 'BOM 名称不能为空', 'data': None}), 400
        bom.name = name
    if 'description' in data:
        bom.description = (data.get('description') or '').strip() or None

    db.session.commit()
    return jsonify({'code': 200, 'message': '更新成功', 'data': _serialize_bom(bom)})


@boms_bp.route('/<int:bom_id>', methods=['DELETE'])
@admin_required
def delete_bom(bom_id):
    bom = db.session.get(Bom, bom_id)
    if not bom:
        return jsonify({'code': 404, 'message': 'BOM 不存在', 'data': None}), 404

    db.session.delete(bom)
    db.session.commit()
    return jsonify({'code': 200, 'message': '删除成功', 'data': None})


@boms_bp.route('/<int:bom_id>/items', methods=['PUT'])
@admin_required
def replace_items(bom_id):
    bom = db.session.get(Bom, bom_id)
    if not bom:
        return jsonify({'code': 404, 'message': 'BOM 不存在', 'data': None}), 404

    data = request.get_json() or {}
    try:
        new_items = _validate_items(data.get('items', []))
    except ValueError as exc:
        return jsonify({'code': 400, 'message': str(exc), 'data': None}), 400

    bom.items = []
    for item in new_items:
        bom.items.append(item)
    db.session.commit()

    return jsonify({'code': 200, 'message': '保存成功', 'data': _serialize_bom(bom, with_items=True)})
