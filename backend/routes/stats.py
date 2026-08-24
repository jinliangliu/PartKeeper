import csv
import io
from datetime import datetime

from flask import Blueprint, request, jsonify, Response

from services import stats_service
from utils.decorators import login_required

stats_bp = Blueprint('stats', __name__, url_prefix='/api/stats')


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


def _range_args():
    start = _parse_date(request.args.get('start'))
    end = _parse_date(request.args.get('end'), end_of_day=True)
    return start, end


@stats_bp.route('/overview', methods=['GET'])
@login_required
def overview():
    start, end = _range_args()
    return jsonify({'code': 200, 'message': 'success', 'data': stats_service.overview(start, end)})


@stats_bp.route('/purchases', methods=['GET'])
@login_required
def purchases():
    group = request.args.get('group', 'component')
    limit = request.args.get('limit', 10, type=int)
    start, end = _range_args()
    data = stats_service.purchases_by(group=group, limit=limit, start=start, end=end)
    return jsonify({'code': 200, 'message': 'success', 'data': data})


@stats_bp.route('/consumption', methods=['GET'])
@login_required
def consumption():
    group = request.args.get('group', 'component')
    limit = request.args.get('limit', 10, type=int)
    start, end = _range_args()
    data = stats_service.consumption_by(group=group, limit=limit, start=start, end=end)
    return jsonify({'code': 200, 'message': 'success', 'data': data})


@stats_bp.route('/trend', methods=['GET'])
@login_required
def trend():
    months = request.args.get('months', 12, type=int)
    start, end = _range_args()
    return jsonify({
        'code': 200,
        'message': 'success',
        'data': stats_service.monthly_trend(months, start, end),
    })


@stats_bp.route('/export', methods=['GET'])
@login_required
def export():
    start, end = _range_args()
    rows = stats_service.export_components(start=start, end=end)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        '元件ID', '元件名称', '值', '分类', '供应商',
        '采购数量', '采购金额(元)', '消耗数量', '估算消耗金额(元)',
    ])
    for r in rows:
        writer.writerow([
            r['id'], r['name'], r['value'], r['category'], r['supplier'],
            r['in_qty'], r['in_cost'], r['out_qty'], r['out_cost'],
        ])

    csv_data = '\ufeff' + output.getvalue()
    filename = 'purchase_consumption_stats.csv'
    return Response(
        csv_data,
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename={filename}'},
    )
