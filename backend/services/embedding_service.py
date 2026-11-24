"""物品参数的向量化与语义检索。

设计要点：

1. **模型懒加载**。首次调用才载入 ONNX 权重，避免每次进程启动都付出
   几百毫秒与上百 MB 内存。gunicorn 多 worker 下每个进程各持一份。
2. **内容哈希跳过重编码**。物品保存时拼接检索文本、算 SHA-256，与旧值相同
   就不调模型——绝大多数编辑（改库存、改库位）不影响检索语义。
3. **只对 PostgreSQL 生效**。SQLite 没有 vector 类型，调用方应先查
   ``is_available()``，否则语义接口返回明确的不可用提示而不是 500。
"""

import hashlib
import threading

from flask import current_app
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from models import db, Category, Item, ItemEmbedding, EMBEDDING_DIM, EMBEDDING_MODEL

# 中文类型标签参与向量化：模型对「电子元器件」的理解比 kind='electronic' 好
KIND_LABELS = {
    'electronic': '电子元器件',
    'appliance': '家用电器',
    'furniture': '家具',
    'vehicle': '车辆',
    'other': '其他物品',
}

_model = None
_model_lock = threading.Lock()


class EmbeddingUnavailable(RuntimeError):
    """向量能力不可用（未启用、非 PG、模型加载失败）。"""


def _get_model():
    """懒加载并缓存 embedding 模型。"""
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as exc:  # 依赖未装
                raise EmbeddingUnavailable('未安装 fastembed，无法生成向量') from exc
            try:
                _model = TextEmbedding(current_app.config.get('EMBEDDING_MODEL', EMBEDDING_MODEL))
            except Exception as exc:  # 权重下载失败、ONNX 运行时不兼容等
                raise EmbeddingUnavailable(f'embedding 模型加载失败：{exc}') from exc
    return _model


def is_available():
    """当前环境是否具备语义检索能力。"""
    if db.engine.dialect.name != 'postgresql':
        return False
    return bool(current_app.config.get('EMBEDDING_ENABLED', True))


def build_text(item):
    """把物品的可检索信息拼成一段自然语言。

    只放对「找东西」有意义的字段：类型、名称、品牌、分类、参数。
    库存、库位、供应商不参与——「放在 A1 货架」不该影响语义相似度。
    """
    parts = [KIND_LABELS.get(item.kind, ''), item.name or '', item.brand or '']
    if getattr(item, 'category', None) is not None:
        parts.append(item.category.name or '')
    spec = getattr(item, 'spec', None)
    if spec is not None:
        parts.extend([
            spec.spec_value or '',
            spec.spec_package or '',
            spec.spec_tolerance or '',
        ])
    return ' '.join(p.strip() for p in parts if p and p.strip())


