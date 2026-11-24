from flask import Blueprint, request, jsonify

from services import bom_service
from utils.decorators import login_required, admin_required

bom_bp = Blueprint('bom', __name__, url_prefix='/api/bom')


def _read_file():
    file = request.files.get('file')
    if file is None or file.filename == '':
        raise bom_service.BOMError('请上传 BOM 文件（CSV）')
    return file.read()


@bom_bp.route('/import', methods=['POST'])
@login_required
def import_bom():
    try:
        raw = _read_file()
        data = bom_service.parse_bom(raw)
    except bom_service.BOMError as exc:
        return jsonify({'code': 400, 'message': str(exc), 'data': None}), 400
    return jsonify({'code': 200, 'message': 'success', 'data': data})


@bom_bp.route('/apply', methods=['POST'])
@admin_required
def apply_bom():
    try:
        raw = _read_file()
        data = bom_service.create_missing_components(raw)
    except bom_service.BOMError as exc:
        return jsonify({'code': 400, 'message': str(exc), 'data': None}), 400
    # 新建物品默认没有向量，补一次（失败不影响导入结果）
    from routes.integrations import _sync_embeddings_quiet
    _sync_embeddings_quiet()
    return jsonify({'code': 200, 'message': 'success', 'data': data})
