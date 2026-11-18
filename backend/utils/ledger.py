"""账本类枚举与渠道归一化 —— Web 与 MCP 共用同一套标签。

原先 MCP 层与 REST 层各自维护一份中文标签和渠道别名，改一处很容易漏掉另一处，
这里收敛为单一事实源。新增类型/渠道时只改这里。
"""

# 缴费类型 -> 中文标签（key 必须与 models.UtilityBill.category 枚举一致）
UTILITY_LABELS = {
    'water': '水费',
    'electricity': '电费',
    'gas': '燃气费',
    'internet': '宽带费',
    'phone': '话费',
    'other': '其他',
}

# 开支类型 -> 中文标签（key 必须与 models.Expense.VALID_CATEGORIES 一致）
EXPENSE_LABELS = {
    'education': '教育',
    'training': '培训',
    'travel': '旅行',
    'entertainment': '娱乐',
    'shopping': '购物',
    'medical': '医疗',
    'dining': '餐饮',
    'transport': '交通',
    'housing': '居住',
    'digital': '数码',
    'maintenance': '维修保养',
    'other': '其他',
}

# 维护类型 -> 中文标签（key 必须与 models.Maintenance.VALID_TYPES 一致）
MAINTENANCE_LABELS = {
    'cleaning': '清洁保养',
    'repair': '维修',
    'replacement': '更换耗材',
    'inspection': '巡检',
    'other': '其他',
}

# 维护类型的中文/别名 -> 枚举值（供对话录入时识别口语说法）
MAINTENANCE_ALIASES = {
    '清洁': 'cleaning', '清洗': 'cleaning', '保养': 'cleaning', '维护': 'cleaning',
    'cleaning': 'cleaning',
    '维修': 'repair', '修理': 'repair', '报修': 'repair', 'repair': 'repair',
    '更换': 'replacement', '换件': 'replacement', '换滤芯': 'replacement',
    '耗材': 'replacement', 'replacement': 'replacement',
    '巡检': 'inspection', '检查': 'inspection', '年检': 'inspection',
    'inspection': 'inspection',
    '其他': 'other', 'other': 'other',
}

# 缴费渠道 -> 中文标签
UTILITY_CHANNELS = {
    'alipay': '支付宝',
    'wechat': '微信',
    'bank': '银行代扣',
    'cash': '现金',
    'other': '其他渠道',
}

# 开支渠道 -> 中文标签
CHANNELS = {
    'alipay': '支付宝',
    'wechat': '微信',
    'bank': '银行代扣',
    'cash': '现金',
    'other': '其他',
}

# 中文/别名 -> 英文枚举值
CHANNEL_ALIASES = {
    '微信': 'wechat', '微信支付': 'wechat', 'wx': 'wechat',
    '支付宝': 'alipay', 'ali': 'alipay',
    '银行': 'bank', '银行代扣': 'bank', '银行卡': 'bank', 'card': 'bank',
    '现金': 'cash',
}


def normalize_channel(value, allowed):
    """把中文/别名渠道名归一化为英文枚举值；无法识别时归入 other。

    ``allowed`` 传合法渠道集合，便于不同表各自收窄取值范围。
    """
    raw = str(value or 'other').strip().lower()
    channel = CHANNEL_ALIASES.get(raw, raw)
    return channel if channel in allowed else 'other'
