import asyncio
import json
import random
import re
import uuid
from base64 import b64decode, b64encode
from dataclasses import dataclass
from html import unescape
from typing import Optional, Dict

import aioconsole
import httpx
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA
from loguru import logger

from .decaptcha import decaptcha

LOGIN_URL = "https://pass.hust.edu.cn/cas/login"
RSA_URL = "https://pass.hust.edu.cn/cas/rsa"
CAPTCHA_URL = "https://pass.hust.edu.cn/cas/code"
MAX_LOGIN_ATTEMPTS = 3

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0"
)


@dataclass
class UaVisitorIdPair:
    ua: str = '{"ua":"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0","browser":{"name":"Firefox","version":"150.0","major":"150"},"cpu":{"architecture":"amd64"},"device":{},"engine":{"name":"Gecko","version":"150.0"},"os":{"name":"Windows","version":"10"}}'
    visitorId: str = "e6e94e9680a9382b7c0f96404a5b9022"


def _prepare_client(
    client: Optional[httpx.AsyncClient] = None,
    extra_headers: Optional[Dict[str, str]] = None,
    extra_cookies: Optional[Dict[str, str]] = None,
) -> httpx.AsyncClient:
    """辅助函数：初始化并配置 HTTPX 异步客户端"""
    if client is None:
        client = httpx.AsyncClient(headers={"User-Agent": DEFAULT_USER_AGENT})
    elif not isinstance(client, httpx.AsyncClient):
        raise TypeError("HUSTPASS: CHECK YOUR CLIENT TYPE (Must be httpx.AsyncClient)")

    if extra_headers:
        client.headers.update(extra_headers)
    if extra_cookies:
        client.cookies.update(extra_cookies)

    return client


def _extract_hidden_value(html: str, name: str) -> str:
    match = re.search(rf'<input[^>]*name="{re.escape(name)}"[^>]*value="([^"]*)"', html)
    if match is None:
        raise ValueError(f"HUSTPASS: LOGIN FORM CHANGED, MISSING {name}")
    return match.group(1)


def _captcha_required(html: str) -> bool:
    return 'id="codeImage"' in html or 'id="code"' in html


async def _load_public_key(client: httpx.AsyncClient) -> RSA.RsaKey:
    response = await client.post(RSA_URL)
    response.raise_for_status()
    public_key = response.json()["publicKey"]

    try:
        return RSA.import_key(b64decode(public_key))
    except (ValueError, TypeError):
        return RSA.import_key(public_key)


async def _extract_error_message(html: str) -> str:
    match = re.search(r'<span id="errormsghide">(.*?)</span>', html, re.S)
    if match is None:
        return ""
    return unescape(re.sub(r"<[^>]+>", "", match.group(1))).strip()


async def CheckLoginStatus(client: httpx.AsyncClient) -> bool:
    """
    Check login status\n
    Return False if is not logged in
    """
    ret = await client.get("https://one.hust.edu.cn")
    if ret.status_code != 200:
        logger.warning(f"HUSTPASS: check login failed, code:{ret.status_code}")
        return False
    return True


async def login_by_qrcode(
    username: str,
    client: Optional[httpx.AsyncClient] = None,
    extra_headers: Optional[Dict[str, str]] = None,
    extra_cookies: Optional[Dict[str, str]] = None,
):
    client = _prepare_client(client, extra_headers, extra_cookies)
    await client.get(LOGIN_URL)

    uuid_str = str(uuid.uuid4())
    link_str = f"https://pass.hust.edu.cn/cas/qyQrLogin?uuid={uuid_str}&service=http%3A%2F%2Fwn-wnlo.hust.edu.cn%2Fcas%2Flogin%2F%3Fnext%3D%252F"
    logger.info(f"请使用微信登录，链接：{link_str}")

    # 使用 await client.post 避免阻塞事件循环，并带上 tid 以支持多任务同步
    response = await client.post(
        "https://wechat-push.00660066.xyz/push_url",
        json={"tid": f"hustcas{username}", "url": link_str},
    )

    if response.status_code == 200 and response.json().get("status") == "success":
        logger.info("✅ 登录链接已发送至云端，等待微信浏览器接管...")
    else:
        raise ConnectionError("❌ 登录链接推送失败，请检查网络或联系管理员")

    while True:
        try:
            r = await client.get(
                f"https://pass.hust.edu.cn/cas/checkQRCodeScan?random={random.random()}&uuid={uuid_str}"
            )
            if r.status_code == 200:
                if "application/json" in r.headers.get("content-type", ""):
                    logger.info("✅ 扫码登录成功")
                    return r
                else:
                    logger.debug("扫码登录中...（服务器还未返回JSON，继续等待）")
            else:
                logger.debug("扫码登录中...")
        except Exception as e:
            logger.error(f"扫码登录请求异常，2s后重试，错误内容：{str(e)}")

        await asyncio.sleep(2)


