# Waitress 配置文件
# Waitress 是 Windows 兼容的 WSGI 服务器
# 使用方式: waitress-serve --call "waitress_config:create_app"

from tr_fill_in_api import app

def create_app():
    """创建应用实例"""
    return app
