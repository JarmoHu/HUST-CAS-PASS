// ==UserScript==
// @name         华科CAS系统辅助脚本
// @namespace    http://tampermonkey.net/
// @version      1.0.0
// @description  华科CAS统一认证系统数据提取,在网页右下角创建可折叠框，显示并一键复制指定的 UA 和 VisitorID 格式
// @author       JarmoHu
// @match        *://pass.hust.edu.cn/*
// @grant        GM_setClipboard
// @run-at       document-end
// @license      MIT
// ==/UserScript==

(function () {
  "use strict";

  // 1. 获取网页源码（模拟你后端的提取逻辑）
  const htmlText = document.documentElement.outerHTML;

  // 2. 使用正则提取数据（完全匹配你提供的正则规则）
  const visitorIdMatch = htmlText.match(
    /<input id="visitorId" type="hidden" name="visitorId" value=["'](.*?)["']>/,
  );
  const uaMatch = htmlText.match(
    /<input id="ua" type="hidden" name="ua" value=["'](.*?)["']>/,
  );

  const visitorId = visitorIdMatch ? visitorIdMatch[1] : "未找到";
  const ua = uaMatch ? uaMatch[1] : "未找到";

  // 3. 创建 UI 样式
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
    `;
  document.head.appendChild(style);

  // 4. 创建 DOM 结构
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
                <div class="ua-box-value">${visitorId}</div>
            </div>
            <div class="ua-box-item">
                <div class="ua-box-label">User Agent (ua):</div>
                <div class="ua-box-value">${ua}</div>
            </div>
            <button id="ua-box-copy-btn">📋 一键复制 Python 格式</button>
        </div>
    `;
  document.body.appendChild(container);

  // 5. 交互事件：折叠与展开
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

  // 6. 交互事件：一键复制
  const copyBtn = document.getElementById("ua-box-copy-btn");
  copyBtn.addEventListener("click", () => {
    // 构建你需要的指定格式
    const formatText = `UaVisitorIdPair(ua="${ua}",visitor="${visitorId}")`;

    // 使用油猴专用的高级剪贴板API（比原生JS更稳定，不容易受安全策略限制）
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
})();
