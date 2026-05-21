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

# ==========================================
# 常量定义 (Constants)
# ==========================================
LOGIN_URL = "https://pass.hust.edu.cn/cas/login"
RSA_URL = "https://pass.hust.edu.cn/cas/rsa"
CAPTCHA_URL = "https://pass.hust.edu.cn/cas/code"
PUSH_SERVICE_URL = "https://wechat-push.00660066.xyz/push_url"

MAX_LOGIN_ATTEMPTS = 3

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0"
DEFAULT_VISITOR_ID = "e6e94e9680a9382b7c0f96404a5b9022"
DEFAULT_UA_JSON = (
    '{"ua":"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0",'
    '"browser":{"name":"Firefox","version":"150.0","major":"150"},"cpu":{"architecture":"amd64"},'
    '"device":{},"engine":{"name":"Gecko","version":"150.0"},"os":{"name":"Windows","version":"10"}}'
)

# 预编译正则，提升性能与整洁度
ERROR_MSG_PATTERN = re.compile(r'<span id="errormsghide">(.*?)</span>', re.S)


# ==========================================
# 数据模型 (Models)
# ==========================================
@dataclass
class UaVisitorIdPair:
    ua: str = DEFAULT_UA_JSON
    visitorId: str = DEFAULT_VISITOR_ID


# ==========================================
# 辅助函数 (Utils)
# ==========================================
def _prepare_client(
    client: httpx.AsyncClient | None = None,
    extra_headers: Dict[str, str] | None = None,
    extra_cookies: Dict[str, str] | None = None,
) -> httpx.AsyncClient:
    """初始化并配置 HTTPX 异步客户端"""
    if client is None:
        client = httpx.AsyncClient(headers={"User-Agent": DEFAULT_USER_AGENT})
    elif not isinstance(client, httpx.AsyncClient):
        raise TypeError("HUSTPASS: CHECK YOUR CLIENT TYPE (Must be httpx.AsyncClient)")

    if extra_headers:
        client.headers.update(extra_headers)
    if extra_cookies:
        client.cookies.update(extra_cookies)
    return client


def _parse_user_agent(ua_raw: str) -> str:
    """从可能存在的 JSON 字符串中提取纯 UA 字符串"""
    try:
        return json.loads(ua_raw).get("ua", DEFAULT_USER_AGENT)
    except (json.JSONDecodeError, TypeError):
        return str(ua_raw)


def _extract_hidden_value(html: str, name: str) -> str:
    """提取表单中的隐藏字段"""
    match = re.search(rf'<input[^>]*name="{re.escape(name)}"[^>]*value="([^"]*)"', html)
    if not match:
        raise ValueError(f"HUSTPASS: LOGIN FORM CHANGED, MISSING {name}")
    return match.group(1)


def _captcha_required(html: str) -> bool:
    """检查是否需要验证码"""
    return 'id="codeImage"' in html or 'id="code"' in html


def _extract_error_message(html: str) -> str:
    """提取页面报错信息 (同步函数)"""
    match = ERROR_MSG_PATTERN.search(html)
    if not match:
        return ""
    return unescape(re.sub(r"<[^>]+>", "", match.group(1))).strip()


async def _load_public_key(client: httpx.AsyncClient) -> RSA.RsaKey:
    """拉取并解析 RSA 公钥"""
    response = await client.post(RSA_URL)
    response.raise_for_status()
    public_key = response.json()["publicKey"]

    try:
        return RSA.import_key(b64decode(public_key))
    except (ValueError, TypeError):
        return RSA.import_key(public_key)


# ==========================================
# 核心业务 (Core API)
# ==========================================
async def check_login_status(client: httpx.AsyncClient) -> bool:
    """检查当前 Client 的登录态是否有效"""
    ret = await client.get("https://one.hust.edu.cn")
    if ret.status_code != 200:
        logger.warning(f"HUSTPASS: Check login failed, status_code: {ret.status_code}")
        return False
    return True


