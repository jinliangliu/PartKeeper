/**
 * PartKeeper 库存匹配 —— EasyEDA 扩展（标准版）
 *
 * 读取当前原理图的元件清单，按「值 + 封装」聚合后提交给 PartKeeper 匹配库存。
 *
 * 说明：EasyEDA 标准版扩展运行在浏览器宿主内，API 以全局 `eda` 暴露；
 * 专业版（Pro）是另一套 TypeScript 扩展体系，不在本文件覆盖范围内。
 * 不同版本的方法名可能有差异，所有调用都做了能力检测，缺失时给出明确提示
 * 而不是静默失败。
 *
 * 调试入口：在控制台执行 window.partkeeperRun() 可手动触发一次匹配。
 */
(function () {
  'use strict';

  const STORAGE_KEY = 'partkeeper.settings';
  const DEFAULT_BASE_URL = 'http://127.0.0.1:8090';

  function loadSettings() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        return {
          baseUrl: parsed.baseUrl || DEFAULT_BASE_URL,
          token: parsed.token || ''
        };
      }
    } catch (err) {
      console.warn('[PartKeeper] 读取设置失败', err);
    }
    return { baseUrl: DEFAULT_BASE_URL, token: '' };
  }

  function saveSettings(settings) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  }

  function toast(message) {
    if (typeof eda !== 'undefined' && eda.sys_Message && eda.sys_Message.showToastMessage) {
      eda.sys_Message.showToastMessage(message);
    } else {
      console.log('[PartKeeper]', message);
      alert(message);
    }
  }

  function requestSettings() {
    const current = loadSettings();
    const baseUrl = prompt('PartKeeper 地址', current.baseUrl);
    if (baseUrl === null) return null;
    const token = prompt('访问令牌（Web「访问令牌」页生成，pk_ 开头）', current.token);
    if (token === null) return null;
    const next = { baseUrl: baseUrl.trim(), token: token.trim() };
    saveSettings(next);
    return next;
  }

  async function api(settings, path, options) {
    const res = await fetch(settings.baseUrl.replace(/\/$/, '') + path, {
      method: (options && options.method) || 'GET',
      headers: Object.assign(
        { Authorization: 'Bearer ' + settings.token },
        options && options.body ? { 'Content-Type': 'application/json' } : {}
      ),
      body: options && options.body ? JSON.stringify(options.body) : undefined
    });
    let body = null;
    try {
      body = await res.json();
    } catch (err) {
      throw new Error('服务器返回的不是 JSON，请确认地址指向 PartKeeper');
    }
    if (res.status === 401) throw new Error('令牌无效或已撤销，请重新设置');
    if (!res.ok || body.code !== 200) throw new Error(body.message || 'HTTP ' + res.status);
    return body.data;
  }

  /**
   * 读取当前原理图元件。
   * 标准版 API：eda.sch_PrimitiveComponent.getAll()
   * 返回项通常含 designator / name / device / footprint 等字段；
   * 这里对取值的多种可能字段名做兼容，避免某个版本改名就整体不可用。
   */
  function collectComponents() {
    if (typeof eda === 'undefined') {
      throw new Error('未检测到 EasyEDA 扩展 API（eda），请在 EasyEDA 扩展环境中运行');
    }
    const compApi = eda.sch_PrimitiveComponent;
    if (!compApi || typeof compApi.getAll !== 'function') {
      throw new Error('当前 EasyEDA 版本的 sch_PrimitiveComponent.getAll 不可用，请按 README 调整采集函数');
    }

    const list = compApi.getAll() || [];
    const pick = (obj, keys) => {
      for (const key of keys) {
        const value = obj && obj[key];
        if (value) return String(value).trim();
      }
      return '';
    };

    return list.map((c) => ({
      designator: pick(c, ['designator', 'Designator', 'ref', 'Reference']),
      value: pick(c, ['name', 'Name', 'value', 'Value', 'device', 'Device']),
      package: pick(c, ['footprint', 'Footprint', 'package', 'Package'])
    })).filter((c) => c.value);
  }

  function aggregate(components) {
    const grouped = new Map();
    for (const c of components) {
      const key = c.value + '\u0000' + (c.package || '');
      const entry = grouped.get(key) || {
        value: c.value,
        package: c.package || null,
        quantity: 0,
        designator: ''
      };
      entry.quantity += 1;
      if (c.designator) {
        entry.designator = entry.designator
          ? entry.designator.split(', ').length < 6
            ? entry.designator + ', ' + c.designator
            : entry.designator
          : c.designator;
      }
      grouped.set(key, entry);
    }
    return Array.from(grouped.values());
  }

  async function run(createMissing) {
    let settings = loadSettings();
    if (!settings.token) {
      settings = requestSettings();
      if (!settings || !settings.token) {
        toast('未配置访问令牌');
        return;
      }
    }

    let items;
    try {
      items = aggregate(collectComponents());
    } catch (err) {
      toast(err.message);
      return;
    }
    if (!items.length) {
      toast('当前原理图没有可识别的元件');
      return;
    }

    try {
      const data = await api(settings, '/api/integrations/bom/match', {
        method: 'POST',
        body: { source: 'easyeda', create_missing: !!createMissing, items }
      });
      const s = data.summary;
      let message = '共 ' + s.total_lines + ' 种 / ' + s.total_qty + ' 个；已匹配 '
        + s.matched_lines + '，缺失 ' + s.missing_lines + '，缺口 ' + s.total_shortage_qty;
      if (data.created !== undefined) message += '；已创建 ' + data.created + ' 个物品';
      toast(message);
      console.log('[PartKeeper] 匹配明细', data.lines);
    } catch (err) {
      toast('匹配失败：' + err.message);
    }
  }

  // 暴露给控制台，菜单注册失败时仍可手动调用
  window.partkeeperRun = function () { run(false); };
  window.partkeeperCreateMissing = function () { run(true); };
  window.partkeeperSettings = requestSettings;

  // 尝试注册菜单。不同版本 API 名称不同，全部失败也不阻塞手动入口。
  try {
    if (typeof eda !== 'undefined' && eda.sys_Command && typeof eda.sys_Command.addCommand === 'function') {
      eda.sys_Command.addCommand('partkeeper.match', 'PartKeeper：匹配库存', function () { run(false); });
      eda.sys_Command.addCommand('partkeeper.create', 'PartKeeper：创建缺失物料', function () { run(true); });
    } else {
      console.info('[PartKeeper] 未找到菜单注册 API，可在控制台调用 window.partkeeperRun()');
    }
  } catch (err) {
    console.warn('[PartKeeper] 菜单注册失败，可使用 window.partkeeperRun()', err);
  }
})();
