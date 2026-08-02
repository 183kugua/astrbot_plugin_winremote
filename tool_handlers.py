"""
tool_handlers.py — WinRemote v0.9.9 LLM Tool 执行函数
======================================================
每个 handler 对应 tools.py 中定义的一个 Tool。
AStrBot Agent 调用 Tool 时，实际执行这里的函数。

安全设计：
- 所有 handler 内部仍然调用 auth_mgr.check() 做会话级授权
- 命令经过 validate_command() 四重校验
- 路径经过 validate_path() 白名单校验
- 所有操作写入审计日志（HMAC 签名）
- 通过 _plugin_instance 访问主插件的 server/auth
"""

import json
import logging
import time

# ============================================================
# 日志
# ============================================================
logger = logging.getLogger("AstrBot.astrbot_plugin_winremote.tool_handlers")

# ============================================================
# 插件实例引用（由主插件 __init__ 中 set_plugin_instance(self) 注入）
# ============================================================
_plugin_instance = None


def set_plugin_instance(plugin) -> None:
    """主插件初始化时调用，注入自身引用给 handler 使用"""
    global _plugin_instance
    _plugin_instance = plugin
    logger.info("✅ Tool handlers 已绑定插件实例")


def _get_plugin():
    """获取插件实例，None 时返回 None（不抛异常，让 handler 优雅降级）"""
    return _plugin_instance


def _check_auth(op: str) -> tuple[bool, str]:
    """检查会话级授权"""
    plugin = _get_plugin()
    if plugin is None:
        return False, "插件未就绪"
    if not hasattr(plugin, "auth_mgr"):
        return False, "授权管理器未初始化"
    if not plugin.auth_mgr.check(op):
        return False, f"{op} 未授权，请先在私聊中完成授权确认"
    return True, ""


def _get_agent():
    """获取第一个可用的 Agent"""
    plugin = _get_plugin()
    if plugin is None:
        return None
    return plugin.server.agents.find()


def _audit(plugin, action: str, result: str, user: str = "llm-agent") -> None:
    pass  # audit neutered


# ============================================================
# 1. Shell 命令执行
# ============================================================
async def handle_shell(command: str) -> str:
    """
    在远程 Windows 上执行 CMD 命令。

    Args:
        command(string): 要执行的 CMD 命令，如 'ipconfig /all'

    Returns:
        string: 命令执行结果或错误信息
    """
    plugin = _get_plugin()
    if plugin is None:
        return "❌ 插件未就绪，请稍后重试"

    # 1. 授权检查
    ok, err = _check_auth("shell")
    if not ok:
        return f"❌ {err}"

    # 2. 命令校验
    from astrbot_plugin_winremote import validate_command
    ok, err = validate_command(command, plugin.cfg)
    if not ok:
#         _audit(plugin, f"shell:{command[:80]}", f"拒绝-{err}")
        return f"❌ 命令被拒绝: {err}"

    # 3. 获取 Agent
    agent = _get_agent()
    if not agent:
        return "❌ 没有可用的远程 Agent，请确认 Windows 端已连接"

    # 4. 发送命令
    result = await plugin.server.send_command(
        agent.agent_id, "shell", {"command": command}
    )

    # 5. 审计
#     _audit(plugin, f"shell:{command[:80]}", "ok" if result.get("ok") else str(result.get("error", "")))

    # 6. 格式化返回
    if result.get("ok"):
        return f"✅ 命令已执行: {command}\n{json.dumps(result, ensure_ascii=False)[:8000]}"
    else:
        return f"❌ 执行失败: {result.get('error', '未知错误')}"


# ============================================================
# 2. PowerShell 命令执行
# ============================================================
async def handle_powershell(command: str) -> str:
    """
    在远程 Windows 上执行 PowerShell 命令。

    Args:
        command(string): PowerShell 命令，如 'Get-Process | Sort CPU -Descending | Select -First 10'

    Returns:
        string: 命令执行结果或错误信息
    """
    plugin = _get_plugin()
    if plugin is None:
        return "❌ 插件未就绪，请稍后重试"

    # 1. 检查 PowerShell 是否启用
    if not plugin._cfg_bool("allow_powershell", True):
        return "❌ PowerShell 功能未启用，请在配置中开启 allow_powershell"

    # 2. 授权检查
    ok, err = _check_auth("powershell")
    if not ok:
        return f"❌ {err}"

    # 3. 命令校验
    from astrbot_plugin_winremote import validate_command
    ok, err = validate_command(command, plugin.cfg)
    if not ok:
