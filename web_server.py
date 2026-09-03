# -*- coding: utf-8 -*-
"""Web 服务精简入口。

实际路由已拆分到 web/ 包下的各功能模块，本文件只负责：
1. 建立运行上下文（项目根、sys.path、工作目录、全局状态）
2. 初始化全局认证与调度器
3. 创建并启动 Flask 应用
"""
import os
import sys

# 保证无论从哪个目录启动，都能找到 web 包（以及后续的 services / dy_apis 等）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from web import context  # noqa: E402  初始化路径/环境上下文

context.init_app()

from web import create_app  # noqa: E402

app = create_app()


if __name__ == '__main__':
    print('Web 服务启动: http://127.0.0.1:5000')
    app.run(host='127.0.0.1', port=5000, debug=False, threaded=True)
