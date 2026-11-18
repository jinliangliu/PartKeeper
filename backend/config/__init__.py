import os
from dotenv import load_dotenv

# 允许从任意工作目录运行时也能定位到 backend/.env
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_BASE_DIR, '.env'))

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-me')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True}
    JWT_EXPIRATION_HOURS = int(os.getenv('JWT_EXPIRATION_HOURS', '24'))
    ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')
    ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'admin@example.com')

    # 凭证附件落盘目录（非公开目录，不经静态文件服务暴露，读取需走鉴权接口）
    UPLOAD_DIR = os.getenv('UPLOAD_DIR', os.path.join(_BASE_DIR, 'instance', 'uploads'))
    # 请求体上限：凭证图限制 10MB，留出 multipart 开销余量
    MAX_CONTENT_LENGTH = 12 * 1024 * 1024