async def login_by_account(
    username: str,
    password: str,
    client: Optional[httpx.AsyncClient] = None,
    extra_headers: Optional[Dict[str, str]] = None,
    extra_cookies: Optional[Dict[str, str]] = None,
    ua_visitor_id_pair: Optional[UaVisitorIdPair] = None,
):
    if not username or not password:
        raise ValueError("HUSTPASS: YOUR UID OR PWD IS EMPTY")

    client = _prepare_client(client, extra_headers, extra_cookies)
    ua_visitor_id_pair = ua_visitor_id_pair or UaVisitorIdPair()

    # 解析 pair 中的 User-Agent，并让其拥有最高优先级，保持前后端一致性
    try:
        ua_data = json.loads(ua_visitor_id_pair.ua)
        pair_ua_str = ua_data.get("ua", DEFAULT_USER_AGENT)
    except (json.JSONDecodeError, TypeError):
        pair_ua_str = str(ua_visitor_id_pair.ua)

    client.headers["User-Agent"] = pair_ua_str

    for attempt in range(1, MAX_LOGIN_ATTEMPTS + 1):
        login_html = await client.get(LOGIN_URL)
        nonce = _extract_hidden_value(login_html.text, "lt")
        execution = _extract_hidden_value(login_html.text, "execution")

        captcha_code = ""
        if _captcha_required(login_html.text):
            captcha_img = await client.get(CAPTCHA_URL)
            logger.info("captcha detected, trying to decaptcha...")
            captcha_code = decaptcha(captcha_img.content).strip()

        logger.debug("encrypting u/p...")
        public_key = await _load_public_key(client)
        cipher = PKCS1_v1_5.new(public_key)
        encrypted_u = b64encode(cipher.encrypt(username.encode())).decode()
        encrypted_p = b64encode(cipher.encrypt(password.encode())).decode()

        post_params = {
            "ua": ua_visitor_id_pair.ua,
            "visitorId": ua_visitor_id_pair.visitorId,
            "rsa": ["", ""],
            "ul": encrypted_u,
            "pl": encrypted_p,
            "code": captcha_code,
            "phoneCode": "",
            "lt": nonce,
            "execution": execution,
            "_eventId": "submit",
        }

        logger.debug(f"posting login-form (Attempt {attempt}/{MAX_LOGIN_ATTEMPTS})...")
        resp = await client.post(LOGIN_URL, data=post_params, follow_redirects=False)

        if "Location" in resp.headers:
            logger.info("---HustPass Succeed---")
            return resp

        if "双因子认证" in resp.text:
            logger.info("Two-factor authentication required.")
            phonecode = await aioconsole.ainput("请输入企业微信验证码: ")
            post_params["phoneCode"] = phonecode.strip()
            resp = await client.post(
                LOGIN_URL, data=post_params, follow_redirects=False
            )
            if "Location" in resp.headers:
                logger.info("---HustPass Succeed---")
                return resp

        error_message = await _extract_error_message(resp.text)
        if "验证码" in error_message and attempt < MAX_LOGIN_ATTEMPTS:
            logger.warning(f"captcha rejected, retrying login... ({error_message})")
            continue

        raise ConnectionRefusedError(
            error_message if error_message else "---HustPass Failed---"
        )

    raise ConnectionRefusedError("---HustPass Failed (Max attempts reached)---")
