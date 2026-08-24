"""库存过账业务逻辑：入库 / 出库。"""

from models import db, Component, Transaction


class StockError(Exception):
    """库存业务异常，message 可直接返回给前端。"""


def _serialize_transaction(tx):
    return {
        'id': tx.id,
        'component_id': tx.component_id,
        'component_name': tx.component.name if tx.component else None,
        'type': tx.type,
        'quantity': tx.quantity,
        'unit_price': tx.unit_price,
        'operator_id': tx.operator_id,
        'operator_name': tx.operator.username if tx.operator else None,
        'note': tx.note,
        'created_at': tx.created_at.isoformat(),
    }


def post_stock_movement(component_id, movement_type, quantity, operator_id, note='', unit_price=None):
    """对物料执行一次入库或出库，并在同一事务中更新库存、记录流水。

    返回序列化后的流水记录；校验失败时抛出 StockError。
    """
    if movement_type not in ('in', 'out'):
        raise StockError('无效的操作类型')

    if quantity is None:
        raise StockError('数量不能为空')
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        raise StockError('数量必须为正整数')

    if unit_price is not None:
        try:
            unit_price = float(unit_price)
        except (TypeError, ValueError):
            raise StockError('单价格式不正确')
        if unit_price < 0:
            raise StockError('单价不能为负数')
        if movement_type != 'in':
            unit_price = None

    component = db.session.get(Component, component_id)
    if not component:
        raise StockError('物料不存在')

    if movement_type == 'in':
        component.current_stock = (component.current_stock or 0) + quantity
    else:
        if (component.current_stock or 0) < quantity:
            raise StockError(f'库存不足：当前库存 {component.current_stock or 0} {component.unit or "个"}')
        component.current_stock -= quantity

    tx = Transaction(
        component_id=component_id,
        type=movement_type,
        quantity=quantity,
        unit_price=unit_price if movement_type == 'in' else None,
        operator_id=operator_id,
        note=(note or '').strip() or None,
    )
    db.session.add(tx)
    db.session.commit()

    return _serialize_transaction(tx)


def list_transactions(component_id=None, operator_id=None, tx_type=None,
                      start=None, end=None, page=1, per_page=20):
    query = Transaction.query

    if component_id:
        query = query.filter(Transaction.component_id == component_id)
    if operator_id:
        query = query.filter(Transaction.operator_id == operator_id)
    if tx_type in ('in', 'out'):
        query = query.filter(Transaction.type == tx_type)
    if start:
        query = query.filter(Transaction.created_at >= start)
    if end:
        query = query.filter(Transaction.created_at <= end)

    pagination = query.order_by(Transaction.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return {
        'total': pagination.total,
        'page': page,
        'per_page': per_page,
        'items': [_serialize_transaction(tx) for tx in pagination.items],
    }


def post_batch_out(items, operator_id):
    """按明细批量出库：逐行校验库存并在同一事务中扣减、记录流水。"""
    if not items:
        raise StockError('批量出库列表为空')

    transactions = []
    for item in items:
        component_id = item.get('component_id')
        quantity = item.get('quantity')
        note = item.get('note')

        component = db.session.get(Component, component_id)
        if not component:
            raise StockError('存在不存在的物料')
        if quantity is None or isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise StockError(f'物料「{component.name}」数量必须为正整数')
        if (component.current_stock or 0) < quantity:
            raise StockError(
                f'物料「{component.name}」库存不足：当前 {component.current_stock or 0} '
                f'{component.unit or "个"}，需出库 {quantity}'
            )

        component.current_stock -= quantity
        tx = Transaction(
            component_id=component_id,
            type='out',
            quantity=quantity,
            operator_id=operator_id,
            note=(note or '').strip() or None,
        )
        db.session.add(tx)
        transactions.append(tx)

    db.session.commit()
    return {
        'count': len(transactions),
        'items': [_serialize_transaction(tx) for tx in transactions],
    }
