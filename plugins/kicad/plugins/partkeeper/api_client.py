"""PartKeeper REST 客户端（仅标准库）。

不依赖 requests：KiCad 自带的 Python 环境不一定装了第三方包，插件的安装
体验应当是「解压即可用」，不能让用户先去 pip install。
"""

import json
import urllib.error
import urllib.request


class PartKeeperError(Exception):
    """可直接展示给用户的错误。"""


class Client:
    def __init__(self, base_url, token, timeout=30):
        self.base_url = (base_url or '').rstrip('/')
        self.token = (token or '').strip()
        self.timeout = timeout

    def _request(self, method, path, payload=None):
        if not self.base_url:
            raise PartKeeperError('未配置服务器地址')
        if not self.token:
            raise PartKeeperError('未配置访问令牌')

        url = f'{self.base_url}{path}'
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header('Authorization', f'Bearer {self.token}')
        if data is not None:
            req.add_header('Content-Type', 'application/json')

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode('utf-8', errors='replace')
            try:
                message = json.loads(raw).get('message') or raw
            except ValueError:
                message = raw
            if exc.code == 401:
                message = '令牌无效或已撤销，请在设置中重新填写访问令牌'
            raise PartKeeperError(f'HTTP {exc.code}：{message}') from exc
        except urllib.error.URLError as exc:
            raise PartKeeperError(f'无法连接 {self.base_url}：{exc.reason}') from exc
        except json.JSONDecodeError as exc:
            raise PartKeeperError('服务器返回的不是 JSON，请确认地址指向 PartKeeper 服务') from exc

        if body.get('code') != 200:
            raise PartKeeperError(body.get('message') or '请求失败')
        return body.get('data')

    def ping(self):
        """验证地址与令牌，返回当前身份。"""
        return self._request('GET', '/api/integrations/ping')

    def match(self, items, create_missing=False):
        """提交元件清单，返回匹配结果。"""
        return self._request('POST', '/api/integrations/bom/match', {
            'source': 'kicad',
            'create_missing': bool(create_missing),
            'items': items,
        })
