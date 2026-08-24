# PartKeeper 电子元器件物料管理系统

轻量级 B/S 架构物料管理系统，用于个人或小团队管理电子元器件库存。

## 技术栈

- 前端：Vue 3 + Element Plus + Axios + Vue Router + Vite
- 后端：Python 3.10+ + Flask + Flask-SQLAlchemy
- 数据库：SQLite 3（单文件，零部署）
- 认证：JWT（前后端分离）

## 系统架构

![PartKeeper 运行时架构](docs/partkeeper-architecture.png)

> 矢量源文件见 [docs/partkeeper.svg](docs/partkeeper.svg)。

## 目录结构

```
PartKeeper/
├── backend/            # Flask 后端
│   ├── app.py          # 应用入口（工厂函数、蓝图注册、建表、种子管理员）
│   ├── config/         # 配置
│   ├── models/         # SQLAlchemy 模型
│   ├── routes/         # 控制器层
│   ├── services/       # 业务逻辑层（库存过账）
│   ├── utils/          # 工具（JWT、密码、装饰器）
│   └── .env.example    # 环境变量示例
├── frontend/           # Vue 3 前端
└── docs/               # 文档与架构图
    ├── 物料管理系统开发规划.md   # 设计方案与实现说明
    ├── 使用说明.md              # 使用说明
    └── partkeeper.svg / partkeeper-architecture.png   # 运行时架构图
```

## 快速开始

### 1. 配置环境变量

本项目使用 SQLite，无需单独安装数据库服务。首次启动会自动在 `backend/instance/` 下生成数据库文件。

复制环境变量模板并按需修改（`.env` 不会被提交到仓库）：

```bash
cd backend
copy .env.example .env    # macOS/Linux: cp .env.example .env
```

### 2. 启动后端

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate   macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

后端默认运行在 `http://localhost:5000`，启动时会自动建表、补充常用分类并创建初始管理员。

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端默认运行在 `http://localhost:5173`，开发服务器已配置将 `/api` 请求代理到后端 `http://localhost:5000`。

## 默认账号

| 用户名 | 密码 | 角色 |
|--------|------|------|
| admin  | admin123 | 管理员 |

> 以上为本地开发默认值，可通过 `backend/.env` 中的 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 修改；生产或正式使用前请务必更换 `SECRET_KEY` 和管理员密码。`.env` 已被 `.gitignore` 排除，不会提交到仓库。

更详细的功能使用说明见 [使用说明.md](docs/使用说明.md)。

## 主要功能

- 物料管理：多条件搜索、分页、CRUD，关联分类/库位/供应商
- BOM 导入：上传常见 EDA 导出的 CSV 物料清单，自动匹配现有库存、标记缺口，并可一键创建缺失物料
- BOM 管理：维护常用物料清单（物料 + 数量），出库时可选 BOM 批量出库，批量表格支持增删改数量
- 分类管理：树形多级分类
- 供应商 / 库位管理：CRUD
- 入库 / 出库操作：自动更新库存，出库校验库存；入库支持记录可选单价
- 库存流水：按物料、类型、时间段过滤
- 低库存预警：高亮展示低于阈值的物料
- 统计分析：采购 / 消耗概览、月度趋势、Top 组件、供应商与分类金额分布、库存估值；支持按时间范围筛选并导出 CSV
- 用户管理：管理员专属，角色区分

## 统一 API 返回格式

```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

主要接口前缀为 `/api`，详见 [物料管理系统开发规划.md](docs/物料管理系统开发规划.md) 第 6 节。
