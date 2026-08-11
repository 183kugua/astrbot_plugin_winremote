"""WinRemote 工具定义（统一格式）"""
from typing import List, Dict

# 工具元数据定义
TOOLS_METADATA = [
    {
        "name": "win_shell",
        "description": "在远程 Windows 电脑上执行 CMD 命令",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的 CMD 命令，如 'ipconfig /all'"
                }
            },
            "required": ["command"]
        }
    },
    {
        "name": "win_powershell",
        "description": "在远程 Windows 电脑上执行 PowerShell 命令",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "PowerShell 命令，如 'Get-Process'"
                }
            },
            "required": ["command"]
        }
    },
    {
        "name": "win_screenshot",
        "description": "对远程 Windows 桌面进行截图",
        "parameters": {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "enum": ["JPEG", "PNG"],
                    "description": "图片格式"
                },
                "quality": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "description": "JPEG 质量"
                }
            }
        }
    },
    {
        "name": "win_keypress",
        "description": "模拟键盘按键",
        "parameters": {
            "type": "object",
            "properties": {
                "keys": {
                    "type": "string",
                    "description": "按键组合，如 'ctrl+c'"
                }
            },
            "required": ["keys"]
        }
    },
    {
        "name": "win_mouse",
        "description": "模拟鼠标操作",
        "parameters": {
            "type": "object",
            "properties": {
                "button": {
                    "type": "string",
                    "enum": ["click", "right", "double", "move"]
                },
                "x": {
                    "type": "integer",
                    "description": "屏幕 X 坐标"
                },
                "y": {
                    "type": "integer",
                    "description": "屏幕 Y 坐标"
                }
            },
            "required": ["x", "y"]
        }
    },
    {
        "name": "win_open",
        "description": "打开程序、文件或 URL",
        "parameters": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "程序名、文件路径或 URL"
                }
            },
            "required": ["target"]
        }
    },
    {
        "name": "win_type",
        "description": "模拟键盘输入文本",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "要输入的文字内容"
                }
            },
            "required": ["text"]
        }
    },
    {
        "name": "win_agent_status",
        "description": "查看远程 Windows 电脑 Agent 连接状态",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
]


def get_tools_schema() -> List[Dict]:
    """获取工具 Schema 列表"""
    return TOOLS_METADATA


def get_tool_names() -> List[str]:
    """获取所有工具名称"""
    return [t["name"] for t in TOOLS_METADATA]
