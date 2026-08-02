"""
tools.py — WinRemote v0.9.8 LLM Tool 定义
==========================================
使用 @dataclass 方式定义 Tool（AStrBot v4.5.7+ 推荐）。
插件初始化时通过 context.add_llm_tools(ALL_TOOLS) 注册。

设计原则：
- 每个 Tool 对应一个远程控制能力
- description 详细描述了适用场景，帮助 LLM 正确选择
- parameters 使用 JSON Schema 格式，与 AStrBot 规范一致
"""

from dataclasses import dataclass, field


# ============================================================
# 1. Shell 命令执行
# ============================================================
@dataclass
class WinShellTool:
    """在远程 Windows 电脑上执行 CMD 命令并返回输出。"""

    name: str = "win_shell"
    description: str = (
        "在远程 Windows 电脑上执行 CMD 命令并返回输出。"
        "适用场景：查看网络配置(ipconfig)、查看进程(tasklist)、"
        "查看目录(dir)、查看系统信息(systeminfo)、"
        "查看环境变量(set)、查看路由表(route print)等。"
        "不要在命令中使用管道符、重定向或危险命令。"
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的 CMD 命令，如 'ipconfig /all'、'tasklist'、'dir C:\\\\Temp'",
                }
            },
            "required": ["command"],
        }
    )


# ============================================================
# 2. PowerShell 命令执行
# ============================================================
@dataclass
class WinPowershellTool:
    """在远程 Windows 电脑上执行 PowerShell 命令。"""

    name: str = "win_powershell"
    description: str = (
        "在远程 Windows 电脑上执行 PowerShell 命令并返回输出。"
        "适用场景：获取进程详情(Get-Process)、服务状态(Get-Service)、"
        "磁盘空间(Get-PSDrive)、内存信息(Get-Counter)、"
        "注册表查询(Get-ItemProperty)、WMI 查询(Get-WmiObject)等高级操作。"
        "比 CMD 更强大，适合复杂系统管理任务。"
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "PowerShell 命令，如 'Get-Process | Sort CPU -Descending | Select -First 10'",
                }
            },
            "required": ["command"],
        }
    )


# ============================================================
# 3. 桌面截图
# ============================================================
@dataclass
class WinScreenshotTool:
    """对远程 Windows 桌面进行截图并返回图片。"""

    name: str = "win_screenshot"
    description: str = (
        "对远程 Windows 电脑的当前桌面进行截图并返回图片。"
        "适用场景：查看远程电脑当前屏幕内容、确认程序运行状态、"
        "查看桌面是否有弹窗/错误提示等。"
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "description": "图片格式：JPEG（默认，体积小）或 PNG（无损）",
                    "enum": ["JPEG", "PNG"],
                },
                "quality": {
                    "type": "integer",
                    "description": "JPEG 质量 1-100，默认 75",
                    "minimum": 1,
                    "maximum": 100,
                },
            },
            "required": [],
        }
    )


# ============================================================
# 4. 键盘模拟
# ============================================================
@dataclass
class WinKeypressTool:
    """在远程 Windows 上模拟键盘按键组合。"""

    name: str = "win_keypress"
    description: str = (
        "在远程 Windows 电脑上模拟键盘按键组合。"
        "适用场景：Ctrl+C 复制、Ctrl+V 粘贴、Alt+Tab 切换窗口、"
        "Win+R 打开运行、Ctrl+Alt+Del 打开安全选项、"
        "Esc 取消操作等。按键名参考 WinRemote 按键规范。"
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "keys": {
                    "type": "string",
                    "description": "按键组合，用+连接，如 'ctrl+c'、'alt+tab'、'win+r'、'ctrl+alt+del'、'escape'",
                }
            },
            "required": ["keys"],
        }
    )


# ============================================================
# 5. 鼠标操作
# ============================================================
@dataclass
class WinMouseTool:
    """在远程 Windows 上模拟鼠标操作。"""

    name: str = "win_mouse"
    description: str = (
        "在远程 Windows 电脑上模拟鼠标点击或移动。"
        "坐标基于屏幕分辨率左上角为(0,0)。"
        "适用场景：点击指定位置、右键菜单、双击打开文件等。"
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "x": {
                    "type": "integer",
                    "description": "屏幕 X 坐标（像素）",
                },
                "y": {
                    "type": "integer",
                    "description": "屏幕 Y 坐标（像素）",
                },
                "button": {
                    "type": "string",
                    "description": "鼠标按钮类型",
                    "enum": ["click", "right", "double", "move"],
                },
            },
            "required": ["x", "y"],
        }
    )


# ============================================================
# 6. 打开程序/文件
# ============================================================
@dataclass
class WinOpenTool:
    """在远程 Windows 上打开程序或文件。"""

    name: str = "win_open"
    description: str = (
        "在远程 Windows 电脑上打开指定的程序或文件。"
        "适用场景：打开计算器(calc)、记事本(notepad)、"
        "资源管理器(explorer)、指定路径的文件或文件夹等。"
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "程序名（calc/notepad/explorer）或文件/文件夹的完整路径",
                }
            },
            "required": ["target"],
        }
    )


# ============================================================
# 7. 读取文件
# ============================================================
@dataclass
class WinReadFileTool:
    """读取远程 Windows 上的文件内容。"""

    name: str = "win_read_file"
    description: str = (
        "读取远程 Windows 电脑上指定路径的文件内容。"
        "仅允许读取白名单目录内的文件（如 C:\\\\Temp、C:\\\\Users\\\\Public 等）。"
        "适用场景：查看日志文件、读取配置文件、查看文本文件内容等。"
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件完整路径，如 'C:\\\\Temp\\\\log.txt'",
                },
                "max_bytes": {
                    "type": "integer",
                    "description": "最大读取字节数，默认 65536（64KB）",
                    "minimum": 1024,
                    "maximum": 1048576,
                },
            },
            "required": ["path"],
        }
    )


# ============================================================
# 导出
# ============================================================
ALL_TOOLS = [
    WinShellTool(),
    WinPowershellTool(),
    WinScreenshotTool(),
    WinKeypressTool(),
    WinMouseTool(),
    WinOpenTool(),
    WinReadFileTool(),
]

__all__ = [
    "WinShellTool",
    "WinPowershellTool",
    "WinScreenshotTool",
    "WinKeypressTool",
    "WinMouseTool",
    "WinOpenTool",
    "WinReadFileTool",
    "ALL_TOOLS",
    "get_tool_names",
]


def get_tool_names() -> list:
    """返回所有 Tool 名称列表"""
    return [t.name for t in ALL_TOOLS]
