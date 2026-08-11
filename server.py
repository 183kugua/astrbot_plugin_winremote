"""WinRemote HTTP 服务器（修复 chunk 传输 bug）"""
import json
import asyncio
import logging
from typing import Dict, Any, Callable, Optional
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import threading
import base64

logger = logging.getLogger(__name__)


class WinRemoteHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器"""
    
    # 路由表：{path: {method: handler}}
    routes: Dict[str, Dict[str, Callable]] = {}
    auth_manager = None
    tool_handlers: Dict[str, Callable] = {}
    
    def log_message(self, format, *args):
        """抑制默认日志输出"""
        logger.debug(f"HTTP: {format % args}")
    
    def _send_json_response(self, data: dict, status: int = 200):
        """发送 JSON 响应（修复 chunk 传输）"""
        response_body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(response_body)))
        self.send_header('Connection', 'close')
        self.end_headers()
        
        # 直接发送完整响应，不用 chunked 编码
        self.wfile.write(response_body)
    
    def _send_error_response(self, message: str, status: int = 400):
        """发送错误响应"""
        self._send_json_response({
            "success": False,
            "error": message
        }, status)
    
    def _send_image_response(self, image_data: bytes, format: str = "PNG"):
        """发送图片响应"""
        self.send_response(200)
        self.send_header('Content-Type', f'image/{format.lower()}')
        self.send_header('Content-Length', str(len(image_data)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(image_data)
    
    def _check_auth(self) -> bool:
        """检查认证"""
        auth_header = self.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            self._send_error_response("缺少认证头", 401)
            return False
        
        token = auth_header[7:]
        if self.auth_manager:
            is_valid, error = self.auth_manager.validate_token(token)
            if not is_valid:
                self._send_error_response(error, 401)
                return False
        return True
    
    def _get_request_body(self) -> dict:
        """获取请求体"""
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            return {}
        
        body = self.rfile.read(content_length)
        try:
            return json.loads(body.decode('utf-8'))
        except json.JSONDecodeError:
            return {}
    
    def do_GET(self):
        """处理 GET 请求"""
        if not self._check_auth():
            return
        
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        
        # 检查路由
        if path in self.routes and 'GET' in self.routes[path]:
            try:
                handler = self.routes[path]['GET']
                result = handler(query=query)
                self._send_json_response(result)
            except Exception as e:
                logger.exception(f"GET {path} 错误")
                self._send_error_response(str(e), 500)
        else:
            self._send_error_response("未找到路由", 404)
    
    def do_POST(self):
        """处理 POST 请求"""
        if not self._check_auth():
            return
        
        parsed = urlparse(self.path)
        path = parsed.path
        
        # 检查路由
        if path in self.routes and 'POST' in self.routes[path]:
            try:
                body = self._get_request_body()
                handler = self.routes[path]['POST']
                result = handler(data=body)
                
                # 检查是否返回图片
                if isinstance(result, dict) and 'image_data' in result:
                    image_data = base64.b64decode(result['image_data'])
                    self._send_image_response(image_data, result.get('image_format', 'PNG'))
                else:
                    self._send_json_response(result)
            except Exception as e:
                logger.exception(f"POST {path} 错误")
                self._send_error_response(str(e), 500)
        else:
            self._send_error_response("未找到路由", 404)


class WinRemoteServer:
    """WinRemote HTTP 服务器"""
    
    def __init__(self, host: str = '0.0.0.0', port: int = 8765):
        self.host = host
        self.port = port
        self.server: Optional[HTTPServer] = None
        self.thread: Optional[threading.Thread] = None
        self.running = False
    
    def register_route(self, path: str, method: str, handler: Callable):
        """注册路由"""
        if path not in WinRemoteHandler.routes:
            WinRemoteHandler.routes[path] = {}
        WinRemoteHandler.routes[path][method] = handler
        logger.info(f"注册路由：{method} {path}")
    
    def register_tool_handler(self, tool_name: str, handler: Callable):
        """注册工具处理器"""
        WinRemoteHandler.tool_handlers[tool_name] = handler
    
    def set_auth_manager(self, auth_manager):
        """设置认证管理器"""
        WinRemoteHandler.auth_manager = auth_manager
    
    def start(self):
        """启动服务器"""
        if self.running:
            logger.warning("服务器已在运行")
            return
        
        try:
            self.server = HTTPServer((self.host, self.port), WinRemoteHandler)
            self.running = True
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
            logger.info(f"WinRemote 服务器启动于 {self.host}:{self.port}")
        except Exception as e:
            logger.exception(f"服务器启动失败：{e}")
            raise
    
    def _run(self):
        """运行服务器"""
        while self.running:
            self.server.handle_request()
    
    def stop(self):
        """停止服务器"""
        self.running = False
        if self.server:
            self.server.shutdown()
            self.server = None
        if self.thread:
            self.thread.join(timeout=5)
            self.thread = None
        logger.info("WinRemote 服务器已停止")
