# PartKeeper EasyEDA 扩展

读取当前原理图的元件清单，提交给 PartKeeper 匹配库存。

## 前提

- EasyEDA **标准版**（专业版是另一套 TypeScript 扩展体系，本扩展不适用）
- PartKeeper 服务可访问；CORS 已由后端放开（`/api/*` 允许任意来源，鉴权靠 Bearer 令牌）
- Web 端「访问令牌」页生成令牌

## 安装

1. EasyEDA 顶部菜单「设置 → 扩展 → 扩展管理器」；
2. 选择「加载扩展」，选中本目录（含 `extension.json` 与 `main.js`）；
3. 刷新编辑器。

## 使用

首次运行会弹窗要求填写：

- **服务器地址**：如 `http://127.0.0.1:8090`
- **访问令牌**：`pk_` 开头，从 Web「访问令牌」页生成

设置存在浏览器 `localStorage`。之后在扩展菜单里执行「PartKeeper：匹配库存」即可。结果以 toast 汇总，明细打印在浏览器控制台。

## 菜单注册失败怎么办

EasyEDA 各版本扩展 API 的方法名不一致，脚本已做能力检测。若菜单项没有出现：

1. 打开浏览器控制台（F12）；
2. 执行 `window.partkeeperRun()` 触发匹配，`window.partkeeperSettings()` 重新配置地址与令牌。

## 适配其他版本

采集函数 `collectComponents()` 依赖 `eda.sch_PrimitiveComponent.getAll()`，并对字段名做了多键兼容（`designator` / `ref` / `name` / `value` / `device` / `footprint`）。如果你的版本方法名不同，只改这一个函数即可，其余逻辑（聚合、请求、结果展示）不用动。
