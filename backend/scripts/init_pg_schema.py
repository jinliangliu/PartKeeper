"""在 PostgreSQL 上初始化表结构与 pgvector（幂等）。

用途：切换生产库前先建好目标结构，再跑数据迁移。
应用启动时也会做同样的事，这个脚本让「建表」和「迁移数据」可以分开执行、
分开验证。
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from sqlalchemy import text

from app import app
from models import db


def main():
    dsn = os.getenv('DATABASE_URL', '')
    if not dsn.startswith('postgresql'):
        raise SystemExit(f'DATABASE_URL 必须指向 PostgreSQL，当前：{dsn or "(未设置)"}')

    with app.app_context():
        with db.engine.connect() as conn:
            tables = conn.execute(text(
                "select table_name from information_schema.tables "
                "where table_schema='public' order by table_name"
            )).scalars().all()
            vector = conn.execute(text(
                "select extversion from pg_extension where extname='vector'"
            )).scalar()
            hnsw = conn.execute(text(
                "select indexdef from pg_indexes where indexname='ix_item_embeddings_hnsw'"
            )).scalar()

        print(f'库：{db.engine.url.database} @ {db.engine.url.host}:{db.engine.url.port}')
        print(f'表数量：{len(tables)}')
        print(f'表清单：{", ".join(tables)}')
        print(f'pgvector：{vector or "未安装"}')
        print(f'HNSW 索引：{"已建" if hnsw else "未建"}')
        if 'item_embeddings' not in tables:
            raise SystemExit('item_embeddings 未创建，请检查建表日志')


if __name__ == '__main__':
    main()
