from flask import Blueprint, request, jsonify

from models import db, Category
from utils.decorators import login_required, admin_required

categories_bp = Blueprint('categories', __name__, url_prefix='/api/categories')


def _serialize(category):
    return {
        'id': category.id,
        'name': category.name,
        'parent_id': category.parent_id,
        'children': [_serialize(child) for child in category.children],
    }


@categories_bp.route('', methods=['GET'])
@login_required
def get_categories():
    roots = Category.query.filter_by(parent_id=None).order_by(Category.id.asc()).all()
    return jsonify({
        'code': 200,
        'message': 'success',
        'data': [_serialize(c) for c in roots],
    })


@categories_bp.route('', methods=['POST'])
@admin_required
def create_category():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'code': 400, 'message': '分类名称不能为空', 'data': None}), 400

    parent_id = data.get('parent_id')
    if parent_id is not None and db.session.get(Category, parent_id) is None:
        return jsonify({'code': 400, 'message': '父级分类不存在', 'data': None}), 400

    category = Category(name=name, parent_id=parent_id)
    db.session.add(category)
    db.session.commit()
    return jsonify({'code': 200, 'message': '创建成功', 'data': {'id': category.id}}), 201


@categories_bp.route('/<int:category_id>', methods=['PUT'])
@admin_required
def update_category(category_id):
    category = db.session.get(Category, category_id)
    if not category:
        return jsonify({'code': 404, 'message': '分类不存在', 'data': None}), 404

    data = request.get_json() or {}
    if 'name' in data:
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'code': 400, 'message': '分类名称不能为空', 'data': None}), 400
        category.name = name
    if 'parent_id' in data:
        parent_id = data.get('parent_id')
        if parent_id == category_id:
            return jsonify({'code': 400, 'message': '不能将自身设为父级', 'data': None}), 400
        if parent_id is not None and db.session.get(Category, parent_id) is None:
            return jsonify({'code': 400, 'message': '父级分类不存在', 'data': None}), 400
        category.parent_id = parent_id

    db.session.commit()
    return jsonify({'code': 200, 'message': '更新成功', 'data': None})


@categories_bp.route('/<int:category_id>', methods=['DELETE'])
@admin_required
def delete_category(category_id):
    category = db.session.get(Category, category_id)
    if not category:
        return jsonify({'code': 404, 'message': '分类不存在', 'data': None}), 404
    if category.children:
        return jsonify({'code': 400, 'message': '存在子分类，无法删除', 'data': None}), 400
    if category.items:
        return jsonify({'code': 400, 'message': '该分类下存在物料，无法删除', 'data': None}), 400

    db.session.delete(category)
    db.session.commit()
    return jsonify({'code': 200, 'message': '删除成功', 'data': None})