def _hash_text(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def embed_texts(texts):
    """批量编码。返回与输入等长的 list[list[float]]。"""
    if not texts:
        return []
    model = _get_model()
    try:
        return [list(map(float, vec)) for vec in model.embed(list(texts))]
    except Exception as exc:
        raise EmbeddingUnavailable(f'文本向量化失败：{exc}') from exc


def sync_item(item, commit=True):
    """同步单个物品的向量。

    返回 'created' / 'updated' / 'skipped'。文本未变时不做任何写入。
    """
    text = build_text(item)
    digest = _hash_text(text)

    row = db.session.get(ItemEmbedding, item.id)
    if row is not None and row.content_hash == digest:
        return 'skipped'

    vector = _encode_checked(text)
    if row is None:
        row = ItemEmbedding(item_id=item.id, content_hash=digest, embedding=vector,
                            model=current_app.config.get('EMBEDDING_MODEL', EMBEDDING_MODEL))
        db.session.add(row)
        result = 'created'
    else:
        row.content_hash = digest
        row.embedding = vector
        row.model = current_app.config.get('EMBEDDING_MODEL', EMBEDDING_MODEL)
        result = 'updated'

    if commit:
        db.session.commit()
    return result


def _encode_checked(text):
    """编码单条文本并校验维度，避免模型与表定义不一致时静默写入脏数据。"""
    vector = embed_texts([text])[0]
    if len(vector) != EMBEDDING_DIM:
        raise EmbeddingUnavailable(
            f'向量维度 {len(vector)} 与表定义 {EMBEDDING_DIM} 不一致，请检查 EMBEDDING_MODEL'
        )
    return vector


def remove_item(item_id, commit=True):
    """删除物品时清掉向量，避免孤儿行占用索引。"""
    row = db.session.get(ItemEmbedding, item_id)
    if row is None:
        return False
    db.session.delete(row)
    if commit:
        db.session.commit()
    return True


def sync_all(force=False, batch_size=64):
    """全量补齐/重建向量。

    force=True 时忽略内容哈希，全部重新编码（换模型后必须这样重建）。
    返回统计字典，便于接口与 CLI 展示。
    """
    stats = {'total': 0, 'created': 0, 'updated': 0, 'skipped': 0}
    existing_rows = {r.item_id: r for r in ItemEmbedding.query.all()}
    pending = []  # (item, digest, text, is_new)

    # 预加载分类：build_text 要读 category.name，不预加载会按物品数打 N 次查询
    items = Item.query.options(joinedload(Item.category)).all()
    for item in items:
        stats['total'] += 1
        text = build_text(item)
        digest = _hash_text(text)
        row = existing_rows.get(item.id)
        if row is not None and not force and row.content_hash == digest:
            stats['skipped'] += 1
            continue
        pending.append((item, digest, text, row is None))

    model_name = current_app.config.get('EMBEDDING_MODEL', EMBEDDING_MODEL)
    for start in range(0, len(pending), batch_size):
        chunk = pending[start:start + batch_size]
        vectors = embed_texts([text for _, _, text, _ in chunk])
        for (item, digest, _text, is_new), vector in zip(chunk, vectors):
            if len(vector) != EMBEDDING_DIM:
                raise EmbeddingUnavailable(
                    f'向量维度 {len(vector)} 与表定义 {EMBEDDING_DIM} 不一致'
                )
            row = existing_rows.get(item.id)
            if row is None:
                db.session.add(ItemEmbedding(
                    item_id=item.id, content_hash=digest, embedding=vector, model=model_name,
                ))
                stats['created'] += 1
            else:
                row.content_hash = digest
                row.embedding = vector
                row.model = model_name
                stats['updated'] += 1
        db.session.commit()

    return stats


def semantic_search(query, limit=10, kind=None, category_ids=None, low_stock=False):
    """向量检索，返回 [(Item, score)]，score 为余弦相似度（越大越相近）。

    结构化过滤在 SQL 层完成，向量排序只对过滤后的子集计算——避免先取
    top-k 再过滤导致结果不足。
    """
    if not query or not query.strip():
        return []
    vector = _encode_checked(query.strip())
    distance = ItemEmbedding.embedding.cosine_distance(vector)

    q = db.session.query(Item, distance.label('distance')).join(
        ItemEmbedding, ItemEmbedding.item_id == Item.id
    )
    if kind:
        q = q.filter(Item.kind == kind)
    if category_ids:
        q = q.filter(Item.category_id.in_(category_ids))
    if low_stock:
        q = q.filter(Item.current_stock <= Item.min_stock)

    rows = q.order_by(distance).limit(max(1, min(limit, 50))).all()
    return [(item, round(1.0 - float(dist), 4)) for item, dist in rows]


def index_status():
    """向量覆盖情况，供页面提示「重建索引」。"""
    total = db.session.query(func.count(Item.id)).scalar() or 0
    embedded = db.session.query(func.count(ItemEmbedding.item_id)).scalar() or 0
    return {'items': total, 'embedded': embedded, 'missing': max(0, total - embedded)}


def category_with_children(category_id):
    """取分类及其所有子分类 ID（分类是树形，按父级筛选应包含下级）。"""
    ids = [category_id]
    frontier = [category_id]
    while frontier:
        children = Category.query.filter(Category.parent_id.in_(frontier)).all()
        frontier = [c.id for c in children]
        ids.extend(frontier)
    return ids
