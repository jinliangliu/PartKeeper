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


class ApiToken(db.Model):
    """对外访问令牌（个人访问令牌 / PAT），供 MCP 连接器等外部客户端使用。

    为什么不用登录 JWT：登录令牌有效期只有 JWT_EXPIRATION_HOURS（默认 24h），
    连接器需要长期有效的凭证；而 .env 里的 MCP_API_KEY 是全局静态串，改一次要重启，
    也记不到「谁在用、什么时候用的」。

    **只存 SHA-256 摘要**，明文在创建时返回一次后即不可再取（GitHub PAT 同款做法）——
    数据库被拷走也拿不到可用凭证。``prefix`` 保留明文头部用于列表辨识，
    二者组合无法还原原文。
    """
    __tablename__ = 'api_tokens'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    name = db.Column(db.String(60), nullable=False)               # 用途备注：WorkBuddy 连接器
    prefix = db.Column(db.String(16), nullable=False, index=True)  # pk_xxxxxxxx，仅展示
    token_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    scopes = db.Column(db.String(200), nullable=False, default='mcp:admin')
    expires_at = db.Column(db.DateTime)          # NULL = 永不过期
    last_used_at = db.Column(db.DateTime)
    revoked_at = db.Column(db.DateTime)          # 非空 = 已撤销（保留记录，便于审计）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship(
        'User',
        backref=db.backref('api_tokens', lazy=True, cascade='all, delete-orphan'),
    )

    def is_active(self, now=None):
        """令牌当前是否可用：未撤销、未过期。"""
        now = now or datetime.utcnow()
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None and self.expires_at <= now:
            return False
        return True

    @property
    def status(self):
        """供前端展示的三态：active / expired / revoked。"""
        if self.revoked_at is not None:
            return 'revoked'
        if self.expires_at is not None and self.expires_at <= datetime.utcnow():
            return 'expired'
        return 'active'


class Category(db.Model):
    __tablename__ = 'categories'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    
    items = db.relationship('Item', backref='category', lazy=True)
    children = db.relationship('Category', backref=db.backref('parent', remote_side=[id]), lazy=True)

class Supplier(db.Model):
    __tablename__ = 'suppliers'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    contact = db.Column(db.String(50))
    phone = db.Column(db.String(20))
    address = db.Column(db.String(200))
    website = db.Column(db.String(200))
    
    items = db.relationship('Item', backref='supplier', lazy=True)

class Location(db.Model):
    __tablename__ = 'locations'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(100))
    
    items = db.relationship('Item', backref='location', lazy=True)


class Item(db.Model):
    """统一物品主表：电子元器件、家电、家具、车辆等共用一张表。

    主表只放**与类型无关**的属性（名称、品牌、库存、分类、库位，以及保修/维护/
    消耗这类家庭生命周期字段）。类型专有属性放 ``item_specs`` 扩展表（1:1），
    新增类型不必给主表加列——这是从「Component 19 个字段上帝表」拆出来的核心目的。

    ``value`` / ``package`` / ``tolerance`` / ``datasheet_url`` 四个元器件字段
    通过 property 代理读写扩展表：调用点（路由、MCP、BOM 匹配、统计）可以继续写
    ``item.value``，但**不能用于 SQL 表达式**（不是 InstrumentedAttribute），
    需要按这些字段过滤/分组时必须显式 join ``ItemSpec``。
    """
    __tablename__ = 'items'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    kind = db.Column(db.String(30), nullable=False, default='electronic', index=True)
    name = db.Column(db.String(100), nullable=False)
    brand = db.Column(db.String(50))
    unit = db.Column(db.String(10), default='个')
    min_stock = db.Column(db.Integer, default=0)
    current_stock = db.Column(db.Integer, default=0)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'))
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'))
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # --- 家庭场景通用属性（与物品类型无关，故留在主表） ---
    is_consumable = db.Column(db.Boolean, default=False)          # 是否为消耗品
    consumption_rate = db.Column(db.Float)                        # 显式消耗速率（单位/天），留空则从出库流水推算
    warranty_expiry = db.Column(db.Date)                          # 保修到期日
    maintenance_cycle_days = db.Column(db.Integer)                # 维护周期（天）
    last_maintenance_date = db.Column(db.Date)                    # 上次维护日期

    # 类型扩展：joined 加载，列表页避免 N+1，也避免会话关闭后代理属性访问失败
    spec = db.relationship(
        'ItemSpec',
        backref=db.backref('item', lazy='joined'),
        uselist=False,
        cascade='all, delete-orphan',
        lazy='joined',
    )

    transactions = db.relationship('Transaction', backref='item', lazy=True)

    # 物品类型固定集合（String 而非 Enum：新增类型无需改表结构）
    VALID_KINDS = ('electronic', 'appliance', 'furniture', 'vehicle', 'other')

    def _spec_for_write(self):
        """取扩展表记录，没有就建一条。元器件字段写入前必须调用。"""
        if self.spec is None:
            self.spec = ItemSpec()
        return self.spec

    def _write_spec(self, column, value):
        """写扩展表。空值且尚无扩展行时不建行——纯家电/家具不该留下空壳记录。"""
        if value in (None, '') and self.spec is None:
            return
        setattr(self._spec_for_write(), column, value)

    @property
    def value(self):
        return self.spec.spec_value if self.spec else None

    @value.setter
    def value(self, v):
        self._write_spec('spec_value', v)

    @property
    def package(self):
        return self.spec.spec_package if self.spec else None

    @package.setter
    def package(self, v):
        self._write_spec('spec_package', v)

    @property
    def tolerance(self):
        return self.spec.spec_tolerance if self.spec else None

    @tolerance.setter
    def tolerance(self, v):
        self._write_spec('spec_tolerance', v)

    @property
    def datasheet_url(self):
        return self.spec.datasheet_url if self.spec else None

    @datasheet_url.setter
    def datasheet_url(self, v):
        self._write_spec('datasheet_url', v)

    def spec_attrs(self):
        """扩展表的自由属性（JSON 解码后），供新增物品类型使用。"""
        import json
        if not self.spec or not self.spec.attrs:
            return {}
        try:
            data = json.loads(self.spec.attrs)
        except (TypeError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}


