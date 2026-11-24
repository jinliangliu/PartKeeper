"""把现有 SQLite 库整体迁移到 PostgreSQL。

用法（在 backend 目录，目标库需已由应用建好表）::

    DATABASE_URL=postgresql+psycopg://user:pass@host:5433/db \
        python scripts/migrate_sqlite_to_pg.py --source instance/app.db --dry-run

    # 确认无误后去掉 --dry-run 真正写入；--truncate 先清空目标表

设计取舍：

- 直接读 SQLite 原始行，不经过 ORM：源库是旧结构（可能还有 components 表），
  用 ORM 会触发模型假设，反而容易出错。
- 按目标表列名匹配，只迁两边都有的列：源库多出的历史列忽略，目标库新增的
  列走默认值。
- 保留主键，迁移后修正序列；否则新插入会撞主键。
- 布尔与日期做显式转换：SQLite 存 0/1 与字符串，PG 不接受隐式转换。
"""

import argparse
import os
import sqlite3
import sys
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, create_engine, inspect, text

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

# 迁移顺序：被引用的表在前
TABLE_ORDER = [
    'users', 'categories', 'suppliers', 'locations',
    'items', 'item_specs',
    'transactions', 'utility_bills', 'expenses', 'expense_attachments',
    'maintenances', 'boms', 'bom_items', 'api_tokens',
]

# 这些列在目标表里是自增主键，迁移后要重设序列
SERIAL_COLUMNS = {'id'}


def _parse_datetime(value):
    if value in (None, ''):
        return None
    if isinstance(value, (datetime, date)):
        return value
    raw = str(value).strip().replace('T', ' ')
    for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _parse_date(value):
    if value in (None, ''):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    parsed = _parse_datetime(value)
    return parsed.date() if parsed else None


def _convert(value, column_type):
    """按目标列类型转换 SQLite 的原值。"""
    if value is None:
        return None
    if isinstance(column_type, Boolean):
        return bool(int(value)) if str(value).strip() not in ('', 'None') else False
    if isinstance(column_type, DateTime):
        return _parse_datetime(value)
    if isinstance(column_type, Date):
        return _parse_date(value)
    if isinstance(column_type, Float):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if isinstance(column_type, Integer):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', default=os.path.join(BASE_DIR, 'instance', 'app.db'))
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--truncate', action='store_true', help='先清空目标表')
    args = parser.parse_args()

    if not os.path.exists(args.source):
        raise SystemExit(f'源库不存在：{args.source}')
    dsn = os.getenv('DATABASE_URL', '')
    if not dsn.startswith('postgresql'):
        raise SystemExit('DATABASE_URL 必须指向 PostgreSQL')

    src = sqlite3.connect(args.source)
    src.row_factory = sqlite3.Row
    engine = create_engine(dsn, future=True)
    target_tables = set(inspect(engine).get_table_names())

    report = []
    if args.truncate:
        # 必须用单条语句、独立事务立即提交：逐表 TRUNCATE 会在长事务里累积锁，
        # 中途中断（信号/网络）会让连接停在 idle in transaction，后续迁移全部阻塞。
        with engine.begin() as conn:
            conn.execute(text(
                f'TRUNCATE TABLE {", ".join(reversed(TABLE_ORDER))} '
                'RESTART IDENTITY CASCADE'
            ))
        print('已清空目标表')

    with engine.begin() as conn:
        conn.execute(text("SET LOCAL lock_timeout = '15s'"))
        conn.execute(text("SET LOCAL statement_timeout = '120s'"))

        for table in TABLE_ORDER:
            if table not in target_tables:
                report.append((table, '跳过（目标无此表）'))
                continue

            src_cols = {r[1] for r in src.execute(f'PRAGMA table_info({table})')}
            dst_cols = {c['name']: c['type'] for c in inspect(engine).get_columns(table)}
            common = [c for c in dst_cols if c in src_cols]
            if not common:
                report.append((table, '跳过（无公共列）'))
                continue

            rows = src.execute(f'SELECT {", ".join(common)} FROM {table}').fetchall()
            if not rows:
                report.append((table, '0 行'))
                continue

            payload = []
            for row in rows:
                payload.append({
                    col: _convert(row[col], dst_cols[col]) for col in common
                })

            if args.dry_run:
                report.append((table, f'{len(payload)} 行（预演，未写入）'))
                continue

            col_list = ', '.join(common)
            placeholders = ', '.join(f':{c}' for c in common)
            conn.execute(text(f'INSERT INTO {table} ({col_list}) VALUES ({placeholders})'), payload)

            if 'id' in common:
                conn.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {table}), 1))"
                ))
            report.append((table, f'{len(payload)} 行'))

    print('\n表'.ljust(24), '结果')
    print('-' * 50)
    for table, result in report:
        print(table.ljust(24), result)

    if args.dry_run:
        print('\n预演结束，未写入任何数据。去掉 --dry-run 正式执行。')
        return

    # 迁移后核对行数
    print('\n行数核对（SQLite → PostgreSQL）')
    print('-' * 50)
    mismatches = 0
    with engine.connect() as conn:
        for table in TABLE_ORDER:
            if table not in target_tables:
                continue
            try:
                src_count = src.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            except sqlite3.OperationalError:
                continue
            dst_count = conn.execute(text(f'SELECT COUNT(*) FROM {table}')).scalar()
            flag = 'OK' if src_count == dst_count else '不一致'
            if src_count != dst_count:
                mismatches += 1
            print(f'{table:<24} {src_count:>6} → {dst_count:>6}  {flag}')

    if mismatches:
        raise SystemExit(f'\n有 {mismatches} 张表行数不一致，请检查后再切换服务')
    print('\n全部一致。')


if __name__ == '__main__':
    main()
