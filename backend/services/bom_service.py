"""BOM（物料清单）解析与库存匹配业务逻辑。

两个入口共用同一套匹配：

- ``parse_bom``：Web 端上传 CSV（EDA 导出的文件）；
- ``match_entries``：插件直连（KiCad / EasyEDA 直接 POST 结构化清单）。

匹配索引一次建好复用。旧写法每行都 ``Item.query.all()``，几十行的 BOM 就是
几十次全表扫描；切到 PostgreSQL 后网络往返会把这个问题放大。
"""

import csv
import io
from collections import defaultdict

from models import db, Item


# 常见 EDA 工具导出的 BOM 表头别名（不区分大小写）
HEADER_ALIASES = {
    'value': ['value', '值', '参数', '规格', 'value/值'],
    'package': ['package', 'footprint', '封装', '封装/尺寸', '封装尺寸', 'footprint/封装'],
    'quantity': ['quantity', 'qty', '数量', '用量', 'qty.', 'count'],
    'designator': ['designator', 'reference', 'ref', 'references', '位号', '编号', 'designators'],
    'name': ['name', 'comment', '名称', '描述', 'description', 'type', '类型'],
    'supplier': ['supplier', '供应商', 'vendor'],
    'mpn': ['mpn', 'part number', 'part_number', '型号', '料号', '厂商料号'],
}

# 插件单次请求的最大行数，防止误传整库
MAX_ENTRIES = 1000


class BOMError(Exception):
    """BOM 解析异常，message 可直接返回前端。"""


def _decode(raw: bytes):
    for encoding in ('utf-8-sig', 'gbk', 'gb18030'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', errors='replace')


def _find_columns(header):
    mapping = {}
    normalized = [str(c).strip().lower() for c in header]
    for field, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            if alias.lower() in normalized:
                mapping[field] = normalized.index(alias.lower())
                break
    return mapping


def _parse_quantity(text):
    text = str(text or '').strip().replace(',', '')
    if not text:
        return 1
    try:
        qty = int(float(text))
        return qty if qty > 0 else 1
    except (TypeError, ValueError):
        return 1


def _build_index():
    """按参数值给全部物品建索引，一次查询解决所有行的匹配。"""
    index = defaultdict(list)
    for item in Item.query.all():
        key = (item.value or '').strip().casefold()
        if key:
            index[key].append(item)
    return index


def _match_in_index(index, value, package):
    target_value = (value or '').strip().casefold()
    target_package = package.strip().casefold() if package else None

    candidates = index.get(target_value) or []
    if not candidates:
        return None
    if target_package:
        for c in candidates:
            if c.package and c.package.strip().casefold() == target_package:
                return c
    return candidates[0]


def _normalize_entry(entry, row_no):
    """把一条输入规整为标准行；value 为空返回 None（视为无效行）。"""
    value = str(entry.get('value') or '').strip()
    if not value:
        return None
    package = str(entry.get('package') or '').strip() or None
    return {
        'row': row_no,
        'designator': str(entry.get('designator') or '').strip() or None,
        'value': value,
        'package': package,
        'quantity': _parse_quantity(entry.get('quantity')),
        'name': str(entry.get('name') or '').strip() or None,
        'supplier': str(entry.get('supplier') or '').strip() or None,
        'mpn': str(entry.get('mpn') or '').strip() or None,
    }


def _match_rows(rows):
    """对标准行做库存匹配，返回 {lines, summary}。"""
    index = _build_index()
    lines = []
    for row in rows:
        component = _match_in_index(index, row['value'], row['package'])
        current_stock = component.current_stock if component else 0
        lines.append({
            **row,
            'matched_id': component.id if component else None,
            'matched_name': component.name if component else None,
            'current_stock': current_stock,
            'shortage': max(0, row['quantity'] - current_stock),
        })

    if not lines:
        raise BOMError('未解析到有效数据行')

    matched = sum(1 for l in lines if l['matched_id'])
    summary = {
        'total_lines': len(lines),
        'matched_lines': matched,
        'missing_lines': len(lines) - matched,
        'shortage_lines': sum(1 for l in lines if l['shortage'] > 0),
        'total_qty': sum(l['quantity'] for l in lines),
        'total_shortage_qty': sum(l['shortage'] for l in lines),
    }
    return {'lines': lines, 'summary': summary}


def parse_bom(raw: bytes):
    """解析 CSV 并匹配库存（Web 上传入口）。"""
    text = _decode(raw)
    rows = [row for row in csv.reader(io.StringIO(text))]
    if not rows:
        raise BOMError('文件为空')

    columns = _find_columns(rows[0])
    if 'value' not in columns:
        raise BOMError('无法识别表头，缺少“值 / Value”列')

    normalized = []
    for idx, row in enumerate(rows[1:], start=2):
        if not row or all((c or '').strip() == '' for c in row):
            continue

        def cell(field):
            col = columns.get(field)
            return row[col].strip() if col is not None and col < len(row) else ''

        entry = _normalize_entry({
            'value': cell('value'),
            'package': cell('package'),
            'quantity': cell('quantity'),
            'designator': cell('designator'),
            'name': cell('name'),
            'supplier': cell('supplier'),
            'mpn': cell('mpn'),
        }, idx)
        if entry is not None:
            normalized.append(entry)

    return _match_rows(normalized)


def match_entries(entries):
    """插件直连入口：对结构化清单做匹配。"""
    if not isinstance(entries, list) or not entries:
        raise BOMError('items 不能为空')
    if len(entries) > MAX_ENTRIES:
        raise BOMError(f'单次最多 {MAX_ENTRIES} 行，当前 {len(entries)} 行')

    rows = []
    for idx, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise BOMError(f'第 {idx} 行格式错误，应为对象')
        normalized = _normalize_entry(entry, idx)
        if normalized is not None:
            rows.append(normalized)
    if not rows:
        raise BOMError('所有行都缺少 value 字段')
    return _match_rows(rows)


def create_missing_from_result(result):
    """为匹配结果中缺失的条目创建物品，返回创建数量。"""
    created = 0
    for line in result['lines']:
        if line['matched_id']:
            continue
        name = line['name'] or line['value']
        db.session.add(Item(
            name=(name or '')[:100],
            value=line['value'][:50],
            package=(line['package'] or None)[:30] if line['package'] else None,
            min_stock=line['quantity'],
            current_stock=0,
        ))
        created += 1
    db.session.commit()
    return created


def create_missing_components(raw: bytes):
    """为 CSV 中未匹配到物料的条目创建记录（Web 上传入口）。"""
    parsed = parse_bom(raw)
    return {'created': create_missing_from_result(parsed), 'summary': parsed['summary']}
