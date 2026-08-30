/**
 * Bot AI — Embeddable Chat Widget

 * Usage on a tenant's site:
 *   <script src="https://cdn.example.com/widget.js"
 *           data-tenant-id="TENANT_UUID"
 *           data-api-url="https://api.example.com"
 *           data-color="#5B5BF0"
 *           data-position="bottom-right"
 *           data-greeting="Hi! How can I help you today?"
 *           defer></script>
 *
 * ---------------------------------------------------------------
 * API CONTRACT — now actually implemented below
 * ---------------------------------------------------------------
 * POST {apiUrl}/chat
 *   request:  {
 *     tenant_id: string (uuid),
 *     session_id: string (uuid) | null,   // null on first message
 *     question: string,
 *     top_k: number
 *   }
 *   response: {
 *     session_id: string (uuid), 
 *     answer: string,
 *     sources: Array<{ chunk_id: string, relevance_score: number }>
 *   }
 */

(function () {
  "use strict";

  function init() {
    var scriptTag =
      document.currentScript ||
      document.querySelector("script[data-tenant-id]");

    if (!scriptTag) {
      console.error("[BotAI Widget] Could not locate its own <script> tag.");
      return;
    }

    var config = {
      tenantId: scriptTag.getAttribute("data-tenant-id"),
      apiUrl: scriptTag.getAttribute("data-api-url") || "",
      color: scriptTag.getAttribute("data-color") || "#5B5BF0",
      position: scriptTag.getAttribute("data-position") || "bottom-right",
      greeting:
        scriptTag.getAttribute("data-greeting") ||
        "Hi! How can I help you today?",
    };

    if (!config.tenantId) {
      console.error(
        "[BotAI Widget] Missing required data-tenant-id attribute — widget not mounted."
      );
      return;
    }
    if (!config.apiUrl) {
      console.error(
        "[BotAI Widget] Missing data-api-url attribute — widget will mount but /chat calls will fail."
      );
    }

    mountWidget(config);
  }

  function mountWidget(config) {
    // Shadow DOM host: a plain, unstyled element sitting in the host
    // page's light DOM. Everything visual lives inside its shadow
    // tree, which the host page's CSS cannot select into, and whose
    // CSS cannot leak back out onto the host page.
    var host = document.createElement("div");
    var shadow = host.attachShadow({ mode: "open" });
    document.body.appendChild(host);

    var style = document.createElement("style");
    style.textContent = buildCSS(config);
    shadow.appendChild(style);

    var root = document.createElement("div");
    root.className = "botai-widget-root botai-widget-" + config.position;
    root.innerHTML =
      '<button class="botai-bubble" type="button" aria-label="Open chat" aria-expanded="false">' +
        bubbleIcon() +
      "</button>" +
      '<div class="botai-panel" hidden>' +
        '<div class="botai-panel-header">' +
          '<span class="botai-panel-title">Chat</span>' +
          '<button class="botai-close" type="button" aria-label="Close chat">' + closeIcon() + "</button>" +
        "</div>" +
        '<div class="botai-panel-body">' +
          '<div class="botai-messages" aria-live="polite"></div>' +
        "</div>" +
        '<div class="botai-panel-footer">' +
          '<input type="text" class="botai-input" placeholder="Type your question…" aria-label="Message" />' +
          '<button class="botai-send" type="button" aria-label="Send message">' + sendIcon() + "</button>" +
        "</div>" +
      "</div>";
    shadow.appendChild(root);

    var bubble = root.querySelector(".botai-bubble");
    var panel = root.querySelector(".botai-panel");
    var closeBtn = root.querySelector(".botai-close");
    var messagesEl = root.querySelector(".botai-messages");
    var inputEl = root.querySelector(".botai-input");
    var sendBtn = root.querySelector(".botai-send");

    var hasGreeted = false;
    var sessionId = null;
    var isSending = false;

    // sender is "bot" or "user" — only ever used to pick a CSS class.
    // Text always goes through textContent, never innerHTML, so a
    // visitor's typed message (or a bot answer) can never be parsed
    // as HTML/script.
    function appendMessage(text, sender) {
      var msg = document.createElement("div");
      msg.className = "botai-msg botai-msg-" + sender;
      msg.textContent = text;
      messagesEl.appendChild(msg);
      messagesEl.scrollTop = messagesEl.scrollHeight;
      return msg;
    }

    function appendTyping() {
      var wrap = document.createElement("div");
      wrap.className = "botai-msg botai-msg-bot botai-typing";
      wrap.innerHTML =
        '<span class="botai-typing-dots">' +
          '<span class="botai-dot"></span><span class="botai-dot"></span><span class="botai-dot"></span>' +
        "</span>";
      messagesEl.appendChild(wrap);
      messagesEl.scrollTop = messagesEl.scrollHeight;
      return wrap;
    }

    function setBusy(busy) {
      isSending = busy;
      inputEl.disabled = busy;
      sendBtn.disabled = busy;
    }

    function openPanel() {
      panel.hidden = false;
      bubble.setAttribute("aria-expanded", "true");
      if (!hasGreeted) {
        appendMessage(config.greeting, "bot");
        hasGreeted = true;
      }
      inputEl.focus();
    }
    function closePanel() {
      panel.hidden = true;
      bubble.setAttribute("aria-expanded", "false");
    }

    function handleSend() {
      if (isSending) return;
      var text = inputEl.value.trim();
      if (!text) return;

      appendMessage(text, "user");
      inputEl.value = "";

      if (!config.apiUrl) {
        appendMessage(
          "Chat isn't connected yet — missing data-api-url on the embed script.",
          "bot"
        );
        return;
      }

      setBusy(true);
      var typingEl = appendTyping();

      fetch(config.apiUrl + "/chat", {
        method: "POST",
        mode: "cors", // explicit for clarity — this IS a cross-origin
                       // request (tenant site → your API's domain).
                       // Browsers default to "cors" automatically for
                       // cross-origin fetch, but stating it makes the
                       // intent obvious to anyone reading this later.
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tenant_id: config.tenantId,
          session_id: sessionId,
          question: text,
          top_k: 5,
        }),
      })
        .then(function (res) {
          if (!res.ok) throw new Error("HTTP " + res.status);
          return res.json();
        })
        .then(function (data) {
          if (data && data.session_id) {
            sessionId = data.session_id;
          }
          typingEl.remove();
          appendMessage(
            (data && data.answer) || "(empty response from server)",
            "bot"
          );
        })
        .catch(function (err) {
          // Browsers deliberately don't tell JS *why* a fetch failed —
          // "Failed to fetch" / TypeError covers network-down, DNS
          // failure, AND a CORS block, all identically. This isn't a
          // bug in this code; it's a browser security choice (leaking
          // the real reason could itself expose info to malicious
          // scripts). Logging the target URL is the most useful thing
          // this file itself can do — the real answer lives in the
          // Network tab, not the console.
          console.error(
            "[BotAI Widget] /chat request failed. If this is a CORS " +
              "error, it'll say so explicitly in the Network tab response " +
              "headers, not here. Target was: " + config.apiUrl + "/chat",
            err
          );
          typingEl.remove();
          appendMessage(
            "Sorry, something went wrong reaching the server. Please try again.",
            "bot"
          );
        })
        .finally(function () {
          setBusy(false);
          inputEl.focus();
        });
    }

    bubble.addEventListener("click", function () {
      panel.hidden ? openPanel() : closePanel();
    });
    closeBtn.addEventListener("click", closePanel);
    sendBtn.addEventListener("click", handleSend);
    inputEl.addEventListener("keydown", function (e) {
      if (e.key === "Enter") handleSend();
    });

    // Exposed on the light-DOM window for host-page integrations
    // (e.g. a "Chat with us" link elsewhere on the tenant's page).
    window.__botaiWidget = { config: config, open: openPanel, close: closePanel };
  }

  function bubbleIcon() {
    return (
      '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
      '<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>' +
      "</svg>"
    );
  }

  function closeIcon() {
    return (
      '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
      '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>' +
      "</svg>"
    );
  }

  function sendIcon() {
    return (
      '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
      '<line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>' +
      "</svg>"
    );
  }

  function buildCSS(config) {
    return (
      // :host resets inherited properties (font, color, line-height,
      // etc.) that would otherwise cascade in from the host page's
      // <body>/<html> rules, even though Shadow DOM blocks rule
      // *matching* from crossing the boundary. This is what makes the
      // widget survive a page with aggressive global CSS.
      ":host{all:initial;}" +
      ".botai-widget-root{position:fixed;z-index:2147483000;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;}" +
      ".botai-widget-bottom-right{right:20px;bottom:20px;}" +
      ".botai-widget-bottom-left{left:20px;bottom:20px;}" +
      ".botai-bubble{width:56px;height:56px;border-radius:50%;border:none;cursor:pointer;" +
      "background:" + config.color + ";color:#fff;display:flex;align-items:center;justify-content:center;" +
      "box-shadow:0 8px 24px rgba(0,0,0,0.18);transition:transform 0.15s ease;padding:0;}" +
      ".botai-bubble:hover{transform:scale(1.05);}" +
      ".botai-bubble:focus-visible{outline:2px solid " + config.color + ";outline-offset:3px;}" +
      ".botai-panel{position:absolute;bottom:72px;right:0;width:340px;max-width:calc(100vw - 40px);" +
      "height:420px;max-height:calc(100vh - 120px);background:#fff;border-radius:16px;" +
      "box-shadow:0 12px 40px rgba(0,0,0,0.2);display:flex;flex-direction:column;overflow:hidden;}" +
      ".botai-widget-bottom-left .botai-panel{right:auto;left:0;}" +
      ".botai-panel[hidden]{display:none;}" +
      ".botai-panel-header{background:" + config.color + ";color:#fff;padding:14px 16px;" +
      "display:flex;align-items:center;justify-content:space-between;flex-shrink:0;}" +
      ".botai-panel-title{font-weight:600;font-size:15px;}" +
      ".botai-close{background:none;border:none;color:#fff;cursor:pointer;padding:2px;display:flex;opacity:0.85;}" +
      ".botai-close:hover{opacity:1;}" +
      ".botai-panel-body{flex:1;padding:16px;overflow-y:auto;}" +
      ".botai-messages{display:flex;flex-direction:column;gap:8px;}" +
      ".botai-msg{max-width:80%;padding:9px 13px;border-radius:14px;font-size:13.5px;" +
      "line-height:1.4;word-wrap:break-word;white-space:pre-wrap;}" +
      ".botai-msg-bot{align-self:flex-start;background:#f1f1f4;color:#26262e;" +
      "border-bottom-left-radius:4px;}" +
      ".botai-msg-user{align-self:flex-end;background:" + config.color + ";color:#fff;" +
      "border-bottom-right-radius:4px;}" +
      ".botai-typing-dots{display:inline-flex;gap:4px;align-items:center;padding:2px 0;}" +
      ".botai-typing-dots .botai-dot{width:6px;height:6px;border-radius:50%;background:#9a9aa4;" +
      "animation:botai-bounce 1.2s infinite ease-in-out;}" +
      ".botai-typing-dots .botai-dot:nth-child(2){animation-delay:0.15s;}" +
      ".botai-typing-dots .botai-dot:nth-child(3){animation-delay:0.3s;}" +
      "@keyframes botai-bounce{0%,60%,100%{transform:translateY(0);opacity:.4;}30%{transform:translateY(-4px);opacity:1;}}" +
      ".botai-panel-footer{flex-shrink:0;display:flex;align-items:center;gap:8px;" +
      "padding:10px 12px;border-top:1px solid #ececef;}" +
      ".botai-input{flex:1;border:1px solid #dcdce2;border-radius:20px;padding:8px 14px;" +
      "font-size:13.5px;outline:none;font-family:inherit;box-sizing:border-box;}" +
      ".botai-input:focus{border-color:" + config.color + ";}" +
      ".botai-input:disabled{background:#f7f7f9;cursor:not-allowed;}" +
      ".botai-send{flex-shrink:0;width:34px;height:34px;border-radius:50%;border:none;" +
      "background:" + config.color + ";color:#fff;display:flex;align-items:center;" +
      "justify-content:center;cursor:pointer;padding:0;}" +
      ".botai-send:hover{opacity:0.9;}" +
      ".botai-send:disabled{opacity:.5;cursor:not-allowed;}"
    );
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();