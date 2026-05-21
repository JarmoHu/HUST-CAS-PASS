# HUST CAS 登录辅助

这个仓库提供两种华科 CAS 登录方式：

1. 账号密码登录：需要先用油猴脚本从华科登录页提取 `ua` 和 `visitorId` 参数。[![Install](https://img.shields.io/badge/点击安装-油猴脚本-green.svg)](https://raw.githubusercontent.com/JarmoHu/HUST-CAS-PASS/main/ua-extractor.user.js)
2. 二维码登录：可以手动扫码授权；如果要全自动挂机，则需要给微信配置本地代理，并让微信先打开一个页面，等待它跳转到华科二维码授权页。



## 文件说明

- `login.py`：核心登录逻辑，包含账号密码登录和二维码登录。
- `decaptcha.py`：验证码识别，用于账号登录时处理页面验证码。
- `ua-extractor.user.js`：油猴脚本，用于从 `pass.hust.edu.cn` 提取 `ua` 和 `visitorId`。
- `auto_login.py`：给微信代理使用的 mitmproxy 脚本，用于拦截并自动点击二维码登录授权页。
- `一键启动微信代理.bat`：Windows 下启动微信代理的快捷脚本。
- `install_mitmproxy_cert.bat`：Windows 下的一键证书安装脚本。

## 安装依赖

建议使用 Python 3.10+。

```bash
pip install httpx aioconsole pycryptodome loguru pillow pytesseract mitmproxy
```

如果要使用验证码识别，还需要额外安装 Tesseract OCR：

- Windows：安装 tesseract 并把可执行文件加入环境变量
- Linux/macOS：安装系统包 `tesseract-ocr`

## 账号密码登录

账号密码登录依赖油猴脚本提取的两项参数：

- `ua`
- `visitorId`

### 1. 安装油猴脚本

把 `ua-extractor.user.js` 安装到 Tampermonkey，或者直接点击仓库顶部的安装按钮。

脚本要在常用浏览器里，先在华科登录页成功登录过一次的 `ua` 和 `visitorId`才不会跳出二验。退出登录后，再回到 `pass.hust.edu.cn` 页面右下角打开“凭证提取器”，读取页面里的 `ua` 和 `visitorId`。

### 2. 复制参数

脚本会给出一个类似 `UaVisitorIdPair(...)` 的格式。实际在 Python 里请按字段名填写：

```python
UaVisitorIdPair(ua='...', visitorId="...")
```

注意：字段名是 `visitorId`，不是 `visitor`。

### 3. 调用登录函数

`login.py` 里提供的核心函数是 `login_by_account`：

```python
from hust_login.login import login_by_account, UaVisitorIdPair

pair = UaVisitorIdPair(
	ua="这里填油猴脚本复制出来的 ua",
	visitorId="这里填油猴脚本复制出来的 visitorId",
)

client = await login_by_account(
	username="你的学号",
	password="你的密码",
	ua_visitor_id_pair=pair,
)
```

### 账号登录流程说明

`login_by_account` 的内部流程如下：

1. 先访问 `https://pass.hust.edu.cn/cas/login` 获取登录页。
2. 解析表单隐藏字段 `lt` 和 `execution`。
3. 如果页面要求验证码，就调用 `decaptcha.py` 识别验证码。
4. 从 `https://pass.hust.edu.cn/cas/rsa` 拉取 RSA 公钥，对学号和密码做加密。
5. 提交登录表单。
6. 如果触发企业微信双因子认证，会在终端里要求你输入验证码。

如果验证码识别失败或登录页结构变化，优先检查：

- 油猴脚本是否已经拿到正确的 `ua` 和 `visitorId`
- Tesseract OCR 是否已安装
- 华科登录页是否更新了字段名

## 二维码登录

二维码登录不走账号密码，而是走微信扫码授权。这个模式有两种用法：

1. 手动登录：直接打开微信里的授权页，扫码并点击确认，不需要本地代理，也不需要提前打开推送页。
2. 全自动挂机：需要启用本地代理，让 `auto_login.py` 在页面跳转到授权页后自动注入点击脚本。

### 1. 启动微信代理

Windows 下直接运行 `一键启动微信代理.bat` 即可。

它本质上会启动：

```bash
mitmdump -s "auto_login.py" -p 31800 --allow-hosts "pass\.hust\.edu\.cn" -q
```

这个代理脚本只拦截华科 CAS 的二维码授权回调页面，并在页面加载后自动点击授权按钮。

### 2. 给微信配置代理

如果要全自动挂机，把微信代理设置到本机 `127.0.0.1:31800`，并确保 mitmproxy 证书已被微信信任，否则代理无法正常解密和注入页面。

### 3. 安装 mitmproxy 证书

首次使用前需要安装 mitmproxy 的根证书。仓库里已经提供了一个一键脚本 `install_mitmproxy_cert.bat`，直接右键以管理员身份运行即可。

脚本会自动进入当前用户目录下的 `.mitmproxy` 文件夹，并执行：

```bat
certutil.exe -addstore root mitmproxy-ca-cert.cer
```

如果你想手动操作，流程也可以是：

1. 先启动一次代理，让 mitmproxy 生成证书文件。
2. 进入 `C:\Users\你的用户名\.mitmproxy`。
3. 在管理员 PowerShell 或 CMD 中执行 `certutil.exe -addstore root mitmproxy-ca-cert.cer`。
4. 如果微信仍然无法被代理解密，再检查系统代理、证书信任链和微信自己的网络设置。

### 4. 全自动挂机时提前打开推送页面

如果要做全自动挂机，在微信内置浏览器里先打开一个页面，让它继续跳转到推送页或授权页。例如先打开：

```text
https://wechat-push.00660066.xyz?tid=hustcas_<学号>
```

这里的 `tid` 必须和学号对应，格式是 `hustcas_<学号>`。之后由页面自己的跳转进入华科二维码授权页，`auto_login.py` 会在跳转后的页面里注入自动点击脚本。

### 5. 调用二维码登录函数

```python
from hust_login.login import login_by_qrcode

client = await login_by_qrcode(username="你的学号")
```

`login_by_qrcode` 会做这些事：

1. 先访问一次登录页初始化会话。
2. 生成一个二维码登录 `uuid`。
3. 把二维码登录链接推送到 `wechat-push.00660066.xyz/push_url`。
4. 轮询扫码状态，直到微信侧完成授权。

### 二维码登录流程说明

`auto_login.py` 的作用是代理微信打开的华科二维码授权页。当请求跳转到带 `code` 参数的回调页面后，它会注入一段脚本，延迟点击 `confirmlogin` 按钮，从而完成授权。

所以全自动挂机时，顺序一般是：

1. 先启动微信代理。
2. 先在微信里打开推送页面并等待它跳转。
3. 再运行二维码登录。
4. 等待页面自动点击授权。

如果你是手动扫码登录，则可以直接打开授权页，不必启动代理，也不必提前打开推送页。

## 常见问题

### 1. 直接运行 `login.py` 为什么不行

这个文件是作为模块被导入使用的，不建议直接双击运行。建议在项目父目录里通过 Python 导入调用。

### 2. 验证码识别失败怎么办

先确认 Tesseract OCR 已安装，再尝试重新登录。若页面验证码样式变化，可能需要调整 `decaptcha.py`。

### 3. 二维码登录一直卡住

通常是下面几类原因：

- 微信代理没有启动
- 微信没有走 `127.0.0.1:31800`
- 推送页面没有提前打开
- `tid` 和学号不一致

### 4. 为什么账号登录还要油猴脚本

因为代码里把 `ua` 和 `visitorId` 一起提交给 CAS，脚本用于从页面实时提取这两个值，避免手工填写出错。只有成功登录过的  `ua` 和 `visitorId` 才不会触发双因子认证验证码，从而自动化登录。

## 登录方式选择建议

- 如果你这边不经常触发双因子认证验证码，可以使用账号密码登录。
- 如果你这边要求绝对的全自动挂机（哪怕可能的双因子认证也不接收），那么选择二维码登录。配置过程很复杂，但是保证登录可靠性。

## Cloudflare Workers 自动同步源码

如果你已经上传了 `workers.js`，可以使用 GitHub Actions 自动发布到 Cloudflare Workers。

仓库里已提供：

- `wrangler.toml`：Worker 发布配置。
- `.github/workflows/deploy-worker.yml`：自动发布工作流。

### 1. 修改 wrangler 配置

编辑 `wrangler.toml`：

- `name` 改成你的 Worker 名称。
- `kv_namespaces.id` 改成你的 KV Namespace ID。
- `kv_namespaces.preview_id` 改成你的 KV Preview ID。

### 2. 配置 GitHub Secrets

在 GitHub 仓库 Settings -> Secrets and variables -> Actions 中新增：

- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`

说明：

- `CLOUDFLARE_API_TOKEN` 需要包含 Workers Scripts Edit 和 KV 编辑权限。
- `CLOUDFLARE_ACCOUNT_ID` 在 Cloudflare Dashboard 可以查看。

### 3. 触发自动同步

推送到 `main` 分支时，只要改动了 `workers.js` 或 `wrangler.toml`，就会自动部署。

也可以在 GitHub Actions 页手动点击 `Deploy Cloudflare Worker` 触发发布。

### 4. 本地手动发布（可选）

如果你想本地先验证，再交给 CI 自动同步：

```bash
npm install -g wrangler
wrangler login
wrangler deploy
```

## 许可证

本仓库遵循 `LICENSE` 中的授权条款。
