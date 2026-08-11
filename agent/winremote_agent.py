"""WinRemote Agent - 运行在 Windows 远程电脑上"""
import os
import sys
import json
import socket
import logging
import subprocess
import threading
import time
from datetime import datetime
from typing import Optional, Dict, Any
import base64
import pyautogui
from PIL import Image
import io

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("winremote_agent")


class WinRemoteAgent:
    """WinRemote Agent 主类"""
    
    def __init__(self, config_path: str = "agent_config.json"):
        self.config = self._load_config(config_path)
        self.agent_id = self.config.get("agent_id", self._generate_agent_id())
        self.server_url = self.config.get("server_url", "http://localhost:8765")
        self.heartbeat_interval = self.config.get("heartbeat_interval", 30)
        self.running = False
        self.heartbeat_thread: Optional[threading.Thread] = None
    
    def _load_config(self, config_path: str) -> dict:
        """加载配置文件"""
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        # 返回默认配置
        return {
            "agent_id": self._generate_agent_id(),
            "server_url": "http://localhost:8765",
            "heartbeat_interval": 30,
            "auth_token": ""
        }
    
    def _generate_agent_id(self) -> str:
        """生成 Agent ID"""
        import uuid
        hostname = socket.gethostname()
        return f"{hostname}-{uuid.uuid4().hex[:8]}"
    
    def _save_config(self, config_path: str):
        """保存配置文件"""
        config = {
            "agent_id": self.agent_id,
            "server_url": self.server_url,
            "heartbeat_interval": self.heartbeat_interval,
            "auth_token": self.config.get("auth_token", "")
        }
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    
    def start(self):
        """启动 Agent"""
        logger.info(f"启动 WinRemote Agent: {self.agent_id}")
        self.running = True
        
        # 启动心跳线程
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()
        
        logger.info("Agent 启动完成")
    
    def stop(self):
        """停止 Agent"""
        self.running = False
        if self.heartbeat_thread:
            self.heartbeat_thread.join(timeout=5)
        logger.info("Agent 已停止")
    
    def _heartbeat_loop(self):
        """心跳循环"""
        while self.running:
            try:
                self._send_heartbeat()
            except Exception as e:
                logger.error(f"心跳发送失败：{e}")
            time.sleep(self.heartbeat_interval)
    
    def _send_heartbeat(self):
        """发送心跳"""
        import requests
        
        heartbeat_data = {
            "agent_id": self.agent_id,
            "status": "online",
            "timestamp": datetime.now().isoformat(),
            "hostname": socket.gethostname(),
            "username": os.getlogin() if hasattr(os, 'getlogin') else "unknown"
        }
        
        headers = {
            "Authorization": f"Bearer {self.config.get('auth_token', '')}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(
                f"{self.server_url}/api/agent/heartbeat",
                json=heartbeat_data,
                headers=headers,
                timeout=10
            )
            if response.status_code == 200:
                logger.debug("心跳发送成功")
        except requests.exceptions.RequestException as e:
            logger.warning(f"心跳请求失败：{e}")
    
    # ========== 工具实现 ==========
    
    def execute_shell(self, command: str) -> dict:
        """执行 CMD 命令"""
        logger.info(f"执行 CMD: {command}")
        start_time = time.time()
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
                encoding='utf-8',
                errors='replace'
            )
            
            elapsed_ms = int((time.time() - start_time) * 1000)
            
            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr,
                "execution_time_ms": elapsed_ms
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "命令执行超时 (60 秒)",
                "execution_time_ms": 60000
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "execution_time_ms": 0
            }
    
    def execute_powershell(self, command: str) -> dict:
        """执行 PowerShell 命令"""
        logger.info(f"执行 PowerShell: {command}")
        start_time = time.time()
        
        try:
            ps_command = f"powershell -Command \"{command}\""
            result = subprocess.run(
                ps_command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
                encoding='utf-8',
                errors='replace'
            )
            
            elapsed_ms = int((time.time() - start_time) * 1000)
            
            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr,
                "execution_time_ms": elapsed_ms
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "execution_time_ms": 0
            }
    
    def take_screenshot(self, format: str = "PNG", quality: int = 75) -> dict:
        """截取屏幕截图"""
        logger.info(f"截取截图 (格式：{format}, 质量：{quality})")
        
        try:
            screenshot = pyautogui.screenshot()
            
            # 转换为字节
            buffer = io.BytesIO()
            if format.upper() == "JPEG":
                screenshot.save(buffer, format="JPEG", quality=quality)
            else:
                screenshot.save(buffer, format="PNG")
            
            image_data = buffer.getvalue()
            
            return {
                "success": True,
                "image_data": base64.b64encode(image_data).decode('utf-8'),
                "image_format": format.upper()
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def send_keypress(self, keys: str) -> dict:
        """模拟键盘按键"""
        logger.info(f"模拟按键：{keys}")
        
        try:
            # 解析按键组合
            key_list = keys.lower().split('+')
            
            # 映射特殊按键
            key_map = {
                'ctrl': 'ctrl',
                'alt': 'alt',
                'shift': 'shift',
                'win': 'command',
                'enter': 'enter',
                'space': 'space',
                'tab': 'tab',
                'esc': 'esc',
                'backspace': 'backspace',
                'delete': 'delete',
                'home': 'home',
                'end': 'end',
                'pageup': 'pageup',
                'pagedown': 'pagedown',
                'up': 'up',
                'down': 'down',
                'left': 'left',
                'right': 'right',
            }
            
            # 处理组合键
            if len(key_list) > 1:
                pyautogui.hotkey(*[key_map.get(k, k) for k in key_list])
            else:
                key = key_map.get(key_list[0], key_list[0])
                pyautogui.press(key)
            
            return {"success": True, "message": f"按键已发送：{keys}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def send_mouse(self, button: str, x: int, y: int) -> dict:
        """模拟鼠标操作"""
        logger.info(f"模拟鼠标：{button} at ({x}, {y})")
        
        try:
            # 移动到位置
            pyautogui.moveTo(x, y, duration=0.3)
            
            # 执行点击
            if button == "click":
                pyautogui.click()
            elif button == "right":
                pyautogui.rightClick()
            elif button == "double":
                pyautogui.doubleClick()
            # move 只移动不点击
            
            return {"success": True, "message": f"鼠标操作完成：{button} at ({x}, {y})"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def open_target(self, target: str) -> dict:
        """打开程序/文件/URL"""
        logger.info(f"打开：{target}")
        
        try:
            if target.startswith("http://") or target.startswith("https://"):
                # 打开 URL
                os.startfile(target)
            else:
                # 打开程序或文件
                os.startfile(target)
            
            return {"success": True, "message": f"已打开：{target}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def type_text(self, text: str) -> dict:
        """模拟键盘输入文本"""
        logger.info(f"输入文本：{text[:50]}...")
        
        try:
            pyautogui.write(text, interval=0.05)
            return {"success": True, "message": f"文本已输入"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_status(self) -> dict:
        """获取 Agent 状态"""
        return {
            "agent_id": self.agent_id,
            "status": "online" if self.running else "offline",
            "hostname": socket.gethostname(),
            "username": os.getlogin() if hasattr(os, 'getlogin') else "unknown",
            "timestamp": datetime.now().isoformat()
        }


def main():
    """主入口"""
    agent = WinRemoteAgent()
    
    # 保存配置示例
    if not os.path.exists("agent_config.json"):
        agent._save_config("agent_config.example.json")
        logger.info("已创建配置示例文件：agent_config.example.json")
    
    try:
        agent.start()
        
        # 保持运行
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在停止...")
    finally:
        agent.stop()


if __name__ == "__main__":
    main()