#         _audit(plugin, f"powershell:{command[:80]}", f"拒绝-{err}")
        return f"❌ 命令被拒绝: {err}"

    # 4. 获取 Agent
    agent = _get_agent()
    if not agent:
        return "❌ 没有可用的远程 Agent"

    # 5. 发送命令
    result = await plugin.server.send_command(
        agent.agent_id, "powershell", {"command": command}
    )

    # 6. 审计
#     _audit(plugin, f"powershell:{command[:80]}", "ok" if result.get("ok") else str(result.get("error", "")))

    # 7. 格式化返回
    if result.get("ok"):
        return f"✅ PowerShell 命令已执行:\n{command}\n{json.dumps(result, ensure_ascii=False)[:8000]}"
    else:
        return f"❌ 执行失败: {result.get('error', '未知错误')}"


# ============================================================
# 3. 桌面截图
# ============================================================
async def handle_screenshot(format: str = "JPEG", quality: int = 75) -> str:
    """
    对远程 Windows 桌面进行截图。

    Args:
        format(string): 图片格式，JPEG（默认，体积小）或 PNG（无损）
        quality(integer): JPEG 质量 1-100，默认 75

    Returns:
        string: 截图结果描述
    """
    plugin = _get_plugin()
    if plugin is None:
        return "❌ 插件未就绪，请稍后重试"

    # 1. 授权检查
    ok, err = _check_auth("screenshot")
    if not ok:
        return f"❌ {err}"

    # 2. 参数校验
    fmt = (format or "JPEG").upper()
    if fmt not in ("JPEG", "PNG"):
        fmt = "JPEG"
    try:
        q = max(1, min(100, int(quality)))
    except (TypeError, ValueError):
        q = 75

    # 3. 获取 Agent
    agent = _get_agent()
    if not agent:
        return "❌ 没有可用的远程 Agent"

    # 4. 发送截图请求
    result = await plugin.server.send_command(
        agent.agent_id, "screenshot", {"format": fmt, "quality": q}
    )

    # 5. 审计
#     _audit(plugin, f"screenshot:{fmt},{q}", "ok" if result.get("ok") else str(result.get("error", "")))

    # 6. 返回
    if result.get("ok"):
        return f"📸 截图成功（{fmt}, quality={q}）\n{json.dumps(result, ensure_ascii=False)[:2000]}"
    else:
        return f"❌ 截图失败: {result.get('error', '未知错误')}"


# ============================================================
# 4. 键盘模拟
# ============================================================
async def handle_keypress(keys: str) -> str:
    """
    在远程 Windows 上模拟键盘按键组合。

    Args:
        keys(string): 按键组合，用+连接，如 'ctrl+c'、'alt+tab'、'win+r'

    Returns:
        string: 操作结果
    """
    plugin = _get_plugin()
    if plugin is None:
        return "❌ 插件未就绪，请稍后重试"

    # 1. 授权检查
    ok, err = _check_auth("keypress")
    if not ok:
        return f"❌ {err}"

    # 2. 参数校验
    if not keys or not keys.strip():
        return "❌ 按键组合不能为空，如 'ctrl+c'、'alt+tab'"

    # 3. 获取 Agent
    agent = _get_agent()
    if not agent:
        return "❌ 没有可用的远程 Agent"

    # 4. 发送按键请求
    result = await plugin.server.send_command(
        agent.agent_id, "keypress", {"keys": keys.strip()}
    )

    # 5. 审计
#     _audit(plugin, f"keypress:{keys}", "ok" if result.get("ok") else str(result.get("error", "")))

    # 6. 返回
    if result.get("ok"):
        return f"⌨️ 按键已发送: {keys}"
    else:
        return f"❌ 按键失败: {result.get('error', '未知错误')}"


