from flask import Blueprint, request, jsonify
from models import db, Component, Category, Supplier, Location, Transaction
from utils.decorators import login_required, admin_required
from datetime import datetime

components_bp = Blueprint('components', __name__, url_prefix='/api/components')

@components_bp.route('', methods=['GET'])
@login_required
def get_components():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    keyword = request.args.get('keyword', '')
    category_id = request.args.get('category_id', type=int)
    
    query = Component.query
    
    if keyword:
        query = query.filter(
            db.or_(
                Component.name.like(f'%{keyword}%'),
                Component.value.like(f'%{keyword}%'),
                Component.package.like(f'%{keyword}%'),
                Component.brand.like(f'%{keyword}%')
            )
        )
    
    if category_id:
        query = query.filter(Component.category_id == category_id)
    
    pagination = query.order_by(Component.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    components = []
    for item in pagination.items:
        components.append({
            'id': item.id,
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
            'created_at': item.created_at.isoformat()
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
    components = Component.query.filter(
        Component.current_stock <= Component.min_stock
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

@components_bp.route('/<int:component_id>', methods=['GET'])
@login_required
def get_component(component_id):
    component = Component.query.get(component_id)
    if not component:
        return jsonify({'code': 404, 'message': '物料不存在', 'data': None}), 404
    
    return jsonify({
        'code': 200,
        'message': 'success',
        'data': {
            'id': component.id,
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
            'created_at': component.created_at.isoformat()
        }
    })

@components_bp.route('', methods=['POST'])
@admin_required
def create_component():
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'code': 400, 'message': '物料名称不能为空', 'data': None}), 400
    
    component = Component(
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
        supplier_id=data.get('supplier_id')
    )
    
    db.session.add(component)
    db.session.commit()
    
    return jsonify({
        'code': 200,
        'message': '创建成功',
        'data': {'id': component.id}
    }), 201

@components_bp.route('/<int:component_id>', methods=['PUT'])
@admin_required
def update_component(component_id):
    component = Component.query.get(component_id)
    if not component:
        return jsonify({'code': 404, 'message': '物料不存在', 'data': None}), 404
    
    data = request.get_json()
    if not data:
        return jsonify({'code': 400, 'message': '请求数据不能为空', 'data': None}), 400
    
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

@components_bp.route('/<int:component_id>', methods=['DELETE'])
@admin_required
def delete_component(component_id):
    component = Component.query.get(component_id)
    if not component:
        return jsonify({'code': 404, 'message': '物料不存在', 'data': None}), 404
    
    db.session.delete(component)
    db.session.commit()
    
    return jsonify({
        'code': 200,
        'message': '删除成功',
        'data': None
    })