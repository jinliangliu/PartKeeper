"""家庭开支与凭证附件的 REST 接口。

与 MCP 工具共用同一套模型与服务层，写的是同一个 SQLite 库，所以对话录入的开支
在这里能看到，网页上传的凭证对话里也能看到。

凭证上传的安全处理全部委托给 ``services.receipt_service``：格式白名单、
10MB 上限、EXIF/GPS 剥离、按内容哈希落盘、越界路径防护。
"""
import os
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request, send_file
from sqlalchemy import or_

from models import Item, Expense, ExpenseAttachment, db
from services import receipt_service
from utils.decorators import admin_required, login_required
from utils.ledger import CHANNELS as _CHANNELS, EXPENSE_LABELS as _LABELS

expenses_bp = Blueprint('expenses', __name__, url_prefix='/api/expenses')

# 类型与渠道的中文标签统一由 utils.ledger 维护，改一处即全局生效
CATEGORIES = list(_LABELS.items())
CHANNELS = list(_CHANNELS.items())
_CATEGORY_KEYS = {k for k, _ in CATEGORIES}
_CHANNEL_KEYS = {k for k, _ in CHANNELS}


def _ok(data=None, message='success'):
    return jsonify({'code': 200, 'message': message, 'data': data})


def _err(message, code=400):
    return jsonify({'code': code, 'message': message, 'data': None}), code


def _upload_dir():
    return current_app.config['UPLOAD_DIR']


def _att_dict(att):
    return {
        'id': att.id,
        'sha256': att.sha256,
        'size_bytes': att.size_bytes,
        'mime': att.mime,
        'url': f'/api/expenses/attachments/{att.id}/file',
    }


