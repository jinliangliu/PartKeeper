"""生活缴费（水电煤等）账单的 REST 接口。

与 MCP 的 ``record_utility_bills`` / ``get_utility_spend`` 共用同一套模型与去重键，
写的是同一个 SQLite 库：对话里用截图录入的账单，网页上能核对、能纠错删除。

去重规则见 ``models.UtilityBill.build_dedup_key``——渠道感知，同单号跨渠道不合并。
"""
from datetime import datetime

from flask import Blueprint, jsonify, request
from sqlalchemy import or_

from models import db, UtilityBill
from utils.decorators import login_required
from utils.ledger import UTILITY_CHANNELS, UTILITY_LABELS, normalize_channel

utility_bp = Blueprint('utility_bills', __name__, url_prefix='/api/utility-bills')

_CATEGORY_KEYS = set(UTILITY_LABELS)
_CHANNEL_KEYS = set(UTILITY_CHANNELS)
_GROUP_KEYS = {'category', 'channel', 'counterparty'}


def _ok(data=None, message='success'):
    return jsonify({'code': 200, 'message': message, 'data': data})


def _err(message, code=400):
    return jsonify({'code': code, 'message': message, 'data': None}), code


def _bill_dict(bill):
    return {
        'id': bill.id,
        'category': bill.category,
        'category_label': UTILITY_LABELS.get(bill.category, bill.category),
        'amount': round(float(bill.amount or 0), 2),
        'paid_at': bill.paid_at.strftime('%Y-%m-%d') if bill.paid_at else None,
        'period': bill.period,
        'counterparty': bill.counterparty,
        'channel': bill.channel,
        'channel_label': UTILITY_CHANNELS.get(bill.channel, bill.channel),
        'external_id': bill.external_id,
        'note': bill.note,
        'source': bill.source,
        'created_at': bill.created_at.strftime('%Y-%m-%d %H:%M') if bill.created_at else None,
    }


def _parse_day(value, end_of_day=False):
    if not value:
        return None
    try:
        dt = datetime.strptime(str(value)[:10], '%Y-%m-%d')
    except ValueError:
        return None
    return dt.replace(hour=23, minute=59, second=59) if end_of_day else dt


def _parse_dt(value):
    """接受 YYYY-MM-DD[ HH:MM[:SS]] 与 YYYY/MM/DD。"""
    if not value:
        return None
    text = str(value).strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d', '%Y/%m/%d'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


@utility_bp.route('/meta', methods=['GET'])
@login_required
def get_meta():
    """下拉选项，供前端渲染表单与筛选项。"""
    return _ok({
        'categories': [{'value': k, 'label': v} for k, v in UTILITY_LABELS.items()],
        'channels': [{'value': k, 'label': v} for k, v in UTILITY_CHANNELS.items()],
    })


