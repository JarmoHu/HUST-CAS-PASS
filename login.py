from enum import Enum, unique
import json
import re
from base64 import b64decode, b64encode
from html import unescape
from logging import root as log
from typing import Optional

import httpx
import requests
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA

from .decaptcha import decaptcha


LOGIN_URL = "https://pass.hust.edu.cn/cas/login"
RSA_URL = "https://pass.hust.edu.cn/cas/rsa"
CAPTCHA_URL = "https://pass.hust.edu.cn/cas/code"
MAX_LOGIN_ATTEMPTS = 3


@unique
class LoginMethod(Enum):
    ACCOUNT = "account"  # 账号密码登录
    QRCODE = "qrcode"  # 二维码登录


class UaVisitorIdPair:
    def __init__(
        self,
        ua: str = '{"ua":"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0","browser":{"name":"Firefox","version":"150.0","major":"150"},"cpu":{"architecture":"amd64"},"device":{},"engine":{"name":"Gecko","version":"150.0"},"os":{"name":"Windows","version":"10"}}',
        visitorId: str = "e6e94e9680a9382b7c0f96404a5b9022",
    ):
        self.ua = ua
        self.visitorId = visitorId


def _extract_hidden_value(html: str, name: str) -> str:
    match = re.search(rf'<input[^>]*name="{re.escape(name)}"[^>]*value="([^"]*)"', html)
    if match is None:
        raise ValueError("HUSTPASS: LOGIN FORM CHANGED, MISSING {}".format(name))
    return match.group(1)


def _captcha_required(html: str) -> bool:
    return 'id="codeImage"' in html or 'id="code"' in html


# 注意：函数名前面需要加上 async
async def _load_public_key(client: httpx.AsyncClient) -> RSA.RsaKey:
    # 1. 异步发送 POST 请求
    response = await client.post(RSA_URL)

    # 2. 直接使用 .json() 获取字典，拿到公钥字符串
    # 如果接口返回的不是 200，建议先调用 response.raise_for_status() 抛出异常
    response.raise_for_status()
    public_key = response.json()["publicKey"]

    # 3. 保持原有的 RSA 解析逻辑不变
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
        log.warning("HUSTPASS: check login failed, code:{}".format(ret.status_code))
        return False
    return True


async def asynclogin(
    username: str,
    password: str,
    login_method: LoginMethod = LoginMethod.ACCOUNT,
    client: Optional[httpx.AsyncClient] = None,
    extra_headers: Optional[dict] = None,
    extra_cookies: Optional[dict] = None,
    ua_visitor_id_pair: Optional[UaVisitorIdPair] = None,
):
    """
    PARAMETERS:\n
    username -- Username of pass.hust.edu.cn  e.g. U2022XXXXX
    password -- Password of the user
    extra_headers -- Optional headers for the request
    client -- Optional async client for making requests
    login_method -- The login method to use
    extra_cookies -- Optional dictionary of additional cookies to include in the login request
    ua_visitor_id_pair -- Optional UaVisitorIdPair object containing UA and visitorId
    """
    if not isinstance(username, str) or not isinstance(password, str):
        raise TypeError("HUSTPASS: CHECK YOUR UID AND PWD TYPE")

    if extra_headers is not None and not isinstance(extra_headers, dict):
        raise TypeError("HUSTPASS: CHECK YOUR EXTRA_HEADERS TYPE")
    if extra_cookies is not None and not isinstance(extra_cookies, dict):
        raise TypeError("HUSTPASS: CHECK YOUR EXTRA_COOKIES TYPE")
    if client is not None and not isinstance(client, httpx.AsyncClient):
        raise TypeError("HUSTPASS: CHECK YOUR CLIENT TYPE")
    if ua_visitor_id_pair is not None and not isinstance(
        ua_visitor_id_pair, UaVisitorIdPair
    ):
        raise TypeError("HUSTPASS: CHECK YOUR UA_VISITOR_ID_PAIR TYPE")

    # Use the provided UaVisitorIdPair or create a default one
    if ua_visitor_id_pair is None:
        ua_visitor_id_pair = UaVisitorIdPair()

    # 输入有效检查
    if not client:
        client = httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0"
            }
        )

    if len(username) == 0 or len(password) == 0:
        raise ValueError("HUSTPASS: YOUR UID OR PWD IS EMPTY")

    if not isinstance(ua_visitor_id_pair.ua, str) or not isinstance(
        ua_visitor_id_pair.visitorId, str
    ):
        raise TypeError(
            "HUSTPASS: ua_visitor_id_pair.ua AND ua_visitor_id_pair.visitorId MUST BE STRINGS"
        )

    # 建立session
    log.info("setting up session...")
    client.headers.update(extra_headers)
    if extra_cookies is not None:
        client.cookies.update(extra_cookies)

    for attempt in range(1, MAX_LOGIN_ATTEMPTS + 1):
        login_html = await client.get(LOGIN_URL)
        nonce = _extract_hidden_value(login_html.text, "lt")
        execution = _extract_hidden_value(login_html.text, "execution")

        captcha_code = ""
        if _captcha_required(login_html.text):
            captcha_img = await client.get(CAPTCHA_URL)
            log.info("captcha detected, trying to decaptcha...")
            captcha_code = decaptcha(captcha_img.content).strip()

        log.debug("encrypting u/p...")
        cipher = PKCS1_v1_5.new(await _load_public_key(client))
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
        log.debug("posting login-form...")
        resp = await client.post(LOGIN_URL, data=post_params, follow_redirects=False)
        if "Location" in resp.headers:
            log.info("---HustPass Succeed---")
            log.debug("Thank you for using hust_login")
            return resp

        error_message = await _extract_error_message(resp.text)
        if "验证码" in error_message and attempt < MAX_LOGIN_ATTEMPTS:
            log.warning("captcha rejected, retrying login...")
            continue
        raise ConnectionRefusedError(
            error_message if error_message else "---HustPass Failed---"
        )

    raise ConnectionRefusedError("---HustPass Failed---")
