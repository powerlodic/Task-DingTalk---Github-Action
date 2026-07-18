from __future__ import annotations

import base64
import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import quote_plus

import requests


class DingTalkConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class DingTalkClient:
    webhook_url: str
    secret: str = ""

    @classmethod
    def from_app_config(cls, config: Mapping[str, str]) -> "DingTalkClient":
        webhook_url = config.get("DINGTALK_WEBHOOK_URL", "")
        if not webhook_url:
            raise DingTalkConfigError("DINGTALK_WEBHOOK_URL belum diisi di .env.")
        return cls(webhook_url=webhook_url, secret=config.get("DINGTALK_SECRET", ""))

    def signed_url(self) -> str:
        if not self.secret:
            return self.webhook_url

        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{self.secret}".encode("utf-8")
        secret = self.secret.encode("utf-8")
        signature = base64.b64encode(
            hmac.new(secret, string_to_sign, digestmod=hashlib.sha256).digest()
        ).decode("utf-8")
        separator = "&" if "?" in self.webhook_url else "?"
        return f"{self.webhook_url}{separator}timestamp={timestamp}&sign={quote_plus(signature)}"

    def send_text(self, content: str) -> None:
        self._post({"msgtype": "text", "text": {"content": content}})

    def send_markdown(self, title: str, text: str) -> None:
        self._post({"msgtype": "markdown", "markdown": {"title": title, "text": text}})

    def _post(self, payload: dict) -> None:
        response = requests.post(self.signed_url(), json=payload, timeout=15)
        response.raise_for_status()
        data = response.json()
        if data.get("errcode") != 0:
            raise RuntimeError(f"DingTalk error {data.get('errcode')}: {data.get('errmsg')}")
