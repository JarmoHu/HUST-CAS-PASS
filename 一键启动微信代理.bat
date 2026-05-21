@echo off
chcp 65001 > nul
title 微信代理 mitmproxy 端口31800

mitmdump -s "%~dp0auto_login.py" -p 31800 --allow-hosts "pass\.hust\.edu\.cn|mitm\.it" -q

