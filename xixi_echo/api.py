"""评分服务 API 客户端（签名 + multipart 上传）。所有网络调用在工作线程里跑。"""

from __future__ import annotations

import base64
import json
from typing import TypedDict
from urllib.parse import urlsplit

import httpx

from . import __version__, signing
from .config import Settings


class ApiError(Exception):
    """带用户可读 message 的 API 错误；status/code 供上层分支（如 401 自愈）。"""

    def __init__(self, message: str, status: int = 0, code: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.code = code


class CharInfo(TypedDict):
    name: str
    star: int
    attr: str
    attr_zh: str
    avatar_url: str | None
    in_tuning: bool


class ScoreResult:
    def __init__(self, matched_character: str, image: bytes, elapsed_ms: int) -> None:
        self.matched_character = matched_character
        self.image = image
        self.elapsed_ms = elapsed_ms


def _friendly(status: int, code: str, message: str) -> str:
    if status == 401:
        return "身份凭据已失效或被停用，请重新申请评分资格"
    if status == 429:
        return "请求太频繁，请等几秒再试"
    if status in (502, 503):
        return message or "评分服务暂时不可用，请稍后重试"
    return message or f"请求失败（HTTP {status}）"


def _post_error(resp: httpx.Response) -> ApiError:
    try:
        data = json.loads(resp.text)
    except json.JSONDecodeError:
        return ApiError(f"请求失败（HTTP {resp.status_code}）", status=resp.status_code)
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        code = error.get("code") if isinstance(error.get("code"), str) else ""
        message = error.get("message") if isinstance(error.get("message"), str) else ""
        return ApiError(_friendly(resp.status_code, code, message), status=resp.status_code, code=code)
    return ApiError(f"请求失败（HTTP {resp.status_code}）", status=resp.status_code)


class GatewayClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _auth_mode(self) -> str:
        # 分发 token 优先；旧静态 key 兼容
        return "token" if self._settings.token else "legacy"

    def _sign_headers(self, method: str, path: str, body: bytes) -> dict[str, str]:
        s = self._settings
        if self._auth_mode() == "token":
            return signing.build_token_headers(s.token, __version__, method, path, body)
        return signing.build_headers(s.key_id, s.secret, method, path, body)

    def chars(self) -> list[CharInfo]:
        path = "/api/v1/chars"
        url = self._settings.server_url + path
        headers = self._sign_headers("GET", path, b"")
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(url, headers=headers)
        if resp.status_code != 200:
            raise _post_error(resp)
        data = json.loads(resp.text)
        chars = data.get("chars") if isinstance(data, dict) else None
        if not isinstance(chars, list):
            raise ApiError("角色目录格式异常")
        return [c for c in chars if isinstance(c, dict) and isinstance(c.get("name"), str)]

    def score(self, char: str, images: list[bytes]) -> ScoreResult:
        path = "/api/v1/score"
        url = self._settings.server_url + path
        files = [(f"shot{i}.png", blob, "image/png") for i, blob in enumerate(images)]
        with httpx.Client(timeout=120.0) as client:
            request = client.build_request("POST", url, data={"char": char}, files=[("files", f) for f in files])
            request.read()
            real_path = urlsplit(str(request.url)).path
            request.headers.update(self._sign_headers("POST", real_path, request.content))
            resp = client.send(request)
        if resp.status_code != 200:
            raise _post_error(resp)
        data = json.loads(resp.text)
        image_b64 = data.get("image_base64") if isinstance(data, dict) else None
        if not isinstance(image_b64, str) or not image_b64:
            raise ApiError("服务端未返回评分图")
        return ScoreResult(
            matched_character=data.get("matched_character") if isinstance(data.get("matched_character"), str) else "",
            image=base64.b64decode(image_b64),
            elapsed_ms=data.get("elapsed_ms") if isinstance(data.get("elapsed_ms"), int) else 0,
        )

    # —— 分发 token ——

    def token_check(self) -> dict:
        """核查 token 有效性；被吊销/停用会抛 ApiError(status=401)。"""
        path = "/api/v1/token/check"
        headers = self._sign_headers("GET", path, b"")
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(self._settings.server_url + path, headers=headers)
        if resp.status_code != 200:
            raise _post_error(resp)
        return json.loads(resp.text)

    def apply_token(self, qq: str, note: str) -> dict:
        url = self._settings.server_url + "/api/v1/distribute/apply"
        headers = {"Content-Type": "application/json"}
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(url, json={"qq": qq, "version": __version__, "note": note}, headers=headers)
        return self._json_or_error(resp)

    def token_status(self, qq: str, ticket: str) -> dict:
        path = f"/api/v1/distribute/status/{qq}"
        headers = {"Content-Type": "application/json"}
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(self._settings.server_url + path, params={"ticket": ticket}, headers=headers)
        return self._json_or_error(resp)

    def _json_or_error(self, resp: httpx.Response) -> dict:
        try:
            data = json.loads(resp.text)
        except json.JSONDecodeError:
            raise ApiError(f"请求失败（HTTP {resp.status_code}）")
        if resp.status_code >= 400:
            error = data.get("error") if isinstance(data, dict) else None
            if isinstance(error, dict):
                raise ApiError(_friendly(resp.status_code, error.get("code", ""), error.get("message", "")))
            raise ApiError(f"请求失败（HTTP {resp.status_code}）")
        return data
