from datetime import datetime

from flask import Blueprint, request, jsonify

from services.transaction_service import post_stock_movement, post_batch_out, list_transactions, StockError
from utils.decorators import login_required

transactions_bp = Blueprint('transactions', __name__, url_prefix='/api/transactions')


def _parse_date(value, end_of_day=False):
    if not value:
        return None
    try:
        dt = datetime.strptime(value, '%Y-%m-%d')
        if end_of_day:
            return dt.replace(hour=23, minute=59, second=59)
        return dt
    except ValueError:
        return None


@transactions_bp.route('/in', methods=['POST'])
@login_required
def stock_in():
    data = request.get_json() or {}
    try:
        tx = post_stock_movement(
            item_id=data.get('item_id') or data.get('component_id'),
            movement_type='in',
            quantity=data.get('quantity'),
            operator_id=request.current_user.get('user_id'),
            note=data.get('note'),
            unit_price=data.get('unit_price'),
        )
    except StockError as exc:
        return jsonify({'code': 400, 'message': str(exc), 'data': None}), 400
    return jsonify({'code': 200, 'message': '入库成功', 'data': tx}), 201


@transactions_bp.route('/out', methods=['POST'])
@login_required
def stock_out():
    data = request.get_json() or {}
    try:
        tx = post_stock_movement(
            item_id=data.get('item_id') or data.get('component_id'),
            movement_type='out',
            quantity=data.get('quantity'),
            operator_id=request.current_user.get('user_id'),
            note=data.get('note'),
        )
    except StockError as exc:
        return jsonify({'code': 400, 'message': str(exc), 'data': None}), 400
    return jsonify({'code': 200, 'message': '出库成功', 'data': tx}), 201


@transactions_bp.route('/out-batch', methods=['POST'])
@login_required
def stock_out_batch():
    data = request.get_json() or {}
    items = data.get('items')
    try:
        result = post_batch_out(items, operator_id=request.current_user.get('user_id'))
    except StockError as exc:
        return jsonify({'code': 400, 'message': str(exc), 'data': None}), 400
    return jsonify({'code': 200, 'message': '批量出库成功', 'data': result}), 201


@transactions_bp.route('', methods=['GET'])
@login_required
def get_transactions():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    # component_id 为旧字段名，保留兼容；新代码统一用 item_id
    item_id = request.args.get('item_id', type=int) or request.args.get('component_id', type=int)
    operator_id = request.args.get('operator_id', type=int)
    tx_type = request.args.get('type')
    start = _parse_date(request.args.get('start'))
    end = _parse_date(request.args.get('end'), end_of_day=True)

    data = list_transactions(
        item_id=item_id,
        operator_id=operator_id,
        tx_type=tx_type,
        start=start,
        end=end,
        page=page,
        per_page=per_page,
    )
    return jsonify({'code': 200, 'message': 'success', 'data': data})
