import hashlib
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.Enum('admin', 'user'), default='user')
    email = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    transactions = db.relationship('Transaction', backref='operator', lazy=True)

class Category(db.Model):
    __tablename__ = 'categories'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    
    components = db.relationship('Component', backref='category', lazy=True)
    children = db.relationship('Category', backref=db.backref('parent', remote_side=[id]), lazy=True)

class Supplier(db.Model):
    __tablename__ = 'suppliers'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    contact = db.Column(db.String(50))
    phone = db.Column(db.String(20))
    address = db.Column(db.String(200))
    website = db.Column(db.String(200))
    
    components = db.relationship('Component', backref='supplier', lazy=True)

class Location(db.Model):
    __tablename__ = 'locations'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(100))
    
    components = db.relationship('Component', backref='location', lazy=True)

class Component(db.Model):
    __tablename__ = 'components'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'))
    name = db.Column(db.String(100), nullable=False)
    value = db.Column(db.String(50))
    package = db.Column(db.String(30))
    tolerance = db.Column(db.String(10))
    brand = db.Column(db.String(50))
    datasheet_url = db.Column(db.String(255))
    min_stock = db.Column(db.Integer, default=0)
    current_stock = db.Column(db.Integer, default=0)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'))
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'))
    unit = db.Column(db.String(10), default='个')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # --- 家庭场景通用属性（方案 B 时可平移到 Item 主表） ---
    is_consumable = db.Column(db.Boolean, default=False)          # 是否为消耗品
    consumption_rate = db.Column(db.Float)                        # 显式消耗速率（单位/天），留空则从出库流水推算
    warranty_expiry = db.Column(db.Date)                          # 保修到期日
    maintenance_cycle_days = db.Column(db.Integer)                # 维护周期（天）
    last_maintenance_date = db.Column(db.Date)                    # 上次维护日期

    transactions = db.relationship('Transaction', backref='component', lazy=True)

