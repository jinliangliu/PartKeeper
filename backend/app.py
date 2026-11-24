"""PartKeeper 后端应用入口。

职责：创建 Flask 应用、初始化数据库与 CORS、注册所有蓝图、初始化管理员账号。
"""
import os
import shutil
import sys
from datetime import datetime

# 保证 `python app.py` 或从项目根目录运行时都能正确导入 backend 包内模块
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from flask import Flask, jsonify, current_app
from flask_cors import CORS
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from config import Config
from models import db, User, Category
from utils import hash_password


# 面向电子 DIY 场景的常用分类树（启动时自动补种，仅添加缺失项）
COMMON_CATEGORIES = [
    ('无源器件', [
        ('电阻', ['贴片电阻', '直插电阻', '电位器']),
        ('电容', ['贴片电容', '陶瓷电容', '电解电容', '钽电容']),
        ('电感', ['贴片电感', '功率电感']),
        ('二极管', ['整流二极管', '稳压二极管', '肖特基二极管', '发光二极管(LED)']),
        ('晶体管', ['三极管', 'MOSFET']),
        ('晶振/谐振器', ['石英晶振', '陶瓷谐振器']),
        ('保险丝/熔断器', []),
    ]),
    ('集成电路(IC)', [
        ('MCU/单片机', []),
        ('电源芯片', []),
        ('运放/比较器', []),
        ('接口/通信芯片', []),
        ('传感器', []),
        ('逻辑芯片', []),
        ('存储器', []),
    ]),
    ('PCB/电路板', ['PCB打样板', '洞洞板/万能板', '面包板', '转接板', '覆铜板']),
    ('连接器', ['排针/排母', '接线端子', 'USB连接器', '其他连接器']),
    ('结构件', ['螺丝/螺母/垫圈', '铜柱/螺柱', '外壳/机箱', '支架/固定件', '散热器/散热片', '风扇']),
    ('零件', ['弹簧/垫片', '轴承/齿轮', '联轴器', '五金杂件']),
    ('电机', ['直流电机', '减速电机', '步进电机', '舵机', '无刷电机', '振动电机']),
    ('开关/按键', []),
    ('模块/开发板', []),
    ('线材/其他', []),
]


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    db.init_app(app)
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    from routes import register_blueprints
    register_blueprints(app)

    register_error_handlers(app)

    with app.app_context():
        # 顺序不可颠倒：结构重构必须在 create_all() 之前，
        # 否则会先建出空的 items 表，与 components 重命名冲突。
        migrate()
        db.create_all()
        seed_admin()
        seed_categories()

    return app


def migrate():
    """轻量迁移入口：先做方案 B 的结构重构，再补齐增量字段。

    create_all() 只会建缺失的表，不会给已有表加列，也不会重构表结构；
    这里用 ALTER TABLE 补齐。每一步都先检查现状，保证重复启动幂等。
    """
    _migrate_components_to_items()

    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())

    # 列定义：表名 -> [(列名, SQLite 列类型与默认值), ...]
    additions = {
        'transactions': [
            ('unit_price', 'FLOAT'),
        ],
        'items': [
            ('kind', "VARCHAR(30) NOT NULL DEFAULT 'electronic'"),
            ('is_consumable', 'BOOLEAN DEFAULT 0'),
            ('consumption_rate', 'FLOAT'),
            ('warranty_expiry', 'DATE'),
            ('maintenance_cycle_days', 'INTEGER'),
            ('last_maintenance_date', 'DATE'),
        ],
        'utility_bills': [
            ('channel', "VARCHAR(20) DEFAULT 'other'"),
        ],
        'expenses': [
            # 注：SQLite 的 ADD COLUMN 不能带外键约束，关联完整性由路由层校验
            ('item_id', 'INTEGER'),
        ],
    }

    for table, columns in additions.items():
        if table not in tables:
            continue
        existing = {c['name'] for c in inspector.get_columns(table)}
        for name, definition in columns:
            if name not in existing:
                db.session.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {definition}'))
                db.session.commit()


