"""KiCad 插件主体：读取当前 PCB 元件，调用 PartKeeper 匹配库存。

设计取舍：

- 只看 PCB 上的封装（footprint）。原理图里的 BOM 更完整，但 KiCad 的
  ActionPlugin 运行在 pcbnew 内，拿不到 eeschema 的符号表；PCB 上的
  Value/Footprint 已经足够做库存匹配。
- 按「值 + 封装」聚合后再提交：同一颗 10k/0603 电阻可能有 20 个位号，
  逐行提交会让几十行的板子变成几百行请求。
- 设置存 ~/.partkeeper/kicad.json，令牌明文写在本地文件——它是可撤销的
  访问令牌，不是账号密码；撤销后重发即可，不必改配置文件结构。
"""

import json
import os

import wx

from .api_client import Client, PartKeeperError

try:
    import pcbnew
    HAS_PCBNEW = True
except ImportError:  # 在 KiCad 之外（如本地语法检查）导入
    pcbnew = None
    HAS_PCBNEW = False

SETTINGS_PATH = os.path.join(os.path.expanduser('~'), '.partkeeper', 'kicad.json')
DEFAULT_BASE_URL = 'http://127.0.0.1:8090'


def load_settings():
    try:
        with open(SETTINGS_PATH, encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    data.setdefault('base_url', DEFAULT_BASE_URL)
    data.setdefault('token', '')
    return data


def save_settings(base_url, token):
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, 'w', encoding='utf-8') as fh:
        json.dump({'base_url': base_url, 'token': token}, fh, ensure_ascii=False, indent=2)


def collect_footprints():
    """按「值 + 封装」聚合当前 PCB 元件。

    返回 [{'value','package','quantity','designators'}]。
    没有 Value 的封装（如纯机械件）跳过——PartKeeper 无法用空值匹配。
    """
    if pcbnew is None:
        raise RuntimeError('当前环境没有 pcbnew，请在 KiCad 的 PCB 编辑器中使用')

    board = pcbnew.GetBoard()
    if board is None:
        raise RuntimeError('没有打开的 PCB 文件')

    grouped = {}
    for fp in board.GetFootprints():
        value = (fp.GetValue() or '').strip()
        if not value:
            continue
        fpid = fp.GetFPID()
        package = str(fpid.GetLibItemName()) if fpid else ''
        key = (value, package)
        entry = grouped.setdefault(key, {
            'value': value,
            'package': package or None,
            'quantity': 0,
            'designators': [],
        })
        entry['quantity'] += 1
        entry['designators'].append(fp.GetReference())

    return sorted(grouped.values(), key=lambda e: (-e['quantity'], e['value']))


class PartKeeperDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title='PartKeeper 库存匹配', size=(900, 620))
        self.result = None
        settings = load_settings()

        panel = wx.Panel(self)
        root = wx.BoxSizer(wx.VERTICAL)

        form = wx.FlexGridSizer(rows=2, cols=2, vgap=8, hgap=8)
        form.AddGrowableCol(1, 1)
        form.Add(wx.StaticText(panel, label='服务器地址'), 0, wx.ALIGN_CENTER_VERTICAL)
        self.url_ctrl = wx.TextCtrl(panel, value=settings['base_url'])
        form.Add(self.url_ctrl, 1, wx.EXPAND)
        form.Add(wx.StaticText(panel, label='访问令牌'), 0, wx.ALIGN_CENTER_VERTICAL)
        self.token_ctrl = wx.TextCtrl(panel, value=settings['token'])
        form.Add(self.token_ctrl, 1, wx.EXPAND)
        root.Add(form, 0, wx.EXPAND | wx.ALL, 12)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.test_btn = wx.Button(panel, label='测试连接')
        self.scan_btn = wx.Button(panel, label='匹配当前板')
        self.create_btn = wx.Button(panel, label='创建缺失物料')
        self.create_btn.Disable()
        buttons.Add(self.test_btn, 0, wx.RIGHT, 8)
        buttons.Add(self.scan_btn, 0, wx.RIGHT, 8)
        buttons.Add(self.create_btn, 0)
        root.Add(buttons, 0, wx.LEFT | wx.RIGHT, 12)

        self.summary = wx.StaticText(panel, label='填写地址与令牌后点「匹配当前板」。')
        root.Add(self.summary, 0, wx.ALL, 12)

        self.list = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        for idx, (title, width) in enumerate([
            ('位号', 230), ('值', 150), ('封装', 130), ('数量', 60), ('状态', 110), ('缺口', 60),
        ]):
            self.list.InsertColumn(idx, title, width=width)
        root.Add(self.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        panel.SetSizer(root)

        self.test_btn.Bind(wx.EVT_BUTTON, self.on_test)
        self.scan_btn.Bind(wx.EVT_BUTTON, self.on_scan)
        self.create_btn.Bind(wx.EVT_BUTTON, self.on_create)

    # --- 事件 ---

    def _client(self):
        base_url = self.url_ctrl.GetValue().strip()
        token = self.token_ctrl.GetValue().strip()
        save_settings(base_url, token)
        return Client(base_url, token)

    def on_test(self, _event):
        try:
            info = self._client().ping()
        except PartKeeperError as exc:
            wx.MessageBox(str(exc), '连接失败', wx.OK | wx.ICON_ERROR)
            return
        wx.MessageBox(f"已连接，当前身份：{info.get('user')}（{info.get('role')}）",
                      '连接正常', wx.OK | wx.ICON_INFORMATION)

    def on_scan(self, _event):
        try:
            entries = collect_footprints()
        except RuntimeError as exc:
            wx.MessageBox(str(exc), '读取 PCB 失败', wx.OK | wx.ICON_ERROR)
            return
        if not entries:
            wx.MessageBox('当前 PCB 没有带 Value 的元件', '无数据', wx.OK | wx.ICON_WARNING)
            return

        try:
            data = self._client().match([
                {
                    'value': e['value'],
                    'package': e['package'],
                    'quantity': e['quantity'],
                    'designator': ', '.join(e['designators'][:6])
                    + ('…' if len(e['designators']) > 6 else ''),
                }
                for e in entries
            ])
        except PartKeeperError as exc:
            wx.MessageBox(str(exc), '匹配失败', wx.OK | wx.ICON_ERROR)
            return

        self.result = data
        self.list.DeleteAllItems()
        for line in data['lines']:
            row = self.list.InsertItem(self.list.GetItemCount(), line.get('designator') or '')
            self.list.SetItem(row, 1, line['value'])
            self.list.SetItem(row, 2, line.get('package') or '')
            self.list.SetItem(row, 3, str(line['quantity']))
            self.list.SetItem(row, 4, '缺料' if not line['matched_id'] else
                              ('库存不足' if line['shortage'] else '库存充足'))
            self.list.SetItem(row, 5, str(line['shortage']))

        summary = data['summary']
        self.summary.SetLabel(
            f"共 {summary['total_lines']} 种 / {summary['total_qty']} 个，"
            f"已匹配 {summary['matched_lines']}，缺失 {summary['missing_lines']}，"
            f"缺口合计 {summary['total_shortage_qty']} 个。"
        )
        self.create_btn.Enable(summary['missing_lines'] > 0)

    def on_create(self, _event):
        if not self.result:
            return
        missing = [l for l in self.result['lines'] if not l['matched_id']]
        if wx.MessageBox(f'将创建 {len(missing)} 个新物品（最低库存=需求数量），继续？',
                         '确认', wx.YES_NO | wx.ICON_QUESTION) != wx.YES:
            return
        try:
            data = self._client().match([
                {'value': l['value'], 'package': l.get('package'), 'quantity': l['quantity']}
                for l in self.result['lines']
            ], create_missing=True)
        except PartKeeperError as exc:
            wx.MessageBox(str(exc), '创建失败', wx.OK | wx.ICON_ERROR)
            return
        wx.MessageBox(f"已创建 {data.get('created', 0)} 个物品，可重新匹配查看结果。",
                      '完成', wx.OK | wx.ICON_INFORMATION)
        self.on_scan(None)


if HAS_PCBNEW:
    class PartKeeperPlugin(pcbnew.ActionPlugin):
        def defaults(self):
            self.name = 'PartKeeper 库存匹配'
            self.category = '库存工具'
            self.description = '读取当前 PCB 元件并与 PartKeeper 库存比对，可一键创建缺失物料'
            self.show_toolbar_button = True
            self.icon_file_name = os.path.join(os.path.dirname(__file__), 'icon.png')

        def Run(self):
            dialog = PartKeeperDialog(None)
            dialog.ShowModal()
            dialog.Destroy()
