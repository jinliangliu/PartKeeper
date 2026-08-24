"""BOM（物料清单）解析与库存匹配业务逻辑。"""

import csv
import io

from models import db, Component


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
    text = (text or '').strip().replace(',', '')
    if not text:
        return 1
    try:
        qty = int(float(text))
        return qty if qty > 0 else 1
    except (TypeError, ValueError):
        return 1


def _match_component(value, package):
    target_value = (value or '').strip().casefold()
    target_package = package.strip().casefold() if package else None

    candidates = [
        c for c in Component.query.all()
        if (c.value or '').strip().casefold() == target_value
    ]
    if not candidates:
        return None
    if target_package:
        for c in candidates:
            if c.package and c.package.strip().casefold() == target_package:
                return c
    return candidates[0]


def parse_bom(raw: bytes):
    text = _decode(raw)
    reader = csv.reader(io.StringIO(text))
    rows = [row for row in reader]
    if not rows:
        raise BOMError('文件为空')

    header = rows[0]
    columns = _find_columns(header)
    if 'value' not in columns:
        raise BOMError('无法识别表头，缺少“值 / Value”列')

    lines = []
    for idx, row in enumerate(rows[1:], start=2):
        if not row or all((c or '').strip() == '' for c in row):
            continue

        def cell(field):
            col = columns.get(field)
            return (row[col].strip() if col is not None and col < len(row) else '')

        value = cell('value')
        if not value:
            continue

        package = cell('package') or None
        quantity = _parse_quantity(cell('quantity'))
        designator = cell('designator') or None
        name = cell('name') or None
        supplier = cell('supplier') or None
        mpn = cell('mpn') or None

        component = _match_component(value, package)
        current_stock = component.current_stock if component else 0
        shortage = max(0, quantity - current_stock)

        lines.append({
            'row': idx,
            'designator': designator,
            'value': value,
            'package': package,
            'quantity': quantity,
            'name': name,
            'supplier': supplier,
            'mpn': mpn,
            'matched_id': component.id if component else None,
            'matched_name': component.name if component else None,
            'current_stock': current_stock,
            'shortage': shortage,
        })

    if not lines:
        raise BOMError('未解析到有效数据行')

    matched = sum(1 for l in lines if l['matched_id'])
    shortage_lines = sum(1 for l in lines if l['shortage'] > 0)
    summary = {
        'total_lines': len(lines),
        'matched_lines': matched,
        'missing_lines': len(lines) - matched,
        'shortage_lines': shortage_lines,
        'total_qty': sum(l['quantity'] for l in lines),
        'total_shortage_qty': sum(l['shortage'] for l in lines),
    }
    return {'lines': lines, 'summary': summary}


def create_missing_components(raw: bytes):
    """为 BOM 中未匹配到物料的条目创建物料记录，并返回创建数量。"""
    parsed = parse_bom(raw)
    created = 0
    for line in parsed['lines']:
        if line['matched_id']:
            continue
        name = line['name'] or line['value']
        component = Component(
            name=(name or '')[:100],
            value=line['value'][:50],
            package=(line['package'] or None)[:30] if line['package'] else None,
            min_stock=line['quantity'],
            current_stock=0,
        )
        db.session.add(component)
        created += 1
    db.session.commit()
    return {'created': created, 'summary': parsed['summary']}
