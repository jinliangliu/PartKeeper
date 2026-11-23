from flask import Blueprint, request, jsonify

from models import db, Supplier
from utils.decorators import login_required, admin_required

suppliers_bp = Blueprint('suppliers', __name__, url_prefix='/api/suppliers')


def _serialize(supplier):
    return {
        'id': supplier.id,
        'name': supplier.name,
        'contact': supplier.contact,
        'phone': supplier.phone,
        'address': supplier.address,
        'website': supplier.website,
    }


@suppliers_bp.route('', methods=['GET'])
@login_required
def get_suppliers():
    keyword = (request.args.get('keyword') or '').strip()
    query = Supplier.query
    if keyword:
        query = query.filter(db.or_(
            Supplier.name.like(f'%{keyword}%'),
            Supplier.contact.like(f'%{keyword}%'),
        ))
    items = query.order_by(Supplier.id.asc()).all()
    return jsonify({'code': 200, 'message': 'success', 'data': [_serialize(s) for s in items]})


@suppliers_bp.route('', methods=['POST'])
@admin_required
def create_supplier():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'code': 400, 'message': '供应商名称不能为空', 'data': None}), 400
    if Supplier.query.filter_by(name=name).first():
        return jsonify({'code': 400, 'message': '供应商已存在', 'data': None}), 400

    supplier = Supplier(
        name=name,
        contact=data.get('contact'),
        phone=data.get('phone'),
        address=data.get('address'),
        website=data.get('website'),
    )
    db.session.add(supplier)
    db.session.commit()
    return jsonify({'code': 200, 'message': '创建成功', 'data': {'id': supplier.id}}), 201


@suppliers_bp.route('/<int:supplier_id>', methods=['PUT'])
@admin_required
def update_supplier(supplier_id):
    supplier = db.session.get(Supplier, supplier_id)
    if not supplier:
        return jsonify({'code': 404, 'message': '供应商不存在', 'data': None}), 404

    data = request.get_json() or {}
    if 'name' in data:
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'code': 400, 'message': '供应商名称不能为空', 'data': None}), 400
        exists = Supplier.query.filter(Supplier.name == name, Supplier.id != supplier_id).first()
        if exists:
            return jsonify({'code': 400, 'message': '供应商已存在', 'data': None}), 400
        supplier.name = name
    for field in ('contact', 'phone', 'address', 'website'):
        if field in data:
            setattr(supplier, field, data.get(field))

    db.session.commit()
    return jsonify({'code': 200, 'message': '更新成功', 'data': None})


@suppliers_bp.route('/<int:supplier_id>', methods=['DELETE'])
@admin_required
def delete_supplier(supplier_id):
    supplier = db.session.get(Supplier, supplier_id)
    if not supplier:
        return jsonify({'code': 404, 'message': '供应商不存在', 'data': None}), 404
    if supplier.items:
        return jsonify({'code': 400, 'message': '该供应商已被物料引用，无法删除', 'data': None}), 400

    db.session.delete(supplier)
    db.session.commit()
    return jsonify({'code': 200, 'message': '删除成功', 'data': None})
