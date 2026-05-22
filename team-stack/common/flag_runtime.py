from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(encoded: str) -> bytes:
    padding = "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode(encoded + padding)


@dataclass
class FlagRuntime:
    service_name: str
    secret: str
    window_seconds: int = 15
    grace_seconds: int = 3

    def __init__(self, service_name: str, secret: Optional[str] = None, window_seconds: Optional[int] = None, grace_seconds: Optional[int] = None):
        self.service_name = service_name
        self.secret = secret or os.getenv("HACKATHON_SECRET", "HACKATHON_SECRET_2025")
        self.window_seconds = max(5, int(window_seconds or os.getenv("FLAG_WINDOW_SECONDS", "15")))
        self.grace_seconds = max(0, int(grace_seconds or os.getenv("FLAG_GRACE_SECONDS", "3")))
        # per-process instance secret (optional, not used for token generation)
        self._instance_secret = secrets.token_hex(16)
        # in-memory mapping of window_index -> random token (short lived)
        self._window_tokens: Dict[int, str] = {}
        # token retention in seconds: keep tokens for an extra grace to allow verification
        self._token_retention = self.window_seconds + self.grace_seconds + 5

    def now(self) -> int:
        return int(time.time())

    def window_index(self, timestamp: Optional[int] = None) -> int:
        return int((timestamp if timestamp is not None else self.now()) // self.window_seconds)

    def _payload(self, window_index: int) -> Dict[str, Any]:
        issued_at = window_index * self.window_seconds
        return {
            "issued_at": issued_at,
            "service": self.service_name,
            "window": window_index,
        }

    def _generate_token_for_window(self, window_index: int) -> str:
        # generate an 8-character alphanumeric token (letters + digits)
        alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        return "".join(secrets.choice(alphabet) for _ in range(8))

    def _prune_tokens(self) -> None:
        # remove tokens older than retention window
        now = self.now()
        keep = {}
        for win_idx, (token, ts) in getattr(self, "_token_store_with_ts", {}).items():
            if ts + self._token_retention >= now:
                keep[win_idx] = (token, ts)
        # convert back to the compact stores
        self._token_store_with_ts = keep
        self._window_tokens = {k: v for k, (v, _) in keep.items()}

    def current_flag(self, timestamp: Optional[int] = None) -> str:
        win = self.window_index(timestamp)
        # lazily initialize token store with timestamps
        if not hasattr(self, "_token_store_with_ts"):
            self._token_store_with_ts: Dict[int, Any] = {}

        # prune old tokens
        try:
            self._prune_tokens()
        except Exception:
            pass

        if win not in self._window_tokens:
            token = self._generate_token_for_window(win)
            self._window_tokens[win] = token
            self._token_store_with_ts[win] = (token, self.now())

        # format: RF1.<window>.<token>
        return f"RF1.{win}.{self._window_tokens[win]}"

    def verify(self, flag: str, timestamp: Optional[int] = None) -> bool:
        # expected format: RF1.<window>.<token>
        try:
            parts = str(flag).strip().split(".")
            if len(parts) != 3:
                return False
            prefix, win_str, token = parts
            if prefix != "RF1":
                return False
            win = int(win_str)
        except Exception:
            return False

        # basic service check via window mapping (issued_at derivable from win)
        payload = self._payload(win)
        if payload.get("service") != self.service_name:
            return False

        # prune old tokens then check
        try:
            self._prune_tokens()
        except Exception:
            pass

        # allow verification if token matches stored token for that window
        stored = self._window_tokens.get(win)
        if stored and secrets.compare_digest(stored, token):
            # ensure the window is within allowable time bounds
            issued_at = win * self.window_seconds
            now_ts = self.now() if timestamp is None else int(timestamp)
            if issued_at < 0 or abs(now_ts - issued_at) > (self.window_seconds + self.grace_seconds):
                return False
            return True

        return False

    def sync_text_file(self, path: Path, timestamp: Optional[int] = None) -> str:
        flag = self.current_flag(timestamp)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(flag, encoding="utf-8")
        return flag
