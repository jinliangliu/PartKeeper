from flask import Blueprint, request, jsonify

from models import db, Location
from utils.decorators import login_required, admin_required

locations_bp = Blueprint('locations', __name__, url_prefix='/api/locations')


def _serialize(location):
    return {
        'id': location.id,
        'name': location.name,
        'description': location.description,
    }


@locations_bp.route('', methods=['GET'])
@login_required
def get_locations():
    items = Location.query.order_by(Location.id.asc()).all()
    return jsonify({'code': 200, 'message': 'success', 'data': [_serialize(l) for l in items]})


@locations_bp.route('', methods=['POST'])
@admin_required
def create_location():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'code': 400, 'message': '库位编号不能为空', 'data': None}), 400
    if Location.query.filter_by(name=name).first():
        return jsonify({'code': 400, 'message': '库位已存在', 'data': None}), 400

    location = Location(name=name, description=data.get('description'))
    db.session.add(location)
    db.session.commit()
    return jsonify({'code': 200, 'message': '创建成功', 'data': {'id': location.id}}), 201


@locations_bp.route('/<int:location_id>', methods=['PUT'])
@admin_required
def update_location(location_id):
    location = db.session.get(Location, location_id)
    if not location:
        return jsonify({'code': 404, 'message': '库位不存在', 'data': None}), 404

    data = request.get_json() or {}
    if 'name' in data:
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'code': 400, 'message': '库位编号不能为空', 'data': None}), 400
        exists = Location.query.filter(Location.name == name, Location.id != location_id).first()
        if exists:
            return jsonify({'code': 400, 'message': '库位已存在', 'data': None}), 400
        location.name = name
    if 'description' in data:
        location.description = data.get('description')

    db.session.commit()
    return jsonify({'code': 200, 'message': '更新成功', 'data': None})


@locations_bp.route('/<int:location_id>', methods=['DELETE'])
@admin_required
def delete_location(location_id):
    location = db.session.get(Location, location_id)
    if not location:
        return jsonify({'code': 404, 'message': '库位不存在', 'data': None}), 404
    if location.components:
        return jsonify({'code': 400, 'message': '该库位已被物料引用，无法删除', 'data': None}), 400

    db.session.delete(location)
    db.session.commit()
    return jsonify({'code': 200, 'message': '删除成功', 'data': None})
