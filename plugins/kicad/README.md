# PartKeeper KiCad 插件

在 PCB 编辑器里一键读取当前板的元件，提交给 PartKeeper 匹配库存，替代「导出 BOM → 打开网页 → 上传文件」的流程。

## 前提

- KiCad 8.0 及以上（ActionPlugin / wxPython 接口）
- PartKeeper 服务可访问，且已在 Web 端「访问令牌」页生成令牌

## 安装

### 方式一：手动复制（推荐先这样验证）

把 `plugins/kicad/plugins/partkeeper/` 整个目录复制到 KiCad 的用户插件目录：

| 系统 | 路径 |
|------|------|
| Windows | `%APPDATA%\kicad\8.0\scripting\plugins\partkeeper\` |
| Linux | `~/.local/share/kicad/8.0/scripting/plugins/partkeeper/` |
| macOS | `~/Library/Preferences/kicad/8.0/scripting/plugins/partkeeper/` |

重启 KiCad，打开 PCB 编辑器，菜单「工具 → 外部插件」里应出现 **PartKeeper 库存匹配**。

### 方式二：PCM 包

把本目录（含 `metadata.json` 与 `plugins/`）压缩为 zip，通过 KiCad 的 Plugin and Content Manager 添加本地包安装。

## 使用

1. 首次打开对话框，填服务器地址（如 `http://127.0.0.1:8090`）与访问令牌，点「测试连接」；
2. 点「匹配当前板」：插件读取 PCB 上所有带 Value 的封装，按「值 + 封装」聚合后提交；
3. 列表显示每种的库存状态与缺口，「创建缺失物料」会为缺料项建物品（最低库存 = 需求数量）。

设置保存在 `~/.partkeeper/kicad.json`，令牌是可在 Web 端随时撤销的访问令牌。

## 已知限制

- 只读 PCB 上的封装，不读原理图符号表。位号与值以 PCB 为准，适合「板子已经画完」的场景。
- 匹配规则与 Web 端 BOM 导入完全一致：按 `值` 精确匹配（不区分大小写），有封装时优先同封装。
- 若插件未出现在菜单里，检查 KiCad 版本目录名（8.0 / 9.0）是否与安装路径一致，以及 `__init__.py` 是否与其余文件在同一目录。
