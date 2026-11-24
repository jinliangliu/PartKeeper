"""EDA 插件直连接口。

KiCad / EasyEDA 插件不再导出 CSV 再手动上传，而是把当前板子的元件清单
直接 POST 过来。与 Web 的 ``/api/bom/import`` 共用同一套匹配逻辑
（``bom_service.match_entries``），差异只在入参是 JSON 而非文件。

鉴权走 ``login_required``：既接受登录 JWT，也接受 ``pk_`` 访问令牌，
插件只需在设置里填一次令牌。
"""

from flask import Blueprint, request, jsonify

from services import bom_service
from utils.decorators import login_required

integrations_bp = Blueprint('integrations', __name__, url_prefix='/api/integrations')


@integrations_bp.route('/ping', methods=['GET'])
@login_required
def ping():
    """插件「测试连接」用：验证地址与令牌，返回当前身份。"""
    return jsonify({
        'code': 200,
        'message': 'success',
        'data': {
            'service': 'PartKeeper',
            'user': request.current_user.get('username'),
            'role': request.current_user.get('role'),
        },
    })


@integrations_bp.route('/bom/match', methods=['POST'])
@login_required
def match_bom():
    """匹配元件清单。

    请求体::

        {
          "source": "kicad",
          "create_missing": false,
          "items": [
            {"designator": "R1", "value": "10k", "package": "0603",
             "quantity": 2, "name": "电阻", "mpn": "RC0603FR-0710KL"}
          ]
        }

    响应 ``lines`` 每行带 ``matched_id`` / ``current_stock`` / ``shortage``；
    ``create_missing=true`` 时为未匹配项建物品（需管理员）。
    """
    payload = request.get_json(silent=True) or {}
    entries = payload.get('items')
    create_missing = bool(payload.get('create_missing'))

    try:
        result = bom_service.match_entries(entries)
    except bom_service.BOMError as exc:
        return jsonify({'code': 400, 'message': str(exc), 'data': None}), 400

    data = dict(result)
    data['source'] = payload.get('source') or 'plugin'

    if create_missing:
        if request.current_user.get('role') != 'admin':
            return jsonify({
                'code': 403,
                'message': '创建缺失物料需要管理员权限',
                'data': None,
            }), 403
        data['created'] = bom_service.create_missing_from_result(result)
        _sync_embeddings_quiet()

    return jsonify({'code': 200, 'message': 'success', 'data': data})


def _sync_embeddings_quiet():
    """新物品补向量。失败不影响导入结果，后续可手动重建索引。"""
    from flask import current_app
    from services import embedding_service

    if not embedding_service.is_available():
        return
    try:
        embedding_service.sync_all()
    except embedding_service.EmbeddingUnavailable as exc:
        current_app.logger.warning('导入后向量补齐失败：%s', exc)
