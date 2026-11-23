"""物品维护记录的核心逻辑：录入、序列化、按物品汇总账本。

Web 路由与 MCP 工具都走这里，避免「网页能记、对话记出来的字段不一样」这类漂移。

关键设计：维护记录**不存金额**。钱只记在 expenses，录入维护时若带花费就顺手生
成一笔 ``category='maintenance'`` 的开支并双向关联。这样家庭总支出天然包含维修费，
物品账本 = 该物品名下所有开支之和，购置与维修同源，不会两处对不上。
"""
from datetime import datetime, timedelta
import hashlib

from models import Expense, Maintenance, db
from utils.ledger import CHANNELS, MAINTENANCE_ALIASES, MAINTENANCE_LABELS, normalize_channel

TYPE_KEYS = set(Maintenance.VALID_TYPES)
CHANNEL_KEYS = set(CHANNELS)


class MaintenanceError(ValueError):
    """录入维护记录时的可预期错误（由调用方转成 400/错误消息）。"""


def parse_dt(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d', '%Y/%m/%d'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def normalize_type(value):
    """中文别名归一化；无法识别时归入 other 而不是报错（维护方式本来就杂）。"""
    raw = str(value or '').strip()
    if not raw:
        return 'other'
    key = MAINTENANCE_ALIASES.get(raw, raw.lower())
    return key if key in TYPE_KEYS else 'other'


def serialize(record, with_component=False):
    exp = record.expense
    row = {
        'id': record.id,
        'item_id': record.item_id,
        'type': record.type,
        'type_label': MAINTENANCE_LABELS.get(record.type, record.type),
        'title': record.title,
        'performed_at': record.performed_at.strftime('%Y-%m-%d') if record.performed_at else None,
        'vendor': record.vendor,
        'note': record.note,
        'cost': round(float(exp.amount or 0), 2) if exp else 0.0,
        'expense_id': record.expense_id,
        'channel': exp.channel if exp else None,
        'channel_label': dict(CHANNELS).get(exp.channel) if exp else None,
    }
    if with_component:
        row['item_name'] = record.item.name if record.item else None
    return row


def create_record(component, title, performed_at, mtype='other', vendor=None,
                  note=None, cost=0.0, channel=None):
    """创建一条维护记录，必要时生成并关联一笔维修开支。

    返回 ``(record, warnings)``，调用方负责把 warnings 一并回给用户。
    抛 ``MaintenanceError`` 表示输入不合法（此时不会写库）。
    """
    title = str(title or '').strip()
    if not title:
        raise MaintenanceError('请填写本次维护做了什么')

    if not isinstance(performed_at, datetime):
        performed_at = parse_dt(performed_at)
    if not performed_at:
        raise MaintenanceError('performed_at 无效，应为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM')

    try:
        cost = float(cost or 0)
    except (TypeError, ValueError):
        raise MaintenanceError('cost 必须是数字')
    if cost < 0:
        raise MaintenanceError('cost 不能为负数')

    vendor = (str(vendor).strip()[:100] or None) if vendor else None
    record = Maintenance(
        item_id=component.id,
        type=normalize_type(mtype),
        title=title[:120],
        performed_at=performed_at,
        vendor=vendor,
        note=(str(note).strip()[:255] or None) if note else None,
    )
    db.session.add(record)

    warnings = []
    if cost > 0:
        chan = normalize_channel(channel, CHANNEL_KEYS)
        # 维护生成的支出用独立去重键：同物品 + 同日期 + 同金额 视为同一次维修。
        # 刻意不含渠道——手工录维护时渠道经常漏填或记错，按渠道区分会把同一笔
        # 维修记成两笔；而有单号的截图录入走的是 build_dedup_key，渠道语义在
        # 那里才是必要的。
        raw = f"maint|{component.id}|{performed_at.strftime('%Y-%m-%d')}|{round(cost, 2):.2f}"
        key = hashlib.sha256(raw.encode('utf-8')).hexdigest()
        if Expense.query.filter_by(dedup_key=key).first():
            warnings.append(
                f'该物品在 {performed_at.strftime("%Y-%m-%d")} 已有 ¥{round(cost, 2):.2f} 的维修开支，'
                '本次未重复记账；若确实是两次独立维修，请在开支明细里手动补记并调整金额'
            )
        else:
            expense = Expense(
                category='maintenance',
                amount=cost,
                occurred_at=performed_at,
                merchant=vendor,
                channel=chan,
                note=f'{component.name} · {title}'[:255],
                source='maintenance',
                dedup_key=key,
                item_id=component.id,
            )
            db.session.add(expense)
            db.session.flush()
            record.expense_id = expense.id

    # 回写上次维护日期：只往后推，补录旧记录不会把提醒日期拉回去
    performed_day = performed_at.date()
    if not component.last_maintenance_date or performed_day > component.last_maintenance_date:
        component.last_maintenance_date = performed_day

    db.session.commit()
    return record, warnings


def build_ledger(component):
    """单个物品的持有账本。返回可直接 JSON 化的字典。"""
    rows = Expense.query.filter(Expense.item_id == component.id).order_by(
        Expense.occurred_at.asc()
    ).all()

    purchase_rows = [e for e in rows if e.category != 'maintenance']
    service_rows = [e for e in rows if e.category == 'maintenance']
    purchase_total = round(sum(float(e.amount or 0) for e in purchase_rows), 2)
    service_total = round(sum(float(e.amount or 0) for e in service_rows), 2)
    total = round(purchase_total + service_total, 2)

    records = Maintenance.query.filter_by(item_id=component.id).order_by(
        Maintenance.performed_at.desc(), Maintenance.id.desc()
    ).all()

    # 持有天数：优先按首笔开支推算，没有开支则退回建档日
    first_at = rows[0].occurred_at if rows else component.created_at
    days_owned = max((datetime.now() - first_at).days, 1) if first_at else None
    annual_cost = round(total / (days_owned / 365), 2) if days_owned else None

    warranty_days_left = None
    if component.warranty_expiry:
        warranty_days_left = (component.warranty_expiry - datetime.now().date()).days

    next_due, overdue = None, False
    if component.last_maintenance_date and component.maintenance_cycle_days:
        due_date = component.last_maintenance_date + timedelta(
            days=int(component.maintenance_cycle_days)
        )
        next_due = due_date.strftime('%Y-%m-%d')
        overdue = due_date <= datetime.now().date()

    return {
        'item_id': component.id,
        'item_name': component.name,
        'purchase_total': purchase_total,
        'purchase_count': len(purchase_rows),
        'maintenance_total': service_total,
        'maintenance_charged_count': len(service_rows),
        'maintenance_record_count': len(records),
        'total_spent': total,
        'first_expense_at': first_at.strftime('%Y-%m-%d') if first_at else None,
        'days_owned': days_owned,
        'annual_cost': annual_cost,
        'warranty_expiry': component.warranty_expiry.strftime('%Y-%m-%d')
                           if component.warranty_expiry else None,
        'warranty_days_left': warranty_days_left,
        'last_maintenance_date': component.last_maintenance_date.strftime('%Y-%m-%d')
                                 if component.last_maintenance_date else None,
        'maintenance_cycle_days': component.maintenance_cycle_days,
        'next_maintenance_due': next_due,
        'maintenance_overdue': overdue,
        'records': [serialize(m) for m in records[:50]],
    }
