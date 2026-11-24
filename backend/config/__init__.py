import os
from dotenv import load_dotenv

# 允许从任意工作目录运行时也能定位到 backend/.env
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_BASE_DIR, '.env'))

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-me')

    # 默认 PostgreSQL（pgvector 语义检索依赖它）。
    # 端口用 5433 而非 5432：同机可能已有其它 PG 实例，不抢占默认端口。
    # 需要临时跑无 PG 环境（如纯 SQLite 单元测试）时，显式设置 DATABASE_URL 覆盖即可。
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL',
        'postgresql+psycopg://partkeeper:partkeeper@127.0.0.1:5433/partkeeper',
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        # 连接池上限压住：gunicorn 多 worker × 每 worker 连接数不要打爆 PG 的 max_connections
        'pool_size': int(os.getenv('DB_POOL_SIZE', '5')),
        'max_overflow': int(os.getenv('DB_MAX_OVERFLOW', '5')),
        'pool_recycle': 1800,
    }

    JWT_EXPIRATION_HOURS = int(os.getenv('JWT_EXPIRATION_HOURS', '24'))
    ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')
    ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'admin@example.com')

    # 语义检索：懒加载模型，首次调用才下载/载入权重。
    # 设为 0 可彻底关闭（SQLite 或低配机器），接口会返回明确的不可用提示。
    EMBEDDING_ENABLED = os.getenv('EMBEDDING_ENABLED', '1') == '1'
    EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL', 'BAAI/bge-small-zh-v1.5')
    # 启动时不自动做全量补齐（大库会拖慢启动），由 /api/components/semantic-reindex 或 CLI 触发
    EMBEDDING_SYNC_ON_STARTUP = os.getenv('EMBEDDING_SYNC_ON_STARTUP', '0') == '1'

    # 凭证附件落盘目录（非公开目录，不经静态文件服务暴露，读取需走鉴权接口）
    UPLOAD_DIR = os.getenv('UPLOAD_DIR', os.path.join(_BASE_DIR, 'instance', 'uploads'))
    # 请求体上限：凭证图限制 10MB，留出 multipart 开销余量
    MAX_CONTENT_LENGTH = 12 * 1024 * 1024

    # 插件直连：允许的跨域来源（EasyEDA 扩展在浏览器宿主内发起请求）。
    # 逗号分隔；默认放开，因为接口本身要求 Bearer 令牌，不依赖来源做鉴权。
    PLUGIN_CORS_ORIGINS = os.getenv('PLUGIN_CORS_ORIGINS', '*')
