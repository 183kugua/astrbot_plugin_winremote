"""
confirm.py - WinRemote 授权确认（私聊模式）
v0.9.5

流程：
1. 用户发起高危操作 → 插件向管理员私聊发送授权申请
2. 管理员在私聊中回复 "同意" / "拒绝"
3. 5 分钟内不回复 → 自动取消
4. 非管理员回复 → 忽略

使用 AStrBot 官方 API：
- context.send_message(unified_msg_origin, chain) 主动发私聊
- event.unified_msg_origin 获取会话标识
- MessageChain 构建消息
"""
import asyncio
import time
import uuid

# AStrBot 消息组件（带 fallback）
try:
    from astrbot.api.event.filter import filter as event_filter
    from astrbot.api.message_components import Plain
    _HAS_ASTRBOT = True
except ImportError:
    Plain = None
    event_filter = None
    _HAS_ASTRBOT = False

# ─── 配置 ────────────────────────────────────────────────

CONFIRM_TIMEOUT = 300  # 等待确认超时（秒），默认 5 分钟
POLL_INTERVAL = 2       # 轮询间隔（秒）

# 认可为「同意」的关键词
APPROVE = {"同意", "确认", "confirm", "yes", "y", "1", "ok", "好", "通过", "允许"}

# 认可为「拒绝」的关键词
DENY = {"拒绝", "取消", "cancel", "no", "n", "0", "驳回", "不许", "禁止"}

# ─── 待确认请求存储 ──────────────────────────────────────
# op_id → {event, op, ttl, requester, expire_at, result_future}
_pending: dict[str, dict] = {}


# ─── 核心函数 ────────────────────────────────────────────

async def request_private_confirm(
    context,
    event,
    op: str,
    ttl: int,
    admin_qq: str | list[str],
    plugin_self=None,
) -> bool:
    """
    向管理员私聊发送授权申请，等待回复。

    Args:
        context: AStrBot Context 对象
        event: 触发事件（用于获取 unified_msg_origin 和回复原始会话）
        op: 申请的操作名（如 "powershell"）
        ttl: 申请的授权时长（秒），0=永久
        admin_qq: 管理员 QQ 号（单个或列表）
        plugin_self: 插件实例（用于发送主动消息）

    Returns:
        True  = 管理员同意
        False = 拒绝 / 超时
    """
    requester = event.get_sender_id() or "unknown"
    ttl_desc = "永久" if ttl == 0 else f"{ttl}秒"
    op_id = str(uuid.uuid4())[:8]

    # 统一 admin_qq 为列表
    if isinstance(admin_qq, str):
        admin_qq_list = [admin_qq]
    else:
        admin_qq_list = [str(q) for q in admin_qq]

    # 构造确认消息
    confirm_msg = (
        f"⚠️ WinRemote 高危操作授权申请\n"
        f"━━━━━━━━━━━━━━\n"
        f"申请人: {requester}\n"
        f"操作: {op}\n"
        f"时长: {ttl_desc}\n"
        f"━━━━━━━━━━━━━━\n"
        f"请回复「同意」或「拒绝」\n"
        f"（{CONFIRM_TIMEOUT // 60} 分钟未回复自动取消）"
    )

    # 通过插件实例发送私聊给管理员
    if plugin_self is not None:
        logger = getattr(plugin_self, "logger", None)
        send_ok = True
        for admin_id in admin_qq_list:
            try:
                if _HAS_ASTRBOT and Plain is not None:
                    await context.send_message(
                        f"private:{admin_id}",
                        [Plain(confirm_msg)]
                    )
                else:
                    # fallback: 直接发到当前会话
                    await context.send(event, f"📨 致管理员 {admin_id}：\n{confirm_msg}")
            except Exception as e:
                send_ok = False
                if logger:
                    logger.error(f"发送私聊确认失败 (admin={admin_id}): {e}")
        if not send_ok:
            await context.send(event, "⚠️ 私聊发送失败，请管理员关注群内申请")
    else:
        # 没有 plugin_self 时直接发到当前会话
        await context.send(event, f"⚠️ 授权申请：\n{confirm_msg}")

    # 创建 Future 用于等待结果
    loop = asyncio.get_event_loop()
    result_future: asyncio.Future = loop.create_future()

    # 存储待确认请求
    _pending[op_id] = {
        "event": event,
        "op": op,
        "ttl": ttl,
        "ttl_desc": ttl_desc,
        "requester": requester,
        "admin_qq_list": admin_qq_list,
        "expire_at": time.time() + CONFIRM_TIMEOUT,
        "result_future": result_future,
        "context": context,
    }

    # 通知原始会话
    await context.send(
        event,
        f"📤 已向管理员发送授权申请（{op}, {ttl_desc}）\n"
        f"⏳ 等待管理员确认（{CONFIRM_TIMEOUT // 60}分钟超时）..."
    )

    # 等待结果（带超时）
    try:
        result = await asyncio.wait_for(result_future, timeout=CONFIRM_TIMEOUT)
        return result
    except asyncio.TimeoutError:
        _pending.pop(op_id, None)
        await context.send(event, f"⏰ 授权确认超时（{CONFIRM_TIMEOUT // 60}分钟），{op} 已自动取消")
        return False
    finally:
        _pending.pop(op_id, None)


