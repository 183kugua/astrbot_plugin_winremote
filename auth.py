"""
auth.py - WinRemote 会话级授权 + 防篡改审计
v0.9.5：auth_ttl_seconds 可配置，替代永久开关

安全设计：
- 所有高危操作必须会话级临时授权
- 授权自动过期（默认5分钟，可配置0=永久但需私聊确认）
- 审计日志每条带 HMAC-SHA256 签名
"""
import hashlib
import hmac
import json
import os
import time
from pathlib import Path

# ─── 常量 ────────────────────────────────────────────────
DEFAULT_TTL = 300           # 默认5分钟
MAX_TTL = 3600              # 最大1小时
HIGH_TTL_THRESHOLD = 1800   # >30分钟需私聊确认
LOG_FILE_DEFAULT = "data/winremote_auth_log.jsonl"
LOG_PERMS = 0o444           # 只读权限
SECRET_DERIVE_INFO = b"winremote-auth-v1"
PERM_TAG = "[PERM]"

# 需要私聊确认的操作类型
CONFIRM_OPS = {"powershell", "write", "mouse", "shell"}


# ─── 内部工具 ────────────────────────────────────────────

def _derive_key(secret_token: str) -> bytes:
    """从 secret_token 派生 HMAC 密钥"""
    return hashlib.pbkdf2_hmac(
        "sha256", secret_token.encode(), SECRET_DERIVE_INFO, 100_000
    )


def _sign(payload: dict, key: bytes) -> str:
    """对 payload 做规范序列化后 HMAC 签名"""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()


def _verify_pwd(pwd: str, pwd_hash: str) -> bool:
    """验证二次密码（SHA-256 比对）"""
    return hashlib.sha256(pwd.encode()).hexdigest() == pwd_hash


# ─── 授权管理器 ──────────────────────────────────────────

