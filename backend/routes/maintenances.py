"""物品维护记录的 REST 接口，以及按物品汇总的「持有账本」。

核心逻辑在 ``services.maintenance_service``：录入维护时若带花费，会顺手生成一笔
维修类开支并双向关联，同时回写物品的「上次维护日期」——否则维护提醒永远停在建档日。
"""
from flask import Blueprint, jsonify, request
from sqlalchemy import or_

from models import Component, Maintenance, db
from services import maintenance_service
from utils.decorators import login_required
from utils.ledger import CHANNELS, MAINTENANCE_LABELS

maintenances_bp = Blueprint('maintenances', __name__, url_prefix='/api/maintenances')

TYPE_KEYS = maintenance_service.TYPE_KEYS


def _ok(data=None, message='success'):
    return jsonify({'code': 200, 'message': message, 'data': data})


def _err(message, code=400):
    return jsonify({'code': code, 'message': message, 'data': None}), code


@maintenances_bp.route('/meta', methods=['GET'])
@login_required
def get_meta():
    return _ok({
        'types': [{'value': k, 'label': v} for k, v in MAINTENANCE_LABELS.items()],
        'channels': [{'value': k, 'label': v} for k, v in CHANNELS.items()],
    })


@maintenances_bp.route('', methods=['GET'])
@login_required
def list_maintenances():
    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(max(1, request.args.get('per_page', 20, type=int)), 200)
    component_id = request.args.get('component_id', type=int)
    mtype = request.args.get('type', '').strip()
    keyword = request.args.get('keyword', '').strip()

    query = Maintenance.query
    if component_id:
        query = query.filter(Maintenance.component_id == component_id)
    if mtype in TYPE_KEYS:
        query = query.filter(Maintenance.type == mtype)
    start_dt = maintenance_service.parse_dt(request.args.get('start'))
    end_dt = maintenance_service.parse_dt(request.args.get('end'))
    if end_dt:
        end_dt = end_dt.replace(hour=23, minute=59, second=59)
    if start_dt:
        query = query.filter(Maintenance.performed_at >= start_dt)
    if end_dt:
        query = query.filter(Maintenance.performed_at <= end_dt)
    if keyword:
        like = f'%{keyword}%'
        query = query.filter(or_(
            Maintenance.title.like(like),
            Maintenance.vendor.like(like),
            Maintenance.note.like(like),
        ))

    pagination = query.order_by(
        Maintenance.performed_at.desc(), Maintenance.id.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    return _ok({
        'total': pagination.total,
        'page': page,
        'per_page': per_page,
        'items': [maintenance_service.serialize(m, with_component=True)
                  for m in pagination.items],
    })


@maintenances_bp.route('', methods=['POST'])
@login_required
def create_maintenance():
    body = request.get_json(silent=True) or {}
    try:
        component_id = int(body.get('component_id'))
    except (TypeError, ValueError):
        return _err('component_id 必填且必须是整数')
    component = db.session.get(Component, component_id)
    if not component:
        return _err(f'物品 ID {component_id} 不存在', 404)

    try:
        record, warnings = maintenance_service.create_record(
            component,
            title=body.get('title'),
            performed_at=body.get('performed_at') or body.get('date'),
            mtype=body.get('type'),
            vendor=body.get('vendor'),
            note=body.get('note'),
            cost=body.get('cost') or 0,
            channel=body.get('channel'),
        )
    except maintenance_service.MaintenanceError as exc:
        return _err(str(exc))

    data = maintenance_service.serialize(record, with_component=True)
    if warnings:
        data['warnings'] = warnings
    return _ok(data, '已记录')


@maintenances_bp.route('/<int:maintenance_id>', methods=['DELETE'])
@login_required
def delete_maintenance(maintenance_id):
    """删除维护记录。默认保留关联开支（钱确实花了），``?delete_expense=1`` 时一并删除。"""
    record = db.session.get(Maintenance, maintenance_id)
    if not record:
        return _err('维护记录不存在', 404)

    expense = record.expense
    drop_expense = request.args.get('delete_expense') in ('1', 'true', 'yes')
    payload = {'id': maintenance_id, 'expense_deleted': False, 'expense_kept': bool(expense)}

    record.expense_id = None
    db.session.delete(record)
    if expense and drop_expense:
        db.session.delete(expense)
        payload['expense_deleted'] = True
        payload['expense_kept'] = False
    db.session.commit()
    return _ok(payload, '已删除')


@maintenances_bp.route('/ledger/<int:component_id>', methods=['GET'])
@login_required
def get_component_ledger(component_id):
    """单个物品的持有账本：花过多少钱、修过几次、保修还剩多久、年均成本。

    购置与维修金额同源于 expenses，不会重复计算；没有登记过开支的物品只显示维护次数。
    """
    component = db.session.get(Component, component_id)
    if not component:
        return _err(f'物品 ID {component_id} 不存在', 404)
    return _ok(maintenance_service.build_ledger(component))