def _expense_dict(exp, attachments=None):
    return {
        'id': exp.id,
        'category': exp.category,
        'category_label': _LABELS.get(exp.category, exp.category),
        'subcategory': exp.subcategory,
        'amount': round(float(exp.amount or 0), 2),
        'occurred_at': exp.occurred_at.strftime('%Y-%m-%d') if exp.occurred_at else None,
        'merchant': exp.merchant,
        'channel': exp.channel,
        'channel_label': dict(CHANNELS).get(exp.channel, exp.channel),
        'external_id': exp.external_id,
        'note': exp.note,
        'tags': [t for t in (exp.tags or '').split(',') if t],
        'currency': exp.currency or 'CNY',
        'item_id': exp.item_id,
        'item_name': exp.item.name if exp.item else None,
        'attachments': [_att_dict(a) for a in (attachments or [])],
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
    if not value:
        return None
    text = str(value).strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d', '%Y/%m/%d'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _resolve_component(raw):
    """校验并归一化「关联物品」。返回 (item_id, None) 或 (None, 错误响应)。

    空值、0、null 都视为不关联——生活开支大多数与具体物品无关。
    """
    if raw in (None, '', 0, '0'):
        return None, None
    try:
        cid = int(raw)
    except (TypeError, ValueError):
        return None, _err('item_id 必须是整数')
    if not db.session.get(Item, cid):
        return None, _err(f'物品 ID {cid} 不存在', 404)
    return cid, None


@expenses_bp.route('/meta', methods=['GET'])
@login_required
def get_meta():
    """下拉选项与上传限制，供前端渲染表单。"""
    return _ok({
        'categories': [{'value': k, 'label': v} for k, v in CATEGORIES],
        'channels': [{'value': k, 'label': v} for k, v in CHANNELS],
        'max_upload_mb': receipt_service.MAX_BYTES // 1024 // 1024,
        'allowed_image_formats': ['jpg', 'png', 'webp'],
    })


@expenses_bp.route('', methods=['GET'])
@login_required
def list_expenses():
    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(max(1, request.args.get('per_page', 20, type=int)), 200)
    category = request.args.get('category', '').strip()
    channel = request.args.get('channel', '').strip()
    merchant = request.args.get('merchant', '').strip()
    keyword = request.args.get('keyword', '').strip()

    query = Expense.query
    if category in _CATEGORY_KEYS:
        query = query.filter(Expense.category == category)
    if channel in _CHANNEL_KEYS:
        query = query.filter(Expense.channel == channel)
    item_id = request.args.get('item_id', type=int) or request.args.get('component_id', type=int)
    if item_id:
        query = query.filter(Expense.item_id == item_id)
    if merchant:
        query = query.filter(Expense.merchant.like(f'%{merchant}%'))
    start_dt = _parse_day(request.args.get('start'))
    end_dt = _parse_day(request.args.get('end'), end_of_day=True)
    if start_dt:
        query = query.filter(Expense.occurred_at >= start_dt)
    if end_dt:
        query = query.filter(Expense.occurred_at <= end_dt)
    if keyword:
        like = f'%{keyword}%'
        query = query.filter(or_(
            Expense.note.like(like),
            Expense.merchant.like(like),
            Expense.subcategory.like(like),
            Expense.tags.like(like),
        ))

    total_amount = query.with_entities(db.func.coalesce(db.func.sum(Expense.amount), 0)).scalar()
    pagination = query.options(db.joinedload(Expense.item)).order_by(
        Expense.occurred_at.desc(), Expense.id.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    ids = [e.id for e in pagination.items]
    att_map = {}
    if ids:
        for att in ExpenseAttachment.query.filter(ExpenseAttachment.expense_id.in_(ids)).all():
            att_map.setdefault(att.expense_id, []).append(att)

    return _ok({
        'total': pagination.total,
        'page': page,
        'per_page': per_page,
        'sum_amount': round(float(total_amount or 0), 2),
        'items': [_expense_dict(e, att_map.get(e.id, [])) for e in pagination.items],
    })


@expenses_bp.route('', methods=['POST'])
@login_required
def create_expense():
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
    occurred_at = _parse_dt(body.get('occurred_at') or body.get('paid_at'))
    if not occurred_at:
        return _err('occurred_at 无效，应为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM')

    channel = str(body.get('channel') or 'other').strip()
    if channel not in _CHANNEL_KEYS:
        channel = 'other'
    external_id = str(body.get('external_id') or '').strip() or None
    merchant = str(body.get('merchant') or '').strip() or None

    tags = body.get('tags')
    if isinstance(tags, (list, tuple)):
        tags = ','.join(str(t).strip() for t in tags if str(t).strip())
    tags = (str(tags).replace('，', ',').replace('、', ',') if tags else '') or None

    key = Expense.build_dedup_key(category, amount, occurred_at, merchant, external_id, channel)
    if Expense.query.filter_by(dedup_key=key).first():
        return _err('该开支已存在（同渠道同单号，或同渠道同日同类型同金额同商户）', 409)

    item_id, err = _resolve_component(body.get('item_id') or body.get('component_id'))
    if err:
        return err

    exp = Expense(
        category=category,
        subcategory=str(body.get('subcategory') or '').strip() or None,
        amount=amount,
        occurred_at=occurred_at,
        merchant=merchant,
        channel=channel,
        external_id=external_id,
        note=str(body.get('note') or '').strip() or None,
        tags=tags,
        currency=str(body.get('currency') or 'CNY').strip().upper()[:8],
        source=str(body.get('source') or 'manual').strip(),
        dedup_key=key,
        item_id=item_id,
    )
    db.session.add(exp)
    db.session.commit()
    return _ok(_expense_dict(exp, []), '已创建')


@expenses_bp.route('/<int:expense_id>', methods=['GET'])
@login_required
def get_expense(expense_id):
    """单条详情（含凭证），供凭证弹窗刷新用。"""
    exp = Expense.query.get(expense_id)
    if not exp:
        return _err('开支不存在', 404)
    atts = ExpenseAttachment.query.filter_by(expense_id=expense_id).all()
    return _ok(_expense_dict(exp, atts))


@expenses_bp.route('/<int:expense_id>', methods=['DELETE'])
@login_required
def delete_expense(expense_id):
    exp = Expense.query.get(expense_id)
    if not exp:
        return _err('开支不存在', 404)
    att_count = ExpenseAttachment.query.filter_by(expense_id=expense_id).count()
    db.session.delete(exp)
    db.session.commit()
    return _ok({'id': expense_id, 'attachment_rows_removed': att_count},
               '已删除（凭证文件保留在磁盘，可用 gc 清理孤儿文件）')


@expenses_bp.route('/<int:expense_id>/component', methods=['PUT'])
@login_required
def set_expense_component(expense_id):
    """调整开支关联的物品。传 item_id=null/0 表示取消关联。

    单独开这个接口，是为了让已经录过的开支也能补挂到物品上（逐字段 PATCH 语义），
    不必重新提交整条记录而触发去重键重算。
    """
    exp = db.session.get(Expense, expense_id)
    if not exp:
        return _err('开支不存在', 404)
    body = request.get_json(silent=True) or {}
    item_id, err = _resolve_component(body.get('item_id') or body.get('component_id'))
    if err:
        return err
    exp.item_id = item_id
    db.session.commit()
    return _ok(_expense_dict(exp, exp.attachments), '已更新')


@expenses_bp.route('/stats', methods=['GET'])
@login_required
def get_stats():
    """开支统计：总额、月度趋势（零填充）、类型排行。供页面图表使用。

    MCP 侧的 ``get_expense_spend`` 提供更细的分组维度，两者读同一批数据。
    """
    months = min(max(request.args.get('months', 6, type=int), 1), 36)
    now = datetime.now()
    year, month = now.year, now.month
    for _ in range(months - 1):
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    start_dt = datetime(year, month, 1)

    rows = Expense.query.filter(
        Expense.occurred_at >= start_dt, Expense.occurred_at <= now
    ).all()

    monthly_map = {}
    by_category = {}
    for exp in rows:
        key = exp.occurred_at.strftime('%Y-%m')
        bucket = monthly_map.setdefault(key, {'amount': 0.0, 'count': 0})
        bucket['amount'] += float(exp.amount or 0)
        bucket['count'] += 1
        node = by_category.setdefault(exp.category, {'amount': 0.0, 'count': 0})
        node['amount'] += float(exp.amount or 0)
        node['count'] += 1

    monthly = []
    y, m = start_dt.year, start_dt.month
    while (y, m) <= (now.year, now.month):
        label = f'{y:04d}-{m:02d}'
        monthly.append({'month': label, 'amount': round(monthly_map.get(label, {}).get('amount', 0.0), 2),
                        'count': monthly_map.get(label, {}).get('count', 0)})
        m += 1
        if m == 13:
            m, y = 1, y + 1

    categories = sorted(
        [{'category': k, 'label': _LABELS.get(k, k), 'amount': round(v['amount'], 2),
          'count': v['count']} for k, v in by_category.items()],
        key=lambda x: x['amount'], reverse=True,
    )
    total = round(sum(float(e.amount or 0) for e in rows), 2)
    return _ok({
        'months': months,
        'total': total,
        'count': len(rows),
        'avg_per_month': round(total / months, 2) if months else 0.0,
        'monthly': monthly,
        'by_category': categories,
    })


@expenses_bp.route('/<int:expense_id>/attachments', methods=['POST'])
@login_required
def upload_attachment(expense_id):
    """上传凭证图片（multipart/form-data，字段名 file）。"""
    exp = Expense.query.get(expense_id)
    if not exp:
        return _err('开支不存在', 404)
    upload = request.files.get('file')
    if upload is None or not upload.filename:
        return _err('请选择要上传的图片（字段名 file）')

    try:
        meta = receipt_service.save_receipt(upload.stream, _upload_dir())
    except receipt_service.ReceiptError as exc:
        return _err(str(exc))
    except OSError as exc:
        current_app.logger.exception('凭证写入失败')
        return _err(f'凭证保存失败：{exc}', 500)

    existing = ExpenseAttachment.query.filter_by(
        expense_id=expense_id, sha256=meta['sha256']
    ).first()
    if existing:
        return _ok({'attachment': _att_dict(existing), 'deduplicated': True},
                   '该凭证已存在')

    att = ExpenseAttachment(
        expense_id=expense_id,
        file_path=meta['rel_path'],
        sha256=meta['sha256'],
        size_bytes=meta['size_bytes'],
        mime=meta['mime'],
    )
    db.session.add(att)
    db.session.commit()
    return _ok({'attachment': _att_dict(att), 'deduplicated': meta['deduplicated']}, '已上传')


@expenses_bp.route('/attachments/<int:attachment_id>/file', methods=['GET'])
@login_required
def get_attachment_file(attachment_id):
    """读取凭证图片。走鉴权接口而非静态目录，避免链接外泄后任意人可访问。

    传 ``?size=160`` 返回等比缩略图（列表页用），不传则返回原图。
    """
    att = ExpenseAttachment.query.get(attachment_id)
    if not att:
        return _err('凭证不存在', 404)

    if request.args.get('size'):
        thumb = receipt_service.make_thumbnail(
            _upload_dir(), att.file_path, request.args.get('size', type=int)
        )
        if thumb:
            response = send_file(thumb, mimetype='image/jpeg', conditional=True)
            # 缩略图按哈希命名、内容不可变，可以放心长缓存
            response.headers['Cache-Control'] = 'private, max-age=86400'
            return response
        # 缩略图生成失败（源文件损坏等）时回落到原图，不让列表直接空掉

    abs_path = receipt_service.resolve_stored_path(_upload_dir(), att.file_path)
    if not abs_path:
        return _err('凭证文件缺失（可能已被清理）', 404)
    response = send_file(abs_path, mimetype=att.mime or 'application/octet-stream',
                         download_name=os.path.basename(abs_path), conditional=True)
    # 私有缓存：允许浏览器短期缓存，但不许中间代理存储
    response.headers['Cache-Control'] = 'private, max-age=600'
    return response


@expenses_bp.route('/attachments/<int:attachment_id>', methods=['DELETE'])
@login_required
def delete_attachment(attachment_id):
    """删除凭证记录。默认保留磁盘文件；``?purge_file=1`` 且无其他记录引用时一并删文件。"""
    att = ExpenseAttachment.query.get(attachment_id)
    if not att:
        return _err('凭证不存在', 404)
    rel_path, sha = att.file_path, att.sha256
    db.session.delete(att)
    db.session.commit()

    purged = False
    if request.args.get('purge_file') in ('1', 'true', 'yes'):
        still_used = ExpenseAttachment.query.filter_by(sha256=sha).first()
        if not still_used:
            purged = receipt_service.remove_stored_file(_upload_dir(), rel_path)
    return _ok({'id': attachment_id, 'file_purged': purged}, '已删除')


@expenses_bp.route('/attachments/gc', methods=['POST'])
@admin_required
def gc_attachments():
    """清理孤儿凭证文件：磁盘上存在但库中无任何记录引用的图片。

    需显式传 ``{"confirm": true}``，避免误触发。删除不可恢复，先算后删。
    """
    body = request.get_json(silent=True) or {}
    if not body.get('confirm'):
        return _err('该操作会删除磁盘文件，请传 {"confirm": true} 明确确认')

    root = os.path.realpath(_upload_dir())
    if not os.path.isdir(root):
        return _ok({'scanned': 0, 'removed': 0})

    referenced = {row[0] for row in db.session.query(ExpenseAttachment.sha256).distinct()}
    scanned, removed, freed = 0, 0, 0
    for dirpath, dirnames, filenames in os.walk(root):
        # 缩略图缓存以原图哈希命名（<sha>_<size>.jpg），不在 referenced 里，
        # 不跳过会被整批误删；它们可随时重建，无需参与引用统计
        dirnames[:] = [d for d in dirnames if d != receipt_service.THUMB_DIRNAME]
        for name in filenames:
            if name.endswith('.tmp'):
                continue
            abs_path = os.path.join(dirpath, name)
            scanned += 1
            stem = os.path.splitext(name)[0]
            if stem in referenced:
                continue
            try:
                size = os.path.getsize(abs_path)
                os.remove(abs_path)
                removed += 1
                freed += size
            except OSError:
                current_app.logger.warning('清理孤儿凭证失败: %s', abs_path)

    return _ok({'scanned': scanned, 'removed': removed, 'freed_bytes': freed},
               f'已清理 {removed} 个孤儿文件')
