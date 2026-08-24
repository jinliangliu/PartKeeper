"""采购 / 消耗统计与分析业务逻辑。"""

from datetime import datetime

from sqlalchemy import func

from models import db, Component, Transaction, Supplier, Category


def _round(value, ndigits=2):
    return round(float(value or 0), ndigits)


def _range_filter(query, start=None, end=None):
    if start is not None:
        query = query.filter(Transaction.created_at >= start)
    if end is not None:
        query = query.filter(Transaction.created_at <= end)
    return query


def _component_avg_prices():
    """返回 {component_id: 平均采购单价}（全时段，用于估算库存/消耗金额）。"""
    rows = (
        db.session.query(
            Transaction.component_id,
            func.coalesce(func.sum(Transaction.quantity * Transaction.unit_price), 0.0),
            func.coalesce(func.sum(Transaction.quantity), 0),
        )
        .filter(Transaction.type == 'in', Transaction.unit_price.isnot(None))
        .group_by(Transaction.component_id)
        .all()
    )
    result = {}
    for component_id, cost, qty in rows:
        if qty:
            result[component_id] = float(cost) / float(qty)
    return result


def overview(start=None, end=None):
    total_in_qty = _range_filter(
        db.session.query(func.coalesce(func.sum(Transaction.quantity), 0))
        .filter(Transaction.type == 'in'),
        start, end,
    ).scalar()
    total_out_qty = _range_filter(
        db.session.query(func.coalesce(func.sum(Transaction.quantity), 0))
        .filter(Transaction.type == 'out'),
        start, end,
    ).scalar()
    total_in_cost = _range_filter(
        db.session.query(func.coalesce(func.sum(Transaction.quantity * Transaction.unit_price), 0.0))
        .filter(Transaction.type == 'in', Transaction.unit_price.isnot(None)),
        start, end,
    ).scalar()

    total_components = Component.query.count()
    supplier_count = Supplier.query.count()
    category_count = Category.query.count()
    low_stock_count = Component.query.filter(
        Component.current_stock <= Component.min_stock
    ).count()
    inventory_qty = db.session.query(func.coalesce(func.sum(Component.current_stock), 0)).scalar()

    avg_prices = _component_avg_prices()
    inventory_value = 0.0
    for component in Component.query.all():
        price = avg_prices.get(component.id)
        if price:
            inventory_value += (component.current_stock or 0) * price

    return {
        'total_components': total_components,
        'supplier_count': supplier_count,
        'category_count': category_count,
        'low_stock_count': low_stock_count,
        'total_in_qty': int(total_in_qty),
        'total_out_qty': int(total_out_qty),
        'total_in_cost': _round(total_in_cost),
        'inventory_qty': int(inventory_qty),
        'inventory_value': _round(inventory_value),
    }


def purchases_by(group='component', limit=10, start=None, end=None):
    """按组件 / 供应商 / 分类统计采购数量与金额（按金额降序）。"""
    limit = max(1, min(int(limit), 100))

    if group == 'supplier':
        q = (
            db.session.query(
                Supplier.id,
                Supplier.name,
                func.coalesce(func.sum(Transaction.quantity), 0),
                func.coalesce(func.sum(Transaction.quantity * Transaction.unit_price), 0.0),
            )
            .select_from(Transaction)
            .join(Component, Transaction.component_id == Component.id)
            .outerjoin(Supplier, Component.supplier_id == Supplier.id)
            .filter(Transaction.type == 'in')
            .group_by(Supplier.id, Supplier.name)
            .order_by(func.sum(Transaction.quantity * Transaction.unit_price).desc())
            .limit(limit)
        )
        rows = _range_filter(q, start, end).all()
        return [
            {'id': supplier_id, 'name': name or '未指定供应商', 'quantity': int(qty), 'cost': _round(cost)}
            for supplier_id, name, qty, cost in rows
        ]

    if group == 'category':
        q = (
            db.session.query(
                Category.id,
                Category.name,
                func.coalesce(func.sum(Transaction.quantity), 0),
                func.coalesce(func.sum(Transaction.quantity * Transaction.unit_price), 0.0),
            )
            .select_from(Transaction)
            .join(Component, Transaction.component_id == Component.id)
            .outerjoin(Category, Component.category_id == Category.id)
            .filter(Transaction.type == 'in')
            .group_by(Category.id, Category.name)
            .order_by(func.sum(Transaction.quantity * Transaction.unit_price).desc())
            .limit(limit)
        )
        rows = _range_filter(q, start, end).all()
        return [
            {'id': category_id, 'name': name or '未分类', 'quantity': int(qty), 'cost': _round(cost)}
            for category_id, name, qty, cost in rows
        ]

    q = (
        db.session.query(
            Component.id,
            Component.name,
            Component.value,
            func.coalesce(func.sum(Transaction.quantity), 0),
            func.coalesce(func.sum(Transaction.quantity * Transaction.unit_price), 0.0),
        )
        .select_from(Transaction)
        .join(Component, Transaction.component_id == Component.id)
        .filter(Transaction.type == 'in')
        .group_by(Component.id, Component.name, Component.value)
        .order_by(func.sum(Transaction.quantity * Transaction.unit_price).desc())
        .limit(limit)
    )
    rows = _range_filter(q, start, end).all()
    return [
        {
            'id': component_id,
            'name': f'{name}{" " + value if value else ""}',
            'quantity': int(qty),
            'cost': _round(cost),
        }
        for component_id, name, value, qty, cost in rows
    ]