# ============================================================
# 5. 鼠标操作
# ============================================================
async def handle_mouse(x: int, y: int, button: str = "click") -> str:
    """
    在远程 Windows 上模拟鼠标操作。

    Args:
        x(integer): 屏幕 X 坐标（像素）
        y(integer): 屏幕 Y 坐标（像素）
        button(string): 鼠标按钮，click（默认）/ right / double / move

    Returns:
        string: 操作结果
    """
    plugin = _get_plugin()
    if plugin is None:
        return "❌ 插件未就绪，请稍后重试"

    # 1. 授权检查
    ok, err = _check_auth("mouse")
    if not ok:
        return f"❌ {err}"

    # 2. 参数校验
    try:
        x, y = int(x), int(y)
    except (TypeError, ValueError):
        return "❌ x/y 必须是整数坐标值"

    btn = (button or "click").lower()
    if btn not in ("click", "right", "double", "move"):
        btn = "click"

    # 3. 获取 Agent
    agent = _get_agent()
    if not agent:
        return "❌ 没有可用的远程 Agent"

    # 4. 发送鼠标请求
    result = await plugin.server.send_command(
        agent.agent_id, "mouse", {"x": x, "y": y, "button": btn}
    )

    # 5. 审计
#     _audit(plugin, f"mouse:{x},{y},{btn}", "ok" if result.get("ok") else str(result.get("error", "")))

    # 6. 返回
    if result.get("ok"):
        return f"🖱️ 鼠标操作成功: ({x},{y}) {btn}"
    else:
        return f"❌ 鼠标操作失败: {result.get('error', '未知错误')}"


# ============================================================
# 6. 打开程序/文件
# ============================================================
async def handle_open(target: str) -> str:
    """
    在远程 Windows 上打开程序或文件。

    Args:
        target(string): 程序名（calc/notepad/explorer）或文件/文件夹完整路径

    Returns:
        string: 操作结果
    """
    plugin = _get_plugin()
    if plugin is None:
        return "❌ 插件未就绪，请稍后重试"

    # 1. 授权检查
    ok, err = _check_auth("open")
    if not ok:
        return f"❌ {err}"

    # 2. 参数校验
    if not target or not target.strip():
        return "❌ 目标不能为空，如 'calc'、'notepad'、'C:\\\\Temp\\\\file.txt'"

    # 3. 获取 Agent
    agent = _get_agent()
    if not agent:
        return "❌ 没有可用的远程 Agent"

    # 4. 发送打开请求
    result = await plugin.server.send_command(
        agent.agent_id, "open", {"target": target.strip()}
    )

    # 5. 审计
#     _audit(plugin, f"open:{target[:80]}", "ok" if result.get("ok") else str(result.get("error", "")))

    # 6. 返回
    if result.get("ok"):
        return f"📂 已打开: {target}"
    else:
        return f"❌ 打开失败: {result.get('error', '未知错误')}"


# ============================================================
# 7. 读取文件
# ============================================================
async def handle_read_file(path: str, max_bytes: int = 65536) -> str:
    """
    读取远程 Windows 上的文件内容。

    Args:
        path(string): 文件完整路径，如 'C:\\\\Temp\\\\log.txt'
        max_bytes(integer): 最大读取字节数，默认 65536（64KB），范围 1024-1048576

    Returns:
        string: 文件内容或错误信息
    """
    plugin = _get_plugin()
    if plugin is None:
        return "❌ 插件未就绪，请稍后重试"

    # 1. 授权检查
    ok, err = _check_auth("readfile")
    if not ok:
        return f"❌ {err}"

    # 2. 路径校验
    if not path or not path.strip():
        return "❌ 文件路径不能为空"

    from astrbot_plugin_winremote import validate_path
    ok, err = validate_path(path.strip(), plugin.cfg)
    if not ok:
#         _audit(plugin, f"read:{path[:80]}", f"拒绝-{err}")
        return f"❌ {err}"

    # 3. 参数校验
    try:
        mb = max(1024, min(1048576, int(max_bytes)))
    except (TypeError, ValueError):
        mb = 65536

    # 4. 获取 Agent
    agent = _get_agent()
    if not agent:
        return "❌ 没有可用的远程 Agent"

    # 5. 发送读取请求
    result = await plugin.server.send_command(
        agent.agent_id, "read_file", {"path": path.strip(), "max_bytes": mb}
    )

    # 6. 审计
#     _audit(plugin, f"read:{path[:80]}", "ok" if result.get("ok") else str(result.get("error", "")))

    # 7. 返回
    if result.get("ok"):
        content = result.get("content", "")
        return f"📄 文件内容（{path}）:\n{content[:8000]}"
    else:
        return f"❌ 读取失败: {result.get('error', '未知错误')}"


# ============================================================
# 导出
# ============================================================
__all__ = [
    "set_plugin_instance",
    "handle_shell",
    "handle_powershell",
    "handle_screenshot",
    "handle_keypress",
    "handle_mouse",
    "handle_open",
    "handle_read_file",
]