def _backup_database():
    """迁移前复制一份 SQLite 文件，返回备份路径（非 SQLite 或文件不存在时返回 None）。"""
    uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
    prefix = 'sqlite:///'
    if not uri.startswith(prefix):
        return None
    path = uri[len(prefix):]
    if not os.path.exists(path):
        return None
    backup_dir = os.path.join(os.path.dirname(path), 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    target = os.path.join(backup_dir, f'app-{stamp}.db')
    shutil.copy2(path, target)
    return target


def _migrate_components_to_items():
    """方案 B 结构重构：components 主表改为 items，元器件专有字段迁到 item_specs。

    为什么必须在这一个函数里一次做完：SQLite 不支持 ADD CONSTRAINT，
    真正的结构变更只能靠 RENAME / ADD COLUMN / DROP COLUMN 组合。好在实测
    （SQLite 3.53）RENAME TABLE 会自动更新子表外键目标，RENAME COLUMN 会更新
    外键列名，因此不需要重建 transactions / expenses / maintenances / bom_items。

    幂等条件：components 不存在（全新库或已迁移）时整段跳过。
    整段在一个事务内执行，任何一步失败都回滚，不会留下半迁移状态。
    """
    tables = set(inspect(db.engine).get_table_names())
    if 'components' not in tables or 'items' in tables:
        return

    backup = _backup_database()
    if backup:
        current_app.logger.info('检测到旧表结构，迁移前已备份数据库至 %s', backup)

    with db.engine.begin() as conn:
        # 1. 主表改名，子表外键目标自动跟随
        conn.execute(text('ALTER TABLE components RENAME TO items'))

        # 2. 类型扩展表（1:1）
        conn.execute(text("""
            CREATE TABLE item_specs (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                spec_value VARCHAR(50),
                spec_package VARCHAR(30),
                spec_tolerance VARCHAR(10),
                datasheet_url VARCHAR(255),
                attrs TEXT,
                updated_at DATETIME,
                FOREIGN KEY(item_id) REFERENCES items (id) ON DELETE CASCADE
            )
        """))
        conn.execute(text('CREATE UNIQUE INDEX ix_item_specs_item_id ON item_specs (item_id)'))

        # 3. 搬迁元器件字段。只给确实有内容的物品建扩展行，避免整库空行
        conn.execute(text("""
            INSERT INTO item_specs (item_id, spec_value, spec_package, spec_tolerance, datasheet_url)
            SELECT id, value, package, tolerance, datasheet_url FROM items
            WHERE COALESCE(value, '') <> '' OR COALESCE(package, '') <> ''
               OR COALESCE(tolerance, '') <> '' OR COALESCE(datasheet_url, '') <> ''
        """))

        # 4. 物品类型。历史数据全部是电子元器件
        conn.execute(text(
            "ALTER TABLE items ADD COLUMN kind VARCHAR(30) NOT NULL DEFAULT 'electronic'"
        ))

        # 5. 删除已迁出的列。必须在第 3 步之后，否则数据丢失
        for column in ('value', 'package', 'tolerance', 'datasheet_url'):
            conn.execute(text(f'ALTER TABLE items DROP COLUMN {column}'))

        # 6. 子表外键列改名（RENAME COLUMN 会同步更新外键定义里的列名）
        # 必须用同一连接读列信息：事务内的 DDL 对其他连接不可见
        for table in ('transactions', 'expenses', 'maintenances', 'bom_items'):
            if table not in tables:
                continue
            columns = {row[1] for row in conn.execute(text(f'PRAGMA table_info({table})'))}
            if 'component_id' in columns:
                conn.execute(text(
                    f'ALTER TABLE {table} RENAME COLUMN component_id TO item_id'
                ))

        # 7. 索引名同步：SQLite 不重命名索引，旧名会一直误导维护者
        if 'maintenances' in tables:
            mcols = {row[1] for row in conn.execute(text('PRAGMA table_info(maintenances)'))}
            if 'item_id' in mcols:
                conn.execute(text('DROP INDEX IF EXISTS ix_maintenances_component_id'))
                conn.execute(text(
                    'CREATE INDEX IF NOT EXISTS ix_maintenances_item_id ON maintenances (item_id)'
                ))

    current_app.logger.info('已迁移 components -> items，并拆分 item_specs')


def register_error_handlers(app):
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({'code': 404, 'message': '接口不存在', 'data': None}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({'code': 405, 'message': '请求方法不允许', 'data': None}), 405

    @app.errorhandler(413)
    def payload_too_large(e):
        limit_mb = int(app.config.get('MAX_CONTENT_LENGTH', 0) / 1024 / 1024)
        return jsonify({
            'code': 413,
            'message': f'上传内容过大（上限 {limit_mb}MB）',
            'data': None,
        }), 413

    @app.errorhandler(500)
    def internal_error(e):
        app.logger.exception('未捕获的服务器异常')
        return jsonify({'code': 500, 'message': '服务器内部错误', 'data': None}), 500


def seed_admin():
    """初始化管理员账号（用户名/密码来自环境变量），仅当不存在时创建。

    多进程（如 gunicorn 多 worker）同时启动时会并发走到这里：先查后插存在竞态，
    两个进程都查不到就会都去插入，后插入的撞 users.username 唯一约束。
    这里捕获并忽略——种子数据的语义是「有则不动」，重复插入不算错误，
    让先提交的那个生效即可。若把异常抛出去，worker 会退出，整个服务启动失败。
    """
    username = current_app.config.get('ADMIN_USERNAME', 'admin')
    password = current_app.config.get('ADMIN_PASSWORD', 'admin123')
    email = current_app.config.get('ADMIN_EMAIL', 'admin@example.com')
    if User.query.filter_by(username=username).first() is not None:
        return

    admin = User(
        username=username,
        password_hash=hash_password(password),
        role='admin',
        email=email,
    )
    db.session.add(admin)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()


def seed_categories():
    """初始化常用元器件分类树，仅补充缺失项，不覆盖已有分类。"""
    def add_node(name, parent_id):
        node = Category.query.filter_by(name=name, parent_id=parent_id).first()
        if node is None:
            node = Category(name=name, parent_id=parent_id)
            db.session.add(node)
            db.session.flush()
        return node

    def build(items, parent_id=None):
        for item in items:
            if isinstance(item, str):
                add_node(item, parent_id)
            else:
                name, children = item
                node = add_node(name, parent_id)
                build(children, node.id)

    build(COMMON_CATEGORIES)
    db.session.commit()


app = create_app()


if __name__ == '__main__':
    host = os.getenv('APP_HOST', '0.0.0.0')
    port = int(os.getenv('APP_PORT', '5000'))
    app.run(host=host, port=port, debug=os.getenv('FLASK_DEBUG', '1') == '1')