async def login_by_qrcode(
    username: str,
    client: httpx.AsyncClient | None = None,
    extra_headers: Dict[str, str] | None = None,
    extra_cookies: Dict[str, str] | None = None,
    need_push: bool | None = True,
    push_service_url: str | None = None,
    
) -> httpx.AsyncClient:
    """扫码登录流程"""
    client = _prepare_client(client, extra_headers, extra_cookies)
    await client.get(LOGIN_URL)

    uuid_str = str(uuid.uuid4())
    link_str = f"https://pass.hust.edu.cn/cas/qyQrLogin?uuid={uuid_str}&service=http%3A%2F%2Fwn-wnlo.hust.edu.cn%2Fcas%2Flogin%2F%3Fnext%3D%252F"
    logger.info(f"🔗 请使用微信登录，链接：{link_str}")

    # 发送推送请求
    response = await client.post(
        push_service_url or PUSH_SERVICE_URL,
        json={"tid": f"hustcas_{username}", "url": link_str},
    )

    

    if response.status_code == 200 and response.json().get("status") == "success":
        logger.info("☁️ 登录链接已发送至云端，等待微信浏览器自动化处理")
    else:
        raise ConnectionError("❌ 登录链接推送失败，请检查网络或联系管理员")

    # 扁平化轮询检查
    while True:
        try:
            r = await client.get(
                f"https://pass.hust.edu.cn/cas/checkQRCodeScan?random={random.random()}&uuid={uuid_str}"
            )
            if r.status_code == 200 and "application/json" in r.headers.get("content-type", ""):
                logger.info("✅ 扫码登录成功")
                return client
            
            logger.debug("⏳ 扫码登录中 (等待中...)")
        except Exception as e:
            logger.error(f"⚠️ 扫码登录请求异常，2s后重试，错误内容：{e}")

        await asyncio.sleep(2)


async def login_by_account(
    username: str,
    password: str,
    client: httpx.AsyncClient | None = None,
    extra_headers: Dict[str, str] | None = None,
    extra_cookies: Dict[str, str] | None = None,
    ua_visitor_id_pair: UaVisitorIdPair | None = None,
) -> httpx.AsyncClient:
    """账号密码登录流程"""
    if not username or not password:
        raise ValueError("HUSTPASS: YOUR UID OR PWD IS EMPTY")

    client = _prepare_client(client, extra_headers, extra_cookies)
    pair = ua_visitor_id_pair or UaVisitorIdPair()

    # 解析并将 UA 注入 HTTP Client，保持高度一致性
    client.headers["User-Agent"] = _parse_user_agent(pair.ua)

    for attempt in range(1, MAX_LOGIN_ATTEMPTS + 1):
        logger.debug(f"🔄 登录尝试 ({attempt}/{MAX_LOGIN_ATTEMPTS})...")
        
        login_html = await client.get(LOGIN_URL)
        nonce = _extract_hidden_value(login_html.text, "lt")
        execution = _extract_hidden_value(login_html.text, "execution")

        # 验证码处理
        captcha_code = ""
        if _captcha_required(login_html.text):
            logger.info("🛡️ 发现验证码，正在尝试识别...")
            captcha_img = await client.get(CAPTCHA_URL)
            captcha_code = decaptcha(captcha_img.content).strip()

        # 密码加密
        public_key = await _load_public_key(client)
        cipher = PKCS1_v1_5.new(public_key)
        encrypted_u = b64encode(cipher.encrypt(username.encode())).decode()
        encrypted_p = b64encode(cipher.encrypt(password.encode())).decode()

        post_params = {
            "ua": pair.ua,
            "visitorId": pair.visitorId,
            "rsa": ["", ""],
            "ul": encrypted_u,
            "pl": encrypted_p,
            "code": captcha_code,
            "phoneCode": "",
            "lt": nonce,
            "execution": execution,
            "_eventId": "submit",
        }

        resp = await client.post(LOGIN_URL, data=post_params, follow_redirects=False)

        # 检查普通登录结果
        if "Location" in resp.headers:
            logger.info("✅ 账号密码登录成功")
            return client

        # 检查双因子认证
        if "双因子认证" in resp.text:
            logger.info("⚠️ 触发企业微信双因子认证")
            phone_code = await aioconsole.ainput("🔑 请输入企业微信验证码: ")
            post_params["phoneCode"] = phone_code.strip()
            
            resp = await client.post(LOGIN_URL, data=post_params, follow_redirects=False)
            if "Location" in resp.headers:
                logger.info("✅ 双因子认证登录成功")
                return client

        # 提取报错信息以决定下一步
        error_message = _extract_error_message(resp.text)
        
        if "验证码" in error_message and attempt < MAX_LOGIN_ATTEMPTS:
            logger.warning(f"❌ 验证码错误或失效，即将重试 ({error_message})")
            continue

        # 达到最大重试次数或其他致命错误
        raise ConnectionRefusedError(
            error_message if error_message else "---HustPass Failed (Unknown Error)---"
        )

    raise ConnectionRefusedError("---HustPass Failed (Max attempts reached)---")