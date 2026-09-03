# -*- coding: utf-8 -*-
"""AI 智能混剪 API —— 对接 Smart-Clip MCP 服务（http://127.0.0.1:8000）。"""
import json
import re
import threading

import requests
from flask import Blueprint, request, jsonify
from loguru import logger

bp = Blueprint('ai_clip', __name__)

MCP_BASE = 'http://127.0.0.1:8000'
MCP_TIMEOUT = (5, 900)  # (connect, read)


def _mcp_call(tool_name, arguments):
    """通过 MCP SSE 协议调用 Smart-Clip 工具，返回 JSON-RPC result/error。"""
    sse = requests.get(MCP_BASE + '/sse', stream=True, timeout=MCP_TIMEOUT)
    buf = ''
    for chunk in sse.iter_content(chunk_size=1, decode_unicode=True):
        if not chunk:
            continue
        buf += chunk
        if '\n\n' in buf:
            break

    m = re.search(r'/messages/[^\s]+', buf)
    if not m:
        sse.close()
        raise RuntimeError('无法获取 Smart-Clip MCP 会话')

    endpoint = m.group(0)
    url = MCP_BASE + endpoint

    # 后台线程持续读取 SSE，保持会话存活
    def _drain():
        try:
            for _ in sse.iter_content(chunk_size=1024, decode_unicode=True):
                pass
        except Exception:
            pass

    threading.Thread(target=_drain, daemon=True).start()

    try:
        requests.post(url, json={
            'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
            'params': {
                'protocolVersion': '2024-11-05',
                'capabilities': {},
                'clientInfo': {'name': 'douyin-web', 'version': '1.0'},
            },
        }, timeout=30)

        r = requests.post(url, json={
            'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
            'params': {'name': tool_name, 'arguments': arguments},
        }, timeout=MCP_TIMEOUT)

        return _parse_response(r.text)
    finally:
        sse.close()


def _parse_response(text):
    """解析 MCP 响应：优先按 JSON，否则按 SSE data 行解析。"""
    text = (text or '').strip()
    if not text:
        return {'error': '空响应'}
    try:
        return json.loads(text)
    except Exception:
        pass
    lines = [ln[5:].strip() for ln in text.splitlines() if ln.startswith('data:')]
    if lines:
        try:
            return json.loads(lines[-1])
        except Exception:
            pass
    return {'error': text[:500]}


@bp.route('/api/aiclip/status', methods=['GET'])
def api_aiclip_status():
    """检测 Smart-Clip MCP 服务是否在线。"""
    try:
        r = requests.get(MCP_BASE + '/sse', timeout=(2, 3), stream=True)
        r.close()
        return jsonify({'success': True, 'running': True, 'endpoint': MCP_BASE + '/sse'})
    except Exception as e:
        return jsonify({'success': True, 'running': False, 'error': str(e)})


@bp.route('/api/aiclip/upload', methods=['POST'])
def api_aiclip_upload():
    """上传视频到 Smart-Clip MCP 服务（返回服务端路径）。"""
    f = request.files.get('file')
    if not f:
        return jsonify({'success': False, 'error': '未收到文件'})
    try:
        files = {'file': (f.filename, f.stream, f.content_type or 'application/octet-stream')}
        r = requests.post(MCP_BASE + '/upload', files=files, timeout=60)
        return jsonify(r.json())
    except Exception as e:
        logger.error('上传到 Smart-Clip 失败: {}'.format(e))
        return jsonify({'success': False, 'error': str(e)})


@bp.route('/api/aiclip/clip', methods=['POST'])
def api_aiclip_clip():
    """调用 smart_clip 工具执行智能剪辑。"""
    data = request.get_json(silent=True) or {}
    video_input = (data.get('video_input') or '').strip()
    if not video_input:
        return jsonify({'success': False, 'error': '请先上传视频或填写视频路径/URL'})

    arguments = {
        'video_input': video_input,
        'intent': (data.get('intent') or '提取精彩片段').strip() or '提取精彩片段',
        'clip_count': int(data.get('clip_count') or 5),
        'clip_duration_min': int(data.get('clip_duration_min') or 15),
        'clip_duration_max': int(data.get('clip_duration_max') or 90),
        'platform': (data.get('platform') or 'original').strip() or 'original',
        'with_subtitles': bool(data.get('with_subtitles', True)),
        'with_bgm': bool(data.get('with_bgm', False)),
        'output_dir': './smart-clip-output',
    }

    try:
        resp = _mcp_call('smart_clip', arguments)
    except Exception as e:
        logger.error('调用 Smart-Clip 失败: {}'.format(e))
        return jsonify({'success': False, 'error': str(e)})

    if resp.get('error'):
        return jsonify({'success': False, 'error': str(resp.get('error'))})

    result = resp.get('result') or {}
    content = result.get('content') or []
    text = ''
    for c in content:
        if c.get('type') == 'text':
            text += c.get('text', '')
    try:
        payload = json.loads(text) if text else result
    except Exception:
        payload = {'raw': text or result}

    return jsonify({'success': True, 'data': payload})