def consumption_by(group='component', limit=10, start=None, end=None):
    """按组件 / 分类统计消耗数量（按数量降序），并估算消耗金额（按平均采购单价）。"""
    limit = max(1, min(int(limit), 100))
    avg_prices = _component_avg_prices()

    if group == 'category':
        q = (
            db.session.query(
                Category.id,
                Category.name,
                func.coalesce(func.sum(Transaction.quantity), 0),
            )
            .select_from(Transaction)
            .join(Component, Transaction.component_id == Component.id)
            .outerjoin(Category, Component.category_id == Category.id)
            .filter(Transaction.type == 'out')
            .group_by(Category.id, Category.name)
            .order_by(func.sum(Transaction.quantity).desc())
            .limit(limit)
        )
        rows = _range_filter(q, start, end).all()
        return [
            {'id': cid, 'name': name or '未分类', 'quantity': int(qty)}
            for cid, name, qty in rows
        ]

    q = (
        db.session.query(
            Component.id,
            Component.name,
            Component.value,
            func.coalesce(func.sum(Transaction.quantity), 0),
        )
        .select_from(Transaction)
        .join(Component, Transaction.component_id == Component.id)
        .filter(Transaction.type == 'out')
        .group_by(Component.id, Component.name, Component.value)
        .order_by(func.sum(Transaction.quantity).desc())
        .limit(limit)
    )
    rows = _range_filter(q, start, end).all()
    result = []
    for component_id, name, value, qty in rows:
        price = avg_prices.get(component_id)
        result.append({
            'id': component_id,
            'name': f'{name}{" " + value if value else ""}',
            'quantity': int(qty),
            'estimated_cost': _round(qty * price) if price else 0.0,
        })
    return result


def _month_buckets(start_dt, end_dt):
    buckets = []
    year, month = start_dt.year, start_dt.month
    while (year, month) <= (end_dt.year, end_dt.month):
        buckets.append((year, month))
        month += 1
        if month == 13:
            month = 1
            year += 1
    return buckets


def monthly_trend(months=12, start=None, end=None):
    """采购 / 消耗逐月趋势（默认最近 N 个月，也可按起止时间）。"""
    months = max(1, min(int(months), 36))
    now = datetime.utcnow()

    if start is None:
        year, month = now.year, now.month
        for _ in range(months - 1):
            month -= 1
            if month == 0:
                month = 12
                year -= 1
        start_dt = datetime(year, month, 1)
    else:
        start_dt = start
    end_dt = end if end is not None else now

    transactions = (
        Transaction.query
        .filter(Transaction.created_at >= start_dt, Transaction.created_at <= end_dt)
        .order_by(Transaction.created_at.asc())
        .all()
    )

    buckets = {}
    for tx in transactions:
        key = tx.created_at.strftime('%Y-%m')
        buckets.setdefault(key, {'in_qty': 0, 'out_qty': 0, 'in_cost': 0.0})
        if tx.type == 'in':
            buckets[key]['in_qty'] += tx.quantity
            if tx.unit_price:
                buckets[key]['in_cost'] += tx.quantity * tx.unit_price
        else:
            buckets[key]['out_qty'] += tx.quantity

    result = []
    for year, month in _month_buckets(start_dt, end_dt):
        key = f'{year:04d}-{month:02d}'
        item = buckets.get(key, {'in_qty': 0, 'out_qty': 0, 'in_cost': 0.0})
        result.append({
            'month': key,
            'in_qty': item['in_qty'],
            'out_qty': item['out_qty'],
            'in_cost': _round(item['in_cost']),
        })
    return result


def export_components(start=None, end=None):
    """导出指定时间范围内，按元件汇总的采购 / 消耗明细（用于 CSV）。"""
    transactions = _range_filter(Transaction.query, start, end).all()
    components = Component.query.order_by(Component.id.asc()).all()
    avg_prices = _component_avg_prices()

    agg = {}
    for tx in transactions:
        a = agg.setdefault(tx.component_id, {'in_qty': 0, 'in_cost': 0.0, 'out_qty': 0})
        if tx.type == 'in':
            a['in_qty'] += tx.quantity
            if tx.unit_price:
                a['in_cost'] += tx.quantity * tx.unit_price
        else:
            a['out_qty'] += tx.quantity

    rows = []
    for c in components:
        a = agg.get(c.id)
        if not a:
            continue
        price = avg_prices.get(c.id)
        rows.append({
            'id': c.id,
            'name': c.name,
            'value': c.value or '',
            'category': c.category.name if c.category else '',
            'supplier': c.supplier.name if c.supplier else '',
            'in_qty': a['in_qty'],
            'in_cost': _round(a['in_cost']),
            'out_qty': a['out_qty'],
            'out_cost': _round(a['out_qty'] * price) if price else 0.0,
        })
    return rows
