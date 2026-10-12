"""请求签名 —— 与评分服务端的签名实现互为镜像，改动必须同步。"""

from __future__ import annotations

import hashlib
import hmac
import time

SCHEME = "SE1-HMAC-SHA256"
HEADER_KEY_ID = "X-SE-KeyId"
HEADER_TIMESTAMP = "X-SE-Timestamp"
HEADER_SIGNATURE = "X-SE-Signature"
TIMESTAMP_TOLERANCE_S = 300


def canonical_string(timestamp: int, method: str, path: str, body: bytes) -> str:
    body_hash = hashlib.sha256(body).hexdigest()
    return "\n".join([SCHEME, str(timestamp), method.upper(), path, body_hash])


def sign(secret: str, timestamp: int, method: str, path: str, body: bytes) -> str:
    payload = canonical_string(timestamp, method, path, body).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def build_headers(key_id: str, secret: str, method: str, path: str, body: bytes) -> dict[str, str]:
    timestamp = int(time.time())
    return {
        HEADER_KEY_ID: key_id,
        HEADER_TIMESTAMP: str(timestamp),
        HEADER_SIGNATURE: sign(secret, timestamp, method, path, body),
    }


def build_token_headers(token: str, version: str, method: str, path: str, body: bytes) -> dict[str, str]:
    """分发 token 模式：token 兼作 HMAC 密钥与身份标识，另带客户端版本号。"""
    timestamp = int(time.time())
    return {
        HEADER_TOKEN: token,
        HEADER_VERSION: version,
        HEADER_TIMESTAMP: str(timestamp),
        HEADER_SIGNATURE: sign(token, timestamp, method, path, body),
    }


HEADER_TOKEN = "X-SE-Token"
HEADER_VERSION = "X-SE-Version"


def verify(
    secret: str,
    timestamp: int,
    method: str,
    path: str,
    body: bytes,
    signature: str,
) -> bool:
    expected = sign(secret, timestamp, method, path, body)
    return hmac.compare_digest(expected, signature)