async def handle_private_reply(context, event) -> bool:
    """
    处理管理员在私聊中的回复。
    由插件在主消息监听器中调用，判断是否为授权确认回复。

    Returns:
        True  = 这是一条授权确认回复（已处理）
        False = 不是授权确认回复（忽略）
    """
    sender = str(event.get_sender_id() or "")
    if not sender:
        return False

    # 查找该管理员相关的待确认请求
    target_op_id = None
    for op_id, info in _pending.items():
        if sender in info["admin_qq_list"]:
            target_op_id = op_id
            break

    if target_op_id is None:
        return False  # 不是授权确认回复

    info = _pending[target_op_id]

    # 检查是否超时
    if time.time() > info["expire_at"]:
        _pending.pop(target_op_id, None)
        if not info["result_future"].done():
            info["result_future"].set_result(False)
        return True

    # 解析回复内容
    raw = ""
    if hasattr(event, "get_message_str"):
        raw = event.get_message_str()
    else:
        raw = getattr(event, "message", "") or ""

    raw_stripped = raw.strip()
    raw_lower = raw_stripped.lower()

    # 检查 emoji（兼容 ✅/❌）
    if "✅" in raw or any(k in raw_lower for k in ["同意", "确认", "允许"]):
        approved = True
    elif "❌" in raw or any(k in raw_lower for k in ["拒绝", "取消", "驳回", "禁止"]):
        approved = False
    else:
        # 纯文本匹配
        if raw_stripped in APPROVE or raw_lower in APPROVE:
            approved = True
        elif raw_stripped in DENY or raw_lower in DENY:
            approved = False
        else:
            # 不明确 → 忽略，继续等待
            await context.send(event, "⚠️ 请回复「同意」或「拒绝」")
            return True

    # 设置结果
    if not info["result_future"].done():
        info["result_future"].set_result(approved)

    # 通知管理员
    if approved:
        await context.send(
            event,
            f"✅ 已同意：{info['op']}（{info['ttl_desc']}）\n"
            f"申请人: {info['requester']}"
        )
    else:
        await context.send(
            event,
            f"❌ 已拒绝：{info['op']}\n"
            f"申请人: {info['requester']}"
        )

    return True


def get_pending_count() -> int:
    """返回当前待确认请求数量"""
    now = time.time()
    # 清理过期
    expired = [k for k, v in _pending.items() if now > v["expire_at"]]
    for k in expired:
        info = _pending.pop(k, None)
        if info and not info["result_future"].done():
            info["result_future"].set_result(False)
    return len(_pending)


def cancel_all():
    """取消所有待确认请求（插件卸载时调用）"""
    for info in _pending.values():
        if not info["result_future"].done():
            info["result_future"].set_result(False)
    _pending.clear()