class Transaction(db.Model):
    __tablename__ = 'transactions'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    component_id = db.Column(db.Integer, db.ForeignKey('components.id'), nullable=False)
    type = db.Column(db.Enum('in', 'out'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float)  # 入库时的单价（元），仅采购入库使用；出库为空
    order_id = db.Column(db.Integer)
    operator_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    note = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class UtilityBill(db.Model):
    """生活缴费账单（水电煤等）。以 dedup_key 唯一约束实现截图重复导入去重。"""
    __tablename__ = 'utility_bills'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    category = db.Column(
        db.Enum('water', 'electricity', 'gas', 'internet', 'phone', 'other'),
        nullable=False,
    )
    amount = db.Column(db.Float, nullable=False)                  # 缴费金额（元）
    paid_at = db.Column(db.DateTime, nullable=False)              # 缴费时间
    period = db.Column(db.String(20))                             # 账单所属期，如 2026-10
    counterparty = db.Column(db.String(100))                      # 收款方，如「国家电网」
    external_id = db.Column(db.String(100))                       # 渠道交易单号（支付宝/微信/银行流水号等）
    channel = db.Column(db.String(20), default='other')           # 缴费渠道：alipay/wechat/bank/cash/other
    note = db.Column(db.String(255))
    source = db.Column(db.String(30), default='screenshot')       # 录入来源：screenshot/manual
    dedup_key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    VALID_CHANNELS = ('alipay', 'wechat', 'bank', 'cash', 'other')

    @staticmethod
    def build_dedup_key(category, amount, paid_at, counterparty='', external_id='', channel='other'):
        """生成去重键，对缴费渠道无偏见。

        有渠道交易单号时：以「渠道 + 单号」为键（同一串单号在支付宝与微信是两笔不同交易，
        必须带渠道区分）；无单号时用「渠道 + 类型 + 金额 + 缴费日期 + 收款方」规范化取哈希。
        时间只取到「日」——账单截图通常不给出具体时分秒，同日不同时刻视为同一笔。
        """
        channel = str(channel or 'other').strip().lower()
        if external_id and str(external_id).strip():
            raw = f"ext|{channel}|{str(external_id).strip()}"
        else:
            dt = paid_at
            if isinstance(dt, str):
                dt = datetime.strptime(dt[:10], '%Y-%m-%d')
            day = dt.strftime('%Y-%m-%d') if hasattr(dt, 'strftime') else str(dt)[:10]
            party = ''.join(str(counterparty or '').split()).lower()
            raw = f"noext|{channel}|{category}|{round(float(amount), 2):.2f}|{day}|{party}"
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()


class Expense(db.Model):
    """家庭各类开支记录（教育/培训/旅行/娱乐/购物/医疗等）。

    与 UtilityBill 物理分表、逻辑归一：生活缴费有「账期」「收款方」等特化语义，
    继续留在 utility_bills；其余开支落本表。统计时两表聚合为家庭总支出。
    以 dedup_key 唯一约束实现截图/重复录入去重。
    """
    __tablename__ = 'expenses'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    category = db.Column(db.String(30), nullable=False, index=True)   # 一级类型，见 VALID_CATEGORIES
    subcategory = db.Column(db.String(50))                            # 自由文本：英语培训 / 机票 / 电影
    amount = db.Column(db.Float, nullable=False)                      # 金额（元）
    occurred_at = db.Column(db.DateTime, nullable=False, index=True)   # 消费发生时间
    merchant = db.Column(db.String(100))                             # 商户 / 机构 / 平台
    channel = db.Column(db.String(20), default='other')              # alipay/wechat/bank/cash/other
    external_id = db.Column(db.String(100))                          # 渠道交易单号（若有）
    note = db.Column(db.String(255))
    tags = db.Column(db.String(200))                                 # 逗号分隔标签，如「孩子,暑期」
    currency = db.Column(db.String(8), default='CNY')
    source = db.Column(db.String(30), default='manual')               # 录入来源：screenshot/manual
    dedup_key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    # 可空外键：买家电、修空调这类钱可以挂到具体物品上，普通生活开支留空
    component_id = db.Column(db.Integer, db.ForeignKey('components.id'), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    attachments = db.relationship(
        'ExpenseAttachment',
        backref='expense',
        cascade='all, delete-orphan',
        lazy=True,
    )
    component = db.relationship('Component', backref=db.backref('expenses', lazy=True))

    # 一级类型固定集合（String 而非 Enum：后续新增类型无需改表结构）
    VALID_CATEGORIES = (
        'education', 'training', 'travel', 'entertainment',
        'shopping', 'medical', 'dining', 'transport',
        'housing', 'digital', 'maintenance', 'other',
    )
    VALID_CHANNELS = ('alipay', 'wechat', 'bank', 'cash', 'other')

    @staticmethod
    def build_dedup_key(category, amount, occurred_at, merchant='', external_id='',
                        channel='other'):
        """生成去重键，语义与 UtilityBill 一致但对开支类型通用。

        有渠道交易单号：``ext|渠道|单号``（同串单号跨渠道是不同交易，不能合并）。
        无单号：``noext|渠道|类型|金额|日期|商户``，时间只取到「日」——
        截图通常不给具体时刻，同日同商户同金额同类型视为同一笔。
        """
        channel = str(channel or 'other').strip().lower()
        if external_id and str(external_id).strip():
            raw = f"ext|{channel}|{str(external_id).strip()}"
        else:
            dt = occurred_at
            if isinstance(dt, str):
                dt = datetime.strptime(dt[:10], '%Y-%m-%d')
            day = dt.strftime('%Y-%m-%d') if hasattr(dt, 'strftime') else str(dt)[:10]
            who = ''.join(str(merchant or '').split()).lower()
            raw = f"noext|{channel}|{category}|{round(float(amount), 2):.2f}|{day}|{who}"
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()


class ExpenseAttachment(db.Model):
    """开支凭证附件（票据/截图）。

    只在库里存文件元信息，二进制落磁盘（instance/uploads/）——SQLite 存 BLOB
    会迅速膨胀且拖慢备份迁移。sha256 既做完整性校验，也做「同一张图重复上传只存一份」的依据。
    原图不存原始文件名（文件名本身可能是隐私），磁盘上以哈希命名。
    """
    __tablename__ = 'expense_attachments'
    __table_args__ = (
        db.UniqueConstraint('expense_id', 'sha256', name='uq_expense_attachment'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    expense_id = db.Column(db.Integer, db.ForeignKey('expenses.id'), nullable=False, index=True)
    file_path = db.Column(db.String(500), nullable=False)   # 相对 instance/ 的路径
    sha256 = db.Column(db.String(64), nullable=False, index=True)
    size_bytes = db.Column(db.Integer)
    mime = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Maintenance(db.Model):
    """物品维护记录：清洁保养、维修、更换耗材、巡检。

    刻意**不存金额**——钱只记在 expenses 一处。维护产生的花费通过 ``expense_id``
    关联到一笔开支（类型 maintenance，同时挂 component_id），这样：
      · 家庭总支出自动包含维修费，不用在统计里加第三张表；
      · 物品账本 = 该物品名下所有开支之和，购置与维修天然同源，不会两处对不上。

    维护只记「发生了什么」：类型、内容、时间、服务商。没有花钱的日常保养
    （自己清洗滤网）不产生开支，expense_id 留空。
    """
    __tablename__ = 'maintenances'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    component_id = db.Column(db.Integer, db.ForeignKey('components.id'),
                             nullable=False, index=True)
    type = db.Column(db.String(20), nullable=False, default='other', index=True)
    title = db.Column(db.String(120), nullable=False)          # 做了什么：换滤芯 / 清洗冷凝器
    performed_at = db.Column(db.DateTime, nullable=False, index=True)
    vendor = db.Column(db.String(100))                         # 服务商 / 维修点
    expense_id = db.Column(db.Integer, db.ForeignKey('expenses.id'), index=True)
    note = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    component = db.relationship('Component', backref=db.backref('maintenances', lazy=True))
    expense = db.relationship('Expense', backref=db.backref('maintenance', uselist=False))

    # 维护类型固定集合（与 utils.ledger.MAINTENANCE_LABELS 一一对应）
    VALID_TYPES = ('cleaning', 'repair', 'replacement', 'inspection', 'other')


class Bom(db.Model):
    __tablename__ = 'boms'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship(
        'BomItem',
        backref='bom',
        cascade='all, delete-orphan',
        lazy=True,
    )


class BomItem(db.Model):
    __tablename__ = 'bom_items'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    bom_id = db.Column(db.Integer, db.ForeignKey('boms.id'), nullable=False)
    component_id = db.Column(db.Integer, db.ForeignKey('components.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)

    component = db.relationship('Component', backref='bom_items', lazy=True)
