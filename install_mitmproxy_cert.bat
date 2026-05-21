@echo off
chcp 65001 > nul
setlocal EnableExtensions

net session >nul 2>&1
if not %errorlevel%==0 (
    echo 请使用管理员权限运行此脚本。
    echo 右键以管理员身份运行，或先打开管理员 PowerShell / CMD 再执行。
    exit /b 1
)

set "CERT_DIR=%USERPROFILE%\.mitmproxy"
set "CERT_FILE=%CERT_DIR%\mitmproxy-ca-cert.cer"

if not exist "%CERT_DIR%" (
    echo 未找到证书目录：%CERT_DIR%
    echo 请先启动一次 mitmproxy 生成证书文件，再重新运行本脚本。
    exit /b 1
)

if not exist "%CERT_FILE%" (
    echo 未找到证书文件：%CERT_FILE%
    echo 请确认 mitmproxy 已生成 mitmproxy-ca-cert.cer。
    exit /b 1
)

pushd "%CERT_DIR%"
echo 正在导入 mitmproxy 根证书...
certutil.exe -addstore root mitmproxy-ca-cert.cer
set "CERTUTIL_ERROR=%errorlevel%"
popd

if not "%CERTUTIL_ERROR%"=="0" (
    echo 证书导入失败，错误码：%CERTUTIL_ERROR%
    exit /b %CERTUTIL_ERROR%
)

echo 证书导入完成。
exit /b 0