@utility_bp.route('', methods=['GET'])
@login_required
def list_bills():
    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(max(1, request.args.get('per_page', 20, type=int)), 200)
    category = request.args.get('category', '').strip()
    channel = request.args.get('channel', '').strip()
    keyword = request.args.get('keyword', '').strip()
    period = request.args.get('period', '').strip()

    query = UtilityBill.query
    if category in _CATEGORY_KEYS:
        query = query.filter(UtilityBill.category == category)
    if channel in _CHANNEL_KEYS:
        query = query.filter(UtilityBill.channel == channel)
    if period:
        query = query.filter(UtilityBill.period == period)

    start_dt = _parse_day(request.args.get('start'))
    end_dt = _parse_day(request.args.get('end'), end_of_day=True)
    if start_dt:
        query = query.filter(UtilityBill.paid_at >= start_dt)
    if end_dt:
        query = query.filter(UtilityBill.paid_at <= end_dt)

    if keyword:
        like = f'%{keyword}%'
        query = query.filter(or_(
            UtilityBill.counterparty.like(like),
            UtilityBill.note.like(like),
            UtilityBill.external_id.like(like),
            UtilityBill.period.like(like),
        ))

    total_amount = query.with_entities(
        db.func.coalesce(db.func.sum(UtilityBill.amount), 0)
    ).scalar()
    pagination = query.order_by(
        UtilityBill.paid_at.desc(), UtilityBill.id.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    return _ok({
        'total': pagination.total,
        'page': page,
        'per_page': per_page,
        'sum_amount': round(float(total_amount or 0), 2),
        'items': [_bill_dict(b) for b in pagination.items],
    })


@utility_bp.route('', methods=['POST'])
@login_required
def create_bill():
    body = request.get_json(silent=True) or {}

    category = str(body.get('category') or '').strip()
    if category not in _CATEGORY_KEYS:
        return _err(f'category 无效，可选：{sorted(_CATEGORY_KEYS)}')

    try:
        amount = float(body.get('amount'))
    except (TypeError, ValueError):
        return _err('amount 必须是数字')
    if amount <= 0:
        return _err('amount 必须大于 0')

    paid_at = _parse_dt(body.get('paid_at'))
    if not paid_at:
        return _err('paid_at 无效，应为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM')

    channel = normalize_channel(body.get('channel'), _CHANNEL_KEYS)
    counterparty = str(body.get('counterparty') or '').strip() or None
    external_id = str(body.get('external_id') or '').strip() or None

    key = UtilityBill.build_dedup_key(
        category, amount, paid_at, counterparty, external_id, channel
    )
    existing = UtilityBill.query.filter_by(dedup_key=key).first()
    if existing:
        return _err(
            f'该账单已存在（{existing.paid_at.strftime("%Y-%m-%d")} '
            f'{UTILITY_LABELS.get(existing.category, existing.category)} '
            f'¥{round(float(existing.amount), 2)}）',
            409,
        )

    bill = UtilityBill(
        category=category,
        amount=amount,
        paid_at=paid_at,
        period=str(body.get('period') or '').strip() or None,
        counterparty=counterparty,
        channel=channel,
        external_id=external_id,
        note=str(body.get('note') or '').strip() or None,
        source=str(body.get('source') or 'manual').strip(),
        dedup_key=key,
    )
    db.session.add(bill)
    db.session.commit()
    return _ok(_bill_dict(bill), '已录入')


@utility_bp.route('/<int:bill_id>', methods=['DELETE'])
@login_required
def delete_bill(bill_id):
    bill = UtilityBill.query.get(bill_id)
    if not bill:
        return _err('账单不存在', 404)
    db.session.delete(bill)
    db.session.commit()
    return _ok({'id': bill_id}, '已删除')


@utility_bp.route('/stats', methods=['GET'])
@login_required
def get_stats():
    """统计：区间总额、月度趋势（零填充）、分组排行。"""
    months = min(max(request.args.get('months', 6, type=int), 1), 36)
    group = request.args.get('group', 'category').strip()
    if group not in _GROUP_KEYS:
        group = 'category'

    now = datetime.now()
    year, month = now.year, now.month
    for _ in range(months - 1):
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    start_dt = datetime(year, month, 1)

    rows = UtilityBill.query.filter(
        UtilityBill.paid_at >= start_dt, UtilityBill.paid_at <= now
    ).all()

    monthly_map = {}
    grouped = {}
    for bill in rows:
        key = bill.paid_at.strftime('%Y-%m')
        bucket = monthly_map.setdefault(key, {'amount': 0.0, 'count': 0})
        bucket['amount'] += float(bill.amount or 0)
        bucket['count'] += 1

        if group == 'channel':
            gkey = bill.channel or 'other'
            label = UTILITY_CHANNELS.get(gkey, gkey)
        elif group == 'counterparty':
            gkey = bill.counterparty or '未填写'
            label = gkey
        else:
            gkey = bill.category
            label = UTILITY_LABELS.get(gkey, gkey)
        node = grouped.setdefault(gkey, {'label': label, 'amount': 0.0, 'count': 0})
        node['amount'] += float(bill.amount or 0)
        node['count'] += 1

    monthly = []
    y, m = start_dt.year, start_dt.month
    while (y, m) <= (now.year, now.month):
        label = f'{y:04d}-{m:02d}'
        hit = monthly_map.get(label, {})
        monthly.append({
            'month': label,
            'amount': round(hit.get('amount', 0.0), 2),
            'count': hit.get('count', 0),
        })
        m += 1
        if m == 13:
            m, y = 1, y + 1

    ranking = sorted(
        [{'key': k, 'label': v['label'], 'amount': round(v['amount'], 2),
          'count': v['count']} for k, v in grouped.items()],
        key=lambda x: x['amount'], reverse=True,
    )
    total = round(sum(float(b.amount or 0) for b in rows), 2)
    peak = max(monthly, key=lambda x: x['amount']) if monthly else None

    return _ok({
        'months': months,
        'group': group,
        'total': total,
        'count': len(rows),
        'avg_per_month': round(total / months, 2) if months else 0.0,
        'monthly': monthly,
        'by_group': ranking,
        'peak_month': peak if peak and peak['amount'] > 0 else None,
    })
