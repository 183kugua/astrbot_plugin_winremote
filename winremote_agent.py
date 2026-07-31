"""
WinRemote Agent V0.9 - Windows 本机常驻客户端
功能：反连服务器 WebSocket，执行 Shell / PowerShell / 截图 / 键鼠 / 文件读写
安全：客户端二次路径校验 + 写入开关 + 超时强杀 + 心跳线程
合规：ruff-formatted, type-annotated, tested
"""

import argparse
import asyncio
import contextlib
import json
import os
import signal
import sys
import time
from pathlib import Path  # noqa: E402

# ruff: noqa: I001 (PIL/pyautogui imported lazily inside functions)


# ============================================================
# 配置（命令行参数优先，其次环境变量，最后默认值）
# ============================================================
def parse_args():
    p = argparse.ArgumentParser(description="WinRemote Agent V0.9.1")
    p.add_argument(
        "--server", default=os.getenv("WINREMOTE_SERVER", "ws://127.0.0.1:6190/winremote")
    )
    p.add_argument("--token", default=os.getenv("WINREMOTE_TOKEN", ""))
    p.add_argument("--agent-id", default=os.getenv("WINREMOTE_AGENT_ID", ""))
    p.add_argument("--config", default=os.getenv("WINREMOTE_CONFIG", ""))
    return p.parse_args()


def load_config(path: str) -> dict:
    cfg = {}
    if path and Path(path).exists():
        try:
            cfg = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[Agent] 配置加载失败: {e}")
    return cfg


# ============================================================
# 路径安全（客户端二次校验）
# ============================================================
def check_path_safe(file_path: str, whitelist: list, blacklist_kw: list) -> tuple[bool, str]:
    try:
        resolved = Path(file_path).resolve()
    except Exception as e:
        return False, f"路径解析失败: {e}"
    for kw in blacklist_kw:
        if kw.lower() in str(resolved).lower():
            return False, f"路径包含禁用关键词: {kw}"
    if not whitelist:
        return True, ""
    for w in whitelist:
        with contextlib.suppress(Exception):
            w_resolved = Path(w).resolve()
            if str(resolved).startswith(str(w_resolved)):
                return True, ""
    return False, "路径不在白名单内"


# ============================================================
# 动作执行
# ============================================================
async def exec_shell(cmd: str, timeout: int, cfg: dict) -> dict:
    """执行 cmd /c 命令，chcp 65001 保证中文"""
    full = f"chcp 65001 >nul && {cmd}"
    try:
        proc = await asyncio.create_subprocess_shell(
            full,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        out = stdout.decode("utf-8", errors="replace")
        err = stderr.decode("utf-8", errors="replace")
        return {
            "stdout": out[: cfg.get("max_output_bytes", 8192)],
            "stderr": err[:2048],
            "returncode": proc.returncode,
        }
    except asyncio.TimeoutError:
        proc.kill()
        return {"stdout": "", "stderr": f"超时({timeout}s)已强杀", "returncode": -1}
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "returncode": -1}


async def exec_powershell(cmd: str, timeout: int, cfg: dict) -> dict:
    full = f'chcp 65001 >nul && powershell -NoProfile -Command "{cmd}"'
    return await exec_shell(full, timeout, cfg)


async def take_screenshot(fmt: str, quality: int, cfg: dict) -> dict:
    try:
        from PIL import ImageGrab
        import base64

        img = ImageGrab.grab()
        import io

        buf = io.BytesIO()
        if fmt.upper() == "PNG":
            img.save(buf, format="PNG")
            mime = "image/png"
        elif fmt.upper() == "WEBP":
            img.save(buf, format="WebP", quality=quality)
            mime = "image/webp"
        else:
            img.save(buf, format="JPEG", quality=quality)
            mime = "image/jpeg"
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return {"ok": True, "format": mime, "data": b64, "size": len(buf.getvalue())}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def keypress(keys: str) -> dict:
    try:
        import pyautogui

        pyautogui.hotkey(*[k.strip() for k in keys.split("+")])
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def mouse_action(x: str, y: str, button: str) -> dict:
    try:
        import pyautogui

        ix, iy = int(x), int(y)
        btn = button.lower()
        if btn == "right":
            pyautogui.rightClick(ix, iy)
        elif btn == "double":
            pyautogui.doubleClick(ix, iy)
        else:
            pyautogui.click(ix, iy)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def open_target(target: str) -> dict:
    try:
        os.startfile(target)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def read_file(path: str, cfg: dict) -> dict:
    whitelist = cfg.get("file_whitelist_paths", [])
    blacklist = cfg.get("file_blacklist_keywords", [])
    ok, reason = check_path_safe(path, whitelist, blacklist)
    if not ok:
        return {"ok": False, "error": reason}
    try:
        max_b = cfg.get("file_max_read_bytes", 1048576)
        data = Path(path).read_text(encoding="utf-8", errors="replace")[:max_b]
        return {"ok": True, "content": data, "bytes": len(data.encode("utf-8"))}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def write_file(path: str, content: str, cfg: dict) -> dict:
    if not cfg.get("file_allow_write", False):
        return {"ok": False, "error": "写入功能已禁用"}
    whitelist = cfg.get("file_whitelist_paths", [])
    blacklist = cfg.get("file_blacklist_keywords", [])
    ok, reason = check_path_safe(path, whitelist, blacklist)
    if not ok:
        return {"ok": False, "error": reason}
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(content, encoding="utf-8")
        return {"ok": True, "bytes": len(content.encode("utf-8"))}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ============================================================
