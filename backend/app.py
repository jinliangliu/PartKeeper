"""PartKeeper 后端应用入口。

职责：创建 Flask 应用、初始化数据库与 CORS、注册所有蓝图、初始化管理员账号。
"""
import os
import sys

# 保证 `python app.py` 或从项目根目录运行时都能正确导入 backend 包内模块
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from flask import Flask, jsonify, current_app
from flask_cors import CORS
from sqlalchemy import inspect, text

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
        db.create_all()
        migrate()
        seed_admin()
        seed_categories()

    return app


def migrate():
    """轻量迁移：为已存在的表补充新增字段，避免重建库丢失数据。

    create_all() 只会建缺失的表，不会给已有表加列；这里用 ALTER TABLE 补齐。
    每列都先检查是否已存在，保证重复启动幂等。
    """
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())

    # 列定义：表名 -> [(列名, SQLite 列类型与默认值), ...]
    additions = {
        'transactions': [
            ('unit_price', 'FLOAT'),
        ],
        'components': [
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
            ('component_id', 'INTEGER'),
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
    """初始化管理员账号（用户名/密码来自环境变量），仅当不存在时创建。"""
    username = current_app.config.get('ADMIN_USERNAME', 'admin')
    password = current_app.config.get('ADMIN_PASSWORD', 'admin123')
    email = current_app.config.get('ADMIN_EMAIL', 'admin@example.com')
    if User.query.filter_by(username=username).first() is None:
        admin = User(
            username=username,
            password_hash=hash_password(password),
            role='admin',
            email=email,
        )
        db.session.add(admin)
        db.session.commit()


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