class ItemSpec(db.Model):
    """物品类型扩展表（1:1 于 items）。

    目前承载电子元器件的专有属性（阻值/容值、封装、精度、数据手册）。这些字段
    刻意用**独立列**而非 JSON：它们是元器件的检索维度（按阻值搜、按封装匹配 BOM），
    放进 JSON 就只能退化成 Python 层过滤。

    ``attrs`` 是给尚未建模的新类型留的兜底（如家电的额定功率、车辆的里程），
    JSON 文本，仅展示用，不参与 SQL 检索。
    """
    __tablename__ = 'item_specs'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    item_id = db.Column(db.Integer, db.ForeignKey('items.id', ondelete='CASCADE'),
                        nullable=False, unique=True, index=True)
    spec_value = db.Column(db.String(50))          # 元器件：阻值 / 容值 / 型号标称值
    spec_package = db.Column(db.String(30))        # 封装：0603 / SOT-23
    spec_tolerance = db.Column(db.String(10))      # 精度：±1%
    datasheet_url = db.Column(db.String(255))
    attrs = db.Column(db.Text)                     # 其他类型自由属性（JSON 文本）
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Transaction(db.Model):
    __tablename__ = 'transactions'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    item_id = db.Column(db.Integer, db.ForeignKey('items.id'), nullable=False)
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
    item_id = db.Column(db.Integer, db.ForeignKey('items.id'), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    attachments = db.relationship(
        'ExpenseAttachment',
        backref='expense',
        cascade='all, delete-orphan',
        lazy=True,
    )
    item = db.relationship('Item', backref=db.backref('expenses', lazy=True))

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
    关联到一笔开支（类型 maintenance，同时挂 item_id），这样：
      · 家庭总支出自动包含维修费，不用在统计里加第三张表；
      · 物品账本 = 该物品名下所有开支之和，购置与维修天然同源，不会两处对不上。

    维护只记「发生了什么」：类型、内容、时间、服务商。没有花钱的日常保养
    （自己清洗滤网）不产生开支，expense_id 留空。
    """
    __tablename__ = 'maintenances'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    item_id = db.Column(db.Integer, db.ForeignKey('items.id'),
                        nullable=False, index=True)
    type = db.Column(db.String(20), nullable=False, default='other', index=True)
    title = db.Column(db.String(120), nullable=False)          # 做了什么：换滤芯 / 清洗冷凝器
    performed_at = db.Column(db.DateTime, nullable=False, index=True)
    vendor = db.Column(db.String(100))                         # 服务商 / 维修点
    expense_id = db.Column(db.Integer, db.ForeignKey('expenses.id'), index=True)
    note = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    item = db.relationship('Item', backref=db.backref('maintenances', lazy=True))
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
    item_id = db.Column(db.Integer, db.ForeignKey('items.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)

    item = db.relationship('Item', backref='bom_items', lazy=True)