# 心跳线程
# ============================================================
def heartbeat_loop(ws, interval: int, stop_event: asyncio.Event):
    async def _beat():
        while not stop_event.is_set():
            with contextlib.suppress(Exception):
                await ws.send(json.dumps({"type": "heartbeat", "ts": time.time()}))
                await asyncio.sleep(interval)
                continue
            break

    return _beat()


# ============================================================
# 主循环
# ============================================================
async def main():
    args = parse_args()
    cfg = load_config(args.config)
    # 合并默认值
    defaults = {
        "heartbeat_interval": 15,
        "shell_timeout": 30,
        "max_output_bytes": 8192,
        "screenshot_format": "JPEG",
        "screenshot_quality": 75,
        "file_whitelist_paths": [],
        "file_blacklist_keywords": ["..\\", "../", "%temp%", "$env:"],
        "file_max_read_bytes": 1048576,
        "file_allow_write": False,
        "allow_powershell": True,
    }
    for k, v in defaults.items():
        cfg.setdefault(k, v)

    import websockets

    agent_id = args.agent_id or f"{os.environ.get('COMPUTERNAME', 'pc')}-{os.urandom(3).hex()}"
    uri = args.server
    token = args.token

    print(f"[Agent] 启动 id={agent_id} uri={uri}")

    async with websockets.connect(uri) as ws:
        # 握手
        await ws.send(
            json.dumps(
                {
                    "token": token,
                    "agent_id": agent_id,
                    "info": {
                        "hostname": os.environ.get("COMPUTERNAME", ""),
                        "username": os.environ.get("USERNAME", ""),
                        "platform": sys.platform,
                    },
                }
            )
        )
        print("[Agent] 已连接，等待指令...")

        stop_event = asyncio.Event()
        hb_task = asyncio.create_task(heartbeat_loop(ws, cfg["heartbeat_interval"], stop_event))

        try:
            async for msg in ws:
                with contextlib.suppress(Exception):
                    m = json.loads(msg)
                    msg_id = m.get("id", "")
                    action = m.get("action", "")
                    params = m.get("params", {})
                    timeout = m.get("timeout", cfg["shell_timeout"])
                msg_id = m.get("id", "")
                action = m.get("action", "")
                params = m.get("params", {})
                timeout = m.get("timeout", cfg["shell_timeout"])

                result = {}
                if action == "shell":
                    result = await exec_shell(params.get("command", ""), timeout, cfg)
                elif action == "powershell":
                    if not cfg.get("allow_powershell"):
                        result = {"ok": False, "error": "PowerShell 已禁用"}
                    else:
                        result = await exec_powershell(params.get("command", ""), timeout, cfg)
                elif action == "screenshot":
                    result = await take_screenshot(
                        params.get("format", cfg["screenshot_format"]),
                        params.get("quality", cfg["screenshot_quality"]),
                        cfg,
                    )
                elif action == "keypress":
                    result = keypress(params.get("keys", ""))
                elif action == "mouse":
                    result = mouse_action(
                        params.get("x", "0"), params.get("y", "0"), params.get("button", "click")
                    )
                elif action == "open":
                    result = open_target(params.get("target", ""))
                elif action == "readfile":
                    result = read_file(params.get("path", ""), cfg)
                elif action == "writefile":
                    result = write_file(params.get("path", ""), params.get("content", ""), cfg)
                elif action == "ping":
                    result = {"ok": True, "pong": time.time()}
                else:
                    result = {"ok": False, "error": f"未知动作: {action}"}

                await ws.send(
                    json.dumps(
                        {
                            "type": "result",
                            "id": msg_id,
                            "action": action,
                            "result": result,
                        }
                    )
                )
                if action == "screenshot" and result.get("ok"):
                    await ws.send(
                        json.dumps(
                            {
                                "type": "chunk",
                                "id": msg_id,
                                "format": result.get("format"),
                                "data": result.get("data"),
                            }
                        )
                    )
        finally:
            stop_event.set()
            hb_task.cancel()

    print("[Agent] 连接已关闭")


# ============================================================
# 信号处理（Windows 也能捕获 Ctrl+C）
# ============================================================
def signal_handler(sig, frame):
    print("[Agent] 收到退出信号，清理中...")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[Agent] 已退出")
        sys.exit(0)
