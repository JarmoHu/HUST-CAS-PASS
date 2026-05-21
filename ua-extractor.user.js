// ==UserScript==
// @name         华科CAS系统辅助脚本
// @namespace    http://tampermonkey.net/
// @version      1.1.0
// @description  华科CAS统一认证系统数据提取,在网页右下角创建可折叠框，显示并一键复制指定的 UA 和 VisitorID 格式（支持动态延迟加载获取）
// @author       JarmoHu
// @match        *://pass.hust.edu.cn/*
// @grant        GM_setClipboard
// @run-at       document-end
// @license      MIT
// ==/UserScript==

(function () {
  "use strict";

  // 1. 初始化变量
  let visitorId = "正在获取...";
  let ua = "正在获取...";

  // 2. 创建 UI 样式
  const style = document.createElement("style");
  style.innerHTML = `
        #ua-box-container {
            position: fixed;
            bottom: 20px;
            right: 20px;
            z-index: 10000;
            background: #ffffff;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            font-size: 13px;
            width: 280px;
            transition: all 0.3s ease;
            overflow: hidden;
        }
        #ua-box-header {
            background: #f5f5f7;
            padding: 10px 14px;
            cursor: pointer;
            font-weight: bold;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #e0e0e0;
            user-select: none;
        }
        #ua-box-body {
            padding: 14px;
            display: none; /* 默认折叠 */
            background: #fff;
        }
        .ua-box-item {
            margin-bottom: 10px;
        }
        .ua-box-label {
            font-weight: 600;
            color: #666;
            margin-bottom: 4px;
        }
        .ua-box-value {
            background: #f0f0f2;
            padding: 6px;
            border-radius: 4px;
            word-break: break-all;
            max-height: 60px;
            overflow-y: auto;
            font-family: monospace;
            font-size: 11px;
        }
        #ua-box-copy-btn {
            width: 100%;
            background: #0071e3;
            color: white;
            border: none;
            padding: 8px;
            border-radius: 4px;
            cursor: pointer;
            font-weight: 500;
            margin-top: 5px;
            transition: background 0.2s;
        }
        #ua-box-copy-btn:hover {
            background: #0077ed;
        }
        /* 正在获取时的闪烁动画 */
        .loading-text {
            animation: pulse 1.5s infinite;
            color: #ff9500;
        }
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
        }
    `;
  document.head.appendChild(style);

  // 3. 创建 DOM 结构 (为需要更新的元素加上了特定的 ID)
  const container = document.createElement("div");
  container.id = "ua-box-container";

  container.innerHTML = `
        <div id="ua-box-header">
            <span>🔍 凭证提取器</span>
            <span id="ua-box-arrow">▼</span>
        </div>
        <div id="ua-box-body">
            <div class="ua-box-item">
                <div class="ua-box-label">Visitor ID:</div>
                <div class="ua-box-value loading-text" id="display-visitorId">${visitorId}</div>
            </div>
            <div class="ua-box-item">
                <div class="ua-box-label">User Agent (ua):</div>
                <div class="ua-box-value loading-text" id="display-ua">${ua}</div>
            </div>
            <button id="ua-box-copy-btn">📋 一键复制 Python 格式</button>
        </div>
    `;
  document.body.appendChild(container);

  // 4. 交互事件：折叠与展开
  const header = document.getElementById("ua-box-header");
  const body = document.getElementById("ua-box-body");
  const arrow = document.getElementById("ua-box-arrow");

  let isExpanded = false;
  header.addEventListener("click", () => {
    isExpanded = !isExpanded;
    if (isExpanded) {
      body.style.display = "block";
      arrow.textContent = "▲";
    } else {
      body.style.display = "none";
      arrow.textContent = "▼";
    }
  });

  // 5. 交互事件：一键复制
  const copyBtn = document.getElementById("ua-box-copy-btn");
  copyBtn.addEventListener("click", () => {
    if (visitorId === "正在获取..." || ua === "正在获取...") {
        alert("数据尚未获取完毕，请稍后再试！");
        return;
    }

    // 构建你需要的指定格式
    const formatText = `UaVisitorIdPair(ua="${ua}",visitor="${visitorId}")`;

    GM_setClipboard(formatText);

    // 按钮点击反馈效果
    const originalText = copyBtn.textContent;
    copyBtn.textContent = "✅ 复制成功！";
    copyBtn.style.background = "#34c759";
    setTimeout(() => {
      copyBtn.textContent = originalText;
      copyBtn.style.background = "#0071e3";
    }, 1500);
  });

  // 6. 动态监测逻辑 (轮询)
  let retryCount = 0;
  const maxRetries = 40; // 最多尝试 40 次 (40 * 250ms = 10秒)
  
  const checkDataInterval = setInterval(() => {
      // 改用 DOM 直接获取 value，比正则更准确地获取 JS 动态赋的值
      const visitorInput = document.getElementById("visitorId");
      const uaInput = document.getElementById("ua");

      const currentVisitor = visitorInput ? visitorInput.value : "";
      const currentUa = uaInput ? uaInput.value : "";

      // 如果两个值都已经被 JS 填充了
      if (currentVisitor && currentUa) {
          visitorId = currentVisitor;
          ua = currentUa;

          // 更新 UI 显示
          const visDisplay = document.getElementById("display-visitorId");
          const uaDisplay = document.getElementById("display-ua");
          
          visDisplay.textContent = visitorId;
          visDisplay.classList.remove("loading-text");
          
          uaDisplay.textContent = ua;
          uaDisplay.classList.remove("loading-text");

          // 数据获取成功，停止轮询
          clearInterval(checkDataInterval);
      } else {
          retryCount++;
          if (retryCount >= maxRetries) {
              // 超时处理
              clearInterval(checkDataInterval);
              document.getElementById("display-visitorId").textContent = "获取超时，未找到";
              document.getElementById("display-ua").textContent = "获取超时，未找到";
              document.getElementById("display-visitorId").classList.remove("loading-text");
              document.getElementById("display-ua").classList.remove("loading-text");
          }
      }
  }, 250); // 每 250 毫秒检查一次

})();