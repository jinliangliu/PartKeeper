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

## MCP 对外通信（供 WorkBuddy 连接器访问）

PartKeeper 提供独立的 MCP Server（Streamable HTTP + Bearer 认证），与 Web Server 共享同一 SQLite 数据库，供 WorkBuddy 自定义连接器调用物料查询、统计与出入库能力。

### 启动

```powershell
# 单独启动 MCP Server（默认 0.0.0.0:8000，端点 /mcp）
powershell -ExecutionPolicy Bypass -File .\start_mcp.ps1

# 或使用一键脚本（会同时拉起前端、后端与 MCP Server）
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

### 认证

所有请求需在 Header 携带 `Authorization: Bearer <MCP_API_KEY>`。密钥来自 `backend/.env` 的 `MCP_API_KEY`；留空时仅接受用 `SECRET_KEY` 签发、`role=admin` 的 JWT。未携带或无效 token 返回 `401`。

### 可用工具（27 个）

| 工具 | 说明 |
|------|------|
| `list_components` | 物料列表，支持关键词/分类/低库存过滤 |
| `get_component` | 按 ID 查物品详情（含消耗品/保修/维护属性） |
| `create_component` | 新建物品档案，分类/库位/供应商按名称自动关联；支持消耗品与保修维护字段 |
| `list_low_stock` | 低库存预警清单 |
| `get_replenishment_suggestions` | 消耗品补货建议：按消耗速率估算剩余天数、建议补货量与紧急度 |
| `list_expiring_warranties` | 保修到期与维护到期扫描（含已过期） |
| `list_categories` | 分类树 |
| `list_suppliers` / `list_locations` | 供应商 / 库位 |
| `list_transactions` | 库存流水（按类型、日期过滤） |
| `get_stats_overview` | 库存与采购/消耗总览 |
| `get_purchase_ranking` / `get_consumption_ranking` | 采购 / 消耗排行 |
| `get_monthly_trend` | 月度趋势 |
| `get_purchase_spend` | 采购支出看板：月度金额、分类/供应商排行、最大开销月 |
| `stock_in` / `stock_out` | 入库 / 出库（记录操作人为 `MCP_OPERATOR_ID`） |
| `record_utility_bills` | 批量录入水电煤等生活缴费账单（自动去重，返回新增/重复/失败明细） |
| `list_utility_bills` | 查询缴费账单明细（按类型/日期过滤） |
| `delete_utility_bill` | 删除误录账单（纠错用） |
| `get_utility_spend` | 缴费支出归总：月度趋势 + 按类型/收款方汇总 |
| `record_expenses` | 批量录入教育/培训/旅行/娱乐/购物/医疗等各类开支（自动去重，可登记凭证） |
| `attach_expense_receipt` | 给已有开支补挂凭证图片（自动剥离 EXIF/GPS，按内容哈希去重） |
| `list_expenses` | 查询开支明细（按类型/子类/商户/渠道/日期/关键词过滤，附凭证） |
| `delete_expense` | 删除误录开支（纠错用，磁盘文件保留） |
| `get_expense_spend` | 开支归总：月度趋势（零填充）+ 按类型/子类/商户/渠道汇总 |
| `get_household_spend_overview` | 家庭总支出看板：合并缴费与开支，总额/月度/分类排行 |

### 家庭场景字段说明

`create_component` 支持以下可选属性，供补货提醒与维护提醒使用：

| 字段 | 类型 | 说明 |
|------|------|------|
| `is_consumable` | bool | 是否消耗品，补货建议默认只扫描标记为 true 的物品 |
| `consumption_rate` | float | 消耗速率（单位/天）；留空则从最近 90 天出库流水自动推算 |
| `warranty_expiry` | date | 保修到期日，格式 `YYYY-MM-DD` |
| `maintenance_cycle_days` | int | 维护周期（天） |
| `last_maintenance_date` | date | 上次维护日期，格式 `YYYY-MM-DD` |

这 5 个字段是与物品类型无关的通用属性，后续模型重构为 `Item` 主表 + 类型扩展表时可直接平移。已有数据库在应用启动时由 `backend/app.py` 的 `migrate()` 自动补列，无需手工处理。

### 生活缴费账单（各渠道缴费截图）

在 WorkBuddy 中直接发支付宝、微信、银行代扣等任意渠道的生活缴费清单截图，说明「录入这些缴费」，模型会从图中提取账单并调用 `record_utility_bills` 批量写入。

**渠道字段 `channel`**：`alipay`（支付宝）、`wechat`（微信）、`bank`（银行代扣）、`cash`（现金）、`other`（其他，默认）。兼容中文传参——「支付宝」「微信」「银行代扣」「现金」会自动归一化到对应英文值。

**去重机制**（避免同一笔交易在多张截图中重复计入）：
1. 有渠道交易单号（`external_id`）时，以「渠道 + 单号」为键——**同一串单号在支付宝和微信属于两笔不同交易，不会误合并**。
2. 无单号时，以「渠道 + 类型 + 金额（精确到分）+ 缴费日期 + 收款方」规范化取 SHA-256。同日不同时刻视为同一笔，不同日期或不同收款方不合并。

每条账单支持 `category`（water/electricity/gas/internet/phone/other）、`amount`、`paid_at`、`channel`、`period`、`counterparty`、`external_id`、`source`、`note`。录入结果按「新增 / 重复跳过 / 格式失败」三类分别返回，重复项不会写入也不会报错。

误录时用 `list_utility_bills`（支持按 category/channel/日期过滤）找到 `id`，再调 `delete_utility_bill` 删除即可。统计用 `get_utility_spend`，`group` 可选 `category`（按水电煤类型）、`counterparty`（按收款方）、`channel`（按缴费渠道）。

### 家庭各类开支（教育/培训/旅行/娱乐等）

水电煤等**生活缴费**走 `utility_bills`；其余开支（教育、培训、旅行、娱乐、购物、医疗、餐饮、交通、居住、数码、其他）走 `expenses` 表。两表物理分开、统计时归一——生活缴费有「账期」「收款方」这类特化语义，混进同一张表会让字段全部变可空、语义崩坏。

同一笔支出**只记一处**。若既记入缴费又记入开支，`get_household_spend_overview` 会重复计算。

```text
把这几笔开支记一下：
- 英语培训 3800，新东方，微信，9月1日
- 机票 1860，携程，支付宝，10月2日
- 电影票 96，万达影城，微信，10月5日
```

模型会调用 `record_expenses` 批量写入。每条支持：

| 字段 | 必填 | 说明 |
|------|------|------|
| `category` | 是 | 中文或英文均可，如 `教育`/`education`、`旅行`/`travel` |
| `amount` | 是 | 金额（元），必须大于 0 |
| `occurred_at` | 是 | 消费发生时间，`YYYY-MM-DD` 或 `YYYY-MM-DD HH:MM` |
| `subcategory` | 否 | 自由文本细分，如「英语培训」「机票」「电影」 |
| `merchant` | 否 | 商户 / 机构 / 平台 |
| `channel` | 否 | `alipay`/`wechat`/`bank`/`cash`/`other`，兼容中文 |
| `external_id` | 否 | 渠道交易单号，填了可跨截图可靠去重 |
| `tags` | 否 | 标签，列表或逗号分隔，如 `孩子,暑期` |
| `receipt_path` | 否 | 凭证图片路径（指向磁盘已有文件），登记 SHA-256/大小/MIME |

**去重**：有单号用「渠道 + 单号」；无单号用「渠道 + 类型 + 金额 + 日期 + 商户」取 SHA-256，同日不同时刻视为同一笔。

**统计**：`get_expense_spend(months, group)` 的 `group` 可选 `category`/`subcategory`/`merchant`/`channel`；`get_household_spend_overview(months)` 给出家庭总支出（缴费 + 开支）、月度趋势与分类排行。

**凭证图片**：支持两种入口——Web 端「家庭开支」页面直接上传（推荐），或由 MCP 的 `record_expenses` / `attach_expense_receipt` 登记磁盘上已存在的文件。两条通道走同一套存储服务，都做格式白名单、10MB 上限、**EXIF/GPS 剥离**、按内容 SHA-256 命名，相同图片只存一份。详见下节。

### 凭证图片的存储与隐私

票据、缴费截图可以挂在开支上。存储策略有三条硬约束：

1. **二进制不进数据库**。文件落磁盘（`backend/instance/uploads/`，已被 git 忽略、不经静态文件服务暴露），库里只存相对路径 + SHA-256 + 大小 + MIME。SQLite 存 BLOB 会让库迅速膨胀、拖慢备份迁移。
2. **必须剥离 EXIF**。手机照片带 GPS 坐标与设备型号，直接存等于把家庭住址写进账本。上传时统一「解码 → 按 Orientation 转正 → 重编码」，新文件不含任何原始元数据（仅保留 ICC 色彩配置，避免广色域偏色）。
3. **按内容哈希命名**。磁盘用 `<sha256 前2位>/<sha256>.<ext>`，不保留原始文件名（"张三的电费.jpg" 本身就是泄露）。同一张图重复上传/多处引用只占一份空间。

接口（均需 `Authorization: Bearer <JWT>`）：

| 方法与路径 | 说明 |
|-----------|------|
| `GET /api/expenses` | 分页列表，支持 `category`/`channel`/`merchant`/`keyword`/`start`/`end` |
| `GET /api/expenses/<id>` | 单条详情（含凭证） |
| `POST /api/expenses` | 新建（JSON；重复返回 409） |
| `DELETE /api/expenses/<id>` | 删除开支（凭证文件保留，可用 gc 清理） |
| `GET /api/expenses/stats?months=` | 总额 / 月度趋势 / 类型排行 |
| `GET /api/expenses/meta` | 类型、渠道选项与上传限制 |
| `POST /api/expenses/<id>/attachments` | 上传凭证（multipart，字段名 `file`） |
| `GET /api/expenses/attachments/<id>/file` | 读取凭证（**走鉴权**，非静态目录） |
| `DELETE /api/expenses/attachments/<id>?purge_file=1` | 删除凭证记录；无其他引用时一并删文件 |
| `POST /api/expenses/attachments/gc` | 管理员清理孤儿文件，需 `{"confirm": true}` |

格式限 JPG / PNG / WEBP，单张 ≤ 10MB（`MAX_CONTENT_LENGTH` 12MB 兜底）。前端页面在侧边栏「家庭开支」，凭证缩略图通过带 token 的请求取回后转 blob URL 显示，避免链接外泄即可访问。

### WorkBuddy 接入

在 `~/.workbuddy/mcp.json` 的 `mcpServers` 中增加：

```json
"partkeeper": {
  "type": "streamableHttp",
  "url": "http://127.0.0.1:8000/mcp",
  "headers": {
    "Authorization": "Bearer <MCP_API_KEY>"
  },
  "timeout": 60000
}
```

修改 `mcp.json` 后需重启 WorkBuddy 会话使其生效。若更换了 `MCP_API_KEY`，须同步更新此处的 token。
