export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;
    
    // 从 URL 参数中获取 tid，如果没有提供则默认为 "default"
    const tid = url.searchParams.get("tid") || "default";

    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET,HEAD,POST,OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    };

    if (request.method === "OPTIONS") return new Response(null, { headers: corsHeaders });

    // 1. 微信浏览器前端界面 (加入重连机制与心跳包)
    if (path === "/") {
      const html = `
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <title>微信自动化挂机节点 (高可用版)</title>
          <style>
            body { font-family: sans-serif; text-align: center; padding-top: 50px; background-color: #f4f5f7; }
            #status { color: #07c160; font-size: 20px; font-weight: bold; }
            .loader { margin: 20px auto; border: 4px solid #e0e0e0; border-top: 4px solid #07c160; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; }
            .task-id { margin-top: 10px; font-size: 14px; color: #555; background: #e8e8e8; display: inline-block; padding: 4px 12px; border-radius: 12px; }
            @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
          </style>
        </head>
        <body>
          <h2>微信自动化中转站</h2>
          <div class="task-id">当前任务 ID: <span id="display-tid"></span></div>
          <div class="loader"></div>
          <p id="status">正在建立长连接...</p>
          <p style="font-size: 12px; color: #888;" id="ping-status">心跳监控初始化中...</p>
          <script>
            const urlParams = new URLSearchParams(window.location.search);
            const currentTid = urlParams.get('tid') || 'default';
            document.getElementById('display-tid').innerText = currentTid;

            const wsProtocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
            // WebSocket 建立时带上 tid
            const wsUrl = wsProtocol + '//' + location.host + '/ws_wechat?tid=' + currentTid;
            let ws;
            let heartbeatTimer;
            let timeoutTimer;
            let reconnectDelay = 2000;

            function connect() {
              ws = new WebSocket(wsUrl);

              ws.onopen = () => { 
                document.getElementById('status').innerText = '🟢 长连接已就绪，等待指令...'; 
                document.getElementById('ping-status').innerText = '心跳正常';
                reconnectDelay = 2000; 
                
                heartbeatTimer = setInterval(() => {
                  if (ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({ type: 'ping' }));
                    timeoutTimer = setTimeout(() => {
                      document.getElementById('ping-status').innerText = '⚠️ 心跳超时，尝试重启连接...';
                      ws.close();
                    }, 5000);
                  }
                }, 20000);
              };

              ws.onmessage = async (event) => {
                const data = JSON.parse(event.data);
                
                if (data.type === 'pong') {
                  clearTimeout(timeoutTimer);
                  document.getElementById('ping-status').innerText = '心跳正常 (最后响应: ' + new Date().toLocaleTimeString() + ')';
                  return;
                }

                if (data.url) {
                  document.getElementById('status').innerText = '⚡ 收到跳转指令！' + data.url;
                  // 通知服务端时带上 tid
                  await fetch('/notify_click', { 
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ tid: currentTid })
                  });
                  setTimeout(() => { window.location.href = data.url; }, 500);
                }
              };

              ws.onclose = () => { 
                clearInterval(heartbeatTimer);
                clearTimeout(timeoutTimer);
                document.getElementById('status').innerText = '🔴 连接断开，准备重连...'; 
                document.getElementById('ping-status').innerText = '等待重连中 (' + reconnectDelay/1000 + 's)';
                
                setTimeout(connect, reconnectDelay); 
                reconnectDelay = Math.min(reconnectDelay * 2, 30000);
              };
            }
            connect();
          </script>
        </body>
        </html>
      `;
      return new Response(html, { headers: { "Content-Type": "text/html;charset=UTF-8" } });
    }

    // 2. 微信 WebSocket 处理逻辑
    if (path === "/ws_wechat") {
      if (request.headers.get("Upgrade") !== "websocket") return new Response("Expected websocket", { status: 426 });

      const { 0: client, 1: server } = new WebSocketPair();
      server.accept();

      server.addEventListener("message", (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "ping") {
             server.send(JSON.stringify({ type: "pong" }));
          }
        } catch(e) {}
      });

      // 使用带 tid 的隔离键值
      const targetKey = `target_url_${tid}`;
      
      let intervalId = setInterval(async () => {
        try {
          const targetUrl = await env.WECHAT_KV.get(targetKey);
          if (targetUrl) {
            server.send(JSON.stringify({ url: targetUrl }));
            await env.WECHAT_KV.delete(targetKey); 
          }
        } catch (e) {}
      }, 3000);

      server.addEventListener("close", () => clearInterval(intervalId));

      return new Response(null, { status: 101, webSocket: client });
    }

    // 3. Python WebSocket 监听点击信号
    if (path === "/ws_python") {
      if (request.headers.get("Upgrade") !== "websocket") return new Response("Expected websocket", { status: 426 });

      const { 0: client, 1: server } = new WebSocketPair();
      server.accept();

      server.addEventListener("message", (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "ping") server.send(JSON.stringify({ type: "pong" }));
        } catch(e) {}
      });

      // 使用带 tid 的隔离键值
      const signalKey = `click_signal_${tid}`;

      let intervalId = setInterval(async () => {
        try {
          const signal = await env.WECHAT_KV.get(signalKey);
          if (signal === "true") {
            server.send(JSON.stringify({ click: true, tid: tid }));
            await env.WECHAT_KV.delete(signalKey);
          }
        } catch (e) {}
      }, 1500); 

      server.addEventListener("close", () => clearInterval(intervalId));

      return new Response(null, { status: 101, webSocket: client });
    }

    // 4. 下发目标 URL (Python 端调用)
    if (path === "/push_url" && request.method === "POST") {
      try {
        const body = await request.json();
        // 允许通过 JSON 传入 tid，若无则使用 URL 中的 tid
        const taskTid = body.tid || tid;
        
        await env.WECHAT_KV.put(`target_url_${taskTid}`, body.url, { expirationTtl: 60 });
        await env.WECHAT_KV.put(`click_signal_${taskTid}`, "false", { expirationTtl: 60 });
        
        return new Response(JSON.stringify({ status: "success", tid: taskTid }), { headers: corsHeaders });
      } catch (error) {
        return new Response(JSON.stringify({ error: "Invalid JSON" }), { status: 400, headers: corsHeaders });
      }
    }

    // 5. 微信浏览器前端通知点击成功
    if (path === "/notify_click" && request.method === "POST") {
      try {
        let taskTid = tid;
        // 尝试从请求体获取 tid
        if (request.headers.get("Content-Type")?.includes("application/json")) {
          const body = await request.json();
          taskTid = body.tid || tid;
        }
        
        await env.WECHAT_KV.put(`click_signal_${taskTid}`, "true", { expirationTtl: 60 });
        return new Response("OK", { headers: corsHeaders });
      } catch (error) {
        return new Response("Error processing request", { status: 400, headers: corsHeaders });
      }
    }

    return new Response("Not Found", { status: 404 });
  }
};