class AuthManager:
    """
    会话级临时授权管理器。

    状态机：
    - 未授权 → request() 验证密码 → 临时授权 / 需私聊确认
    - 临时授权 → check() 在 TTL 内返回 True，过期自动失效
    - 私聊确认 → confirm() 通过 → 授权生效；deny()/超时 → 取消
    - revoke() / revoke_all() → 立即撤销
    """

    def __init__(
        self,
        secret_token: str,
        ttl: int = DEFAULT_TTL,
        log_path: str = LOG_FILE_DEFAULT,
    ):
        self.key = _derive_key(secret_token)
        self.ttl = self._clamp_ttl(ttl)
        self.auth: dict[str, float] = {}       # op → expire_timestamp (0=永久)
        self.pending: dict[str, dict] = {}      # op → {expire_at, ttl}
        self.log_path = log_path
        self._ensure_log()

    # ── 内部 ──

    def _clamp_ttl(self, ttl: int) -> int:
        if ttl < 0:
            return DEFAULT_TTL
        if ttl > MAX_TTL:
            return MAX_TTL
        return ttl

    def _ensure_log(self):
        """确保日志文件存在且设为只读"""
        Path(self.log_path).parent.mkdir(parents=True, exist_ok=True)
        if not Path(self.log_path).exists():
            Path(self.log_path).touch()
        try:
            os.chmod(self.log_path, LOG_PERMS)
        except OSError:
            pass  # 某些环境不支持 chmod

    def _write_log(self, entry: dict):
        """写入一条审计记录（自动附加 HMAC 签名）"""
        entry["sig"] = _sign(entry, self.key)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _needs_confirm(self, op: str) -> bool:
        """判断某操作是否需要私聊确认"""
        return op in CONFIRM_OPS and (self.ttl == 0 or self.ttl > HIGH_TTL_THRESHOLD)

    # ── 授权流程 ──

    def request(self, op: str, password: str, password_hash: str) -> dict:
        """
        发起授权请求。
        返回 dict:
            {"status": "ok", "ttl": int, "perm": bool}
            {"status": "need_confirm", "op": str}
            {"status": "wrong_pwd"}
        """
        # 1. 验证二次密码
        if not _verify_pwd(password, password_hash):
            self._write_log({
                "ts": time.time(),
                "event": "auth_fail",
                "op": op,
                "reason": "wrong_password",
            })
            return {"status": "wrong_pwd"}

        # 2. 判断是否需要私聊确认
        if self._needs_confirm(op):
            self.pending[op] = {
                "expire_at": time.time() + 60,
                "ttl": self.ttl,
            }
            self._write_log({
                "ts": time.time(),
                "event": "auth_pending",
                "op": op,
                "ttl": self.ttl,
            })
            return {"status": "need_confirm", "op": op}

        # 3. 直接授权（TTL 内有效）
        exp = 0 if self.ttl == 0 else time.time() + self.ttl
        self.auth[op] = exp
        tag = PERM_TAG if exp == 0 else ""
        self._write_log({
            "ts": time.time(),
            "event": "auth_ok",
            "op": op,
            "ttl": self.ttl,
            "exp": exp,
            "tag": tag,
        })
        return {"status": "ok", "ttl": self.ttl, "perm": (exp == 0)}

    def confirm(self, op: str, admin_qq: str) -> bool:
        """私聊确认通过 → 授权生效"""
        pending = self.pending.pop(op, None)
        if pending is None or time.time() > pending["expire_at"]:
            self._write_log({
                "ts": time.time(),
                "event": "confirm_timeout",
                "op": op,
            })
            return False
        ttl = pending["ttl"]
        exp = 0 if ttl == 0 else time.time() + ttl
        self.auth[op] = exp
        self._write_log({
            "ts": time.time(),
            "event": "auth_confirmed",
            "op": op,
            "by": admin_qq,
            "ttl": ttl,
            "exp": exp,
        })
        return True

    def deny(self, op: str, admin_qq: str):
        """私聊确认拒绝"""
        self.pending.pop(op, None)
        self._write_log({
            "ts": time.time(),
            "event": "auth_denied",
            "op": op,
            "by": admin_qq,
        })

    # ── 权限检查 ──

    def check(self, op: str) -> bool:
        """
        检查操作是否已授权。
        - 永久授权 (exp=0) → True
        - 临时授权未过期 → True
        - 过期 → 自动清除并返回 False
        - 未授权/已撤销 → False
        """
        exp = self.auth.get(op, None)  # None = not found (revoked or never authorized)
        if exp is None:
            return False
        if exp == 0:
            return True  # 永久授权仍有效
        if time.time() > exp:
            self.auth.pop(op, None)
            self._write_log({
                "ts": time.time(),
                "event": "auth_exp",
                "op": op,
            })
            return False
        return True

    def ttl_remaining(self, op: str) -> int:
        """返回某操作剩余有效秒数，-1 表示永久，-2 表示未授权"""
        exp = self.auth.get(op, None)
        if exp is None:
            return -2  # 未授权
        if exp == 0:
            return -1  # 永久
        return max(0, int(exp - time.time()))

    # ── 撤销 ──

    def revoke(self, op: str):
        """撤销单个操作授权"""
        self.auth.pop(op, None)
        self.pending.pop(op, None)
        self._write_log({
            "ts": time.time(),
            "event": "auth_revoke",
            "op": op,
        })

    def revoke_all(self):
        """撤销所有授权（插件卸载/重启时调用）"""
        ops = list(self.auth.keys())
        self.auth.clear()
        self.pending.clear()
        for op in ops:
            self._write_log({
                "ts": time.time(),
                "event": "auth_revoke_all",
                "op": op,
            })

    # ── 操作审计 ──

    def log_action(self, qq: str, op: str, cmd: str, result: str):
        """记录一次操作到审计日志"""
        self._write_log({
            "ts": time.time(),
            "qq": qq,
            "op": op,
            "cmd": cmd[:500],
            "result": result[:500],
        })


# ─── 审计校验（独立脚本用） ────────────────────────────────


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("用法: python auth.py <log_path> <secret_token>")
        sys.exit(1)
    