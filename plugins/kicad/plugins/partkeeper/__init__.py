"""KiCad 插件入口：向 pcbnew 注册 ActionPlugin。"""

from .kicad_plugin import HAS_PCBNEW, PartKeeperPlugin

if HAS_PCBNEW:
    _plugin = PartKeeperPlugin()
    # KiCad 8/9 的注册方法大小写不一致，按可用性择一调用
    register = getattr(_plugin, 'register', None) or getattr(_plugin, 'Register')
    register()
