from mitmproxy import http

TARGET_DOMAIN = "pass.hust.edu.cn"


def response(flow: http.HTTPFlow) -> None:
    # 1. 基础过滤：必须是华科域名，且包含登录接口
    if (
        TARGET_DOMAIN in flow.request.pretty_url
        and "qyQrLogin" in flow.request.pretty_url
    ):
        # 2. 【硬核限定】只有当 URL 请求参数中明确包含 "code" 时才允许进入，否则直接放行不注入
        if "code" not in flow.request.query:
            return

        # 3. 确保返回的是标准的 HTML 文本
        if "text/html" not in flow.response.headers.get("content-type", "").lower():
            return

        try:
            if not flow.response:
                print("❌ 哎呀，响应体文本为空，无法注入脚本！")
                return
            html = flow.response.text
        except Exception as e:
            print(f"❌ 无法读取响应体文本: {e}")
            return

        # 延迟 300ms 强行弹射脚本
        inject_js = """
        <script>
            window.addEventListener('load', function() {
                console.log("🚀 [华科自动化] 页面资源已就绪，准备越过时差...");
                setTimeout(function() {
                    var btn = document.getElementById("confirmlogin");
                    if (btn) {
                        console.log("🎯 [华科自动化] 成功锁定授权按钮，触发点击！");
                        btn.click();
                    } else {
                        console.log("❌ [华科自动化] 未找到目标按钮");
                    }
                }, 5000);
            });
        </script>
        """

        # 4. 精准替换（兼容大小写 </html>）
        injected = False
        if "</html>" in html:
            flow.response.text = html.replace("</html>", f"{inject_js}\n</html>")
            injected = True
        elif "</HTML>" in html:
            flow.response.text = html.replace("</HTML>", f"{inject_js}\n</HTML>")
            injected = True

        # 5. 【满足需求】只要完成注入，立刻将最终的 doc 全文无死角打印到控制台
        if injected:
            print("\n" + "═" * 30 + " 📥 注入后的最终 HTML 全文 📥 " + "═" * 30)
            print(flow.response.text)
            print("═" * 88 + "\n")
            print(
                f"✅ [成功拦截] 已捕捉到带 code 密码的合法回调，并完成全文注入与日志快照！"
            )
