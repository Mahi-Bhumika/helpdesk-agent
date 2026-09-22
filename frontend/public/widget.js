(function () {
  "use strict";

  function fetchLiveSettingsOnce(config, timeoutMs) {
  var controller = new AbortController();
  var timeoutId = setTimeout(function () { controller.abort(); }, timeoutMs);

  return fetch(config.apiUrl + "/tenants/" + config.tenantId + "/widget-config", {
    method: "GET",
    mode: "cors",
    signal: controller.signal,
  })
    .then(function (res) {
      clearTimeout(timeoutId);
      if (!res.ok) throw new Error("HTTP " + res.status);
      return res.json();
    })
    .finally(function () {
      clearTimeout(timeoutId);
    });
}

function fetchLiveSettings(config) {
  return fetchLiveSettingsOnce(config, 8000).catch(function (err) {
    console.warn(
      "[HIKA Widget] widget-config failed, using embed snippet defaults.",
      err
    );
    throw err;
  });
}

  function mountWidget(config) {
    var host = document.createElement("div");
    var shadow = host.attachShadow({ mode: "open" });
    document.body.appendChild(host);

    var style = document.createElement("style");
    style.textContent = buildCSS(config);
    shadow.appendChild(style);

    var root = document.createElement("div");
    root.className = "HIKA-widget-root HIKA-widget-" + config.position;
    root.innerHTML =
      '<button class="HIKA-bubble" type="button" aria-label="Open chat" aria-expanded="false">' +
        bubbleIcon() +
      "</button>" +
      '<div class="HIKA-panel" hidden>' +
        '<div class="HIKA-panel-header">' +
          '<span class="HIKA-panel-title">' + config.botName + '</span>' +
          '<div class="HIKA-header-actions">' +
            '<button class="HIKA-end-btn" type="button" title="End Chat">End Chat</button>' +
            '<button class="HIKA-close" type="button" aria-label="Close chat">' + closeIcon() + "</button>" +
          '</div>' +
        "</div>" +
        '<div class="HIKA-panel-body">' +
          '<div class="HIKA-messages" aria-live="polite"></div>' +
          '<div class="HIKA-csat-view" hidden>' +
            '<div class="HIKA-csat-title">How was your experience?</div>' +
            '<div class="HIKA-stars">' +
              '<button type="button" class="HIKA-star" data-rating="1">★</button>' +
              '<button type="button" class="HIKA-star" data-rating="2">★</button>' +
              '<button type="button" class="HIKA-star" data-rating="3">★</button>' +
              '<button type="button" class="HIKA-star" data-rating="4">★</button>' +
              '<button type="button" class="HIKA-star" data-rating="5">★</button>' +
            '</div>' +
            '<button type="button" class="HIKA-csat-skip">Skip rating</button>' +
          '</div>' +
        "</div>" +
        '<div class="HIKA-panel-footer">' +
          '<input type="text" class="HIKA-input" placeholder="Type your question…" aria-label="Message" />' +
          '<button class="HIKA-send" type="button" aria-label="Send message">' + sendIcon() + "</button>" +
        "</div>" +
      "</div>";
    shadow.appendChild(root);

    var bubble = root.querySelector(".HIKA-bubble");
    var panel = root.querySelector(".HIKA-panel");
    var closeBtn = root.querySelector(".HIKA-close");
    var endBtn = root.querySelector(".HIKA-end-btn");
    var messagesEl = root.querySelector(".HIKA-messages");
    var panelBody = root.querySelector(".HIKA-panel-body");
    var inputEl = root.querySelector(".HIKA-input");
    var sendBtn = root.querySelector(".HIKA-send");
    var footerEl = root.querySelector(".HIKA-panel-footer");
    var csatView = root.querySelector(".HIKA-csat-view");
    var skipBtn = root.querySelector(".HIKA-csat-skip");
    var starBtns = root.querySelectorAll(".HIKA-star");

    var hasGreeted = false;
    var sessionId = null;
    var isSending = false;
    var selectedRating = null;

    function formatTime(date) {
      var hours = date.getHours();
      var minutes = date.getMinutes();
      var ampm = hours >= 12 ? "PM" : "AM";
      hours = hours % 12 || 12;
      var minStr = minutes < 10 ? "0" + minutes : String(minutes);
      return hours + ":" + minStr + " " + ampm;
    }

    function appendMessage(text, sender) {
      var wrap = document.createElement("div");
      wrap.className = "HIKA-msg-wrap HIKA-msg-wrap-" + sender;

      var msg = document.createElement("div");
      msg.className = "HIKA-msg HIKA-msg-" + sender;
      msg.textContent = text;
      wrap.appendChild(msg);

      var time = document.createElement("span");
      time.className = "HIKA-timestamp";
      time.textContent = formatTime(new Date());
      wrap.appendChild(time);

      messagesEl.appendChild(wrap);
      panelBody.scrollTo({ top: panelBody.scrollHeight, behavior: "smooth" });
      return msg;
    }

    function appendTyping() {
      var wrap = document.createElement("div");
      wrap.className = "HIKA-msg-wrap HIKA-msg-wrap-bot";
      wrap.innerHTML =
        '<div class="HIKA-msg HIKA-msg-bot HIKA-typing">' +
          '<span class="HIKA-typing-dots">' +
            '<span class="HIKA-dot"></span><span class="HIKA-dot"></span><span class="HIKA-dot"></span>' +
          "</span>" +
        "</div>";
      messagesEl.appendChild(wrap);
      panelBody.scrollTo({ top: panelBody.scrollHeight, behavior: "smooth" });
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
      if (csatView.hidden) {
        inputEl.focus();
      }
    }

    function closePanel() {
      panel.hidden = true;
      bubble.setAttribute("aria-expanded", "false");
    }

    function showCsatScreen() {
      messagesEl.hidden = true;
      footerEl.style.display = "none";
      endBtn.style.display = "none";
      csatView.hidden = false;
    }

    function resetWidgetState() {
      sessionId = null;
      hasGreeted = false;
      messagesEl.innerHTML = "";
      messagesEl.hidden = false;
      csatView.hidden = true;
      footerEl.style.display = "flex";
      endBtn.style.display = "block";
      selectedRating = null;
      starBtns.forEach(function (btn) { btn.classList.remove("selected"); });
    }

    function submitChatEnd(rating) {
      if (sessionId) {
        fetch(config.apiUrl + "/chat/end", {
          method: "POST",
          mode: "cors",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: sessionId,
            tenant_id: config.tenantId,
            csat: rating,
          }),
        }).catch(function (err) {
          console.error("[HIKA Widget] Failed to log chat end:", err);
        });
      }

      resetWidgetState();
      closePanel();
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
        mode: "cors",
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
          console.error(
            "[HIKA Widget] /chat request failed. Target was: " + config.apiUrl + "/chat",
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

    // Event Listeners
    bubble.addEventListener("click", function () {
      panel.hidden ? openPanel() : closePanel();
    });
    closeBtn.addEventListener("click", closePanel);
    endBtn.addEventListener("click", showCsatScreen);
    skipBtn.addEventListener("click", function () { submitChatEnd(null); });

    starBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var rating = parseInt(btn.getAttribute("data-rating"), 10);
        submitChatEnd(rating);
      });

      btn.addEventListener("mouseenter", function () {
        var hoverRating = parseInt(btn.getAttribute("data-rating"), 10);
        starBtns.forEach(function (s) {
          var r = parseInt(s.getAttribute("data-rating"), 10);
          if (r <= hoverRating) {
            s.classList.add("hover");
          } else {
            s.classList.remove("hover");
          }
        });
      });

      btn.addEventListener("mouseleave", function () {
        starBtns.forEach(function (s) { s.classList.remove("hover"); });
      });
    });

    sendBtn.addEventListener("click", handleSend);
    inputEl.addEventListener("keydown", function (e) {
      if (e.key === "Enter") handleSend();
    });

    window.__botaiWidget = { config: config, open: openPanel, close: closePanel };
  }

  function init() {
    var scriptTag = document.currentScript || document.querySelector("script[data-tenant-id]");

    if (!scriptTag) {
      console.error("[HIKA Widget] Could not locate its own <script> tag.");
      return;
    }

    var config = {
      tenantId: scriptTag.getAttribute("data-tenant-id"),
      botName: scriptTag.getAttribute("data-name") || "Chat",
      apiUrl: scriptTag.getAttribute("data-api-url") || "",
      color: scriptTag.getAttribute("data-color") || "#5B5BF0",
      position: scriptTag.getAttribute("data-position") || "bottom-right",
      greeting: scriptTag.getAttribute("data-greeting") || "Hi! How can I help you today?",
    };

    if (!config.tenantId) {
      console.error("[HIKA Widget] Missing required data-tenant-id attribute — widget not mounted.");
      return;
    }
    if (!config.apiUrl) {
      console.error("[HIKA Widget] Missing data-api-url attribute — widget will mount but /chat calls will fail.");
      mountWidget(config);
      return;
    }

    fetchLiveSettings(config)
  .then(function (remoteSettings) {
    if (remoteSettings) {
      config.botName = remoteSettings.bot_name || config.botName;
      config.color = remoteSettings.theme_color || config.color;
      config.greeting = remoteSettings.greeting_message || config.greeting;
      config.fallbackMessage = remoteSettings.fallback_message || null;
    }
  })
      .catch(function () {
        // Fallback already logged in fetchLiveSettings; continue mounting with local script config
      })
      .finally(function () {
        mountWidget(config);
      });
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
      "@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');" +
      ":host{all:initial;}" +
      ".HIKA-widget-root{position:fixed;z-index:2147483000;" +
      "font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;}" +
      ".HIKA-widget-bottom-right{right:20px;bottom:20px;}" +
      ".HIKA-widget-bottom-left{left:20px;bottom:20px;}" +
      ".HIKA-bubble{width:56px;height:56px;border-radius:50%;border:none;cursor:pointer;" +
      "background:" + config.color + ";color:#fff;display:flex;align-items:center;justify-content:center;" +
      "box-shadow:0 8px 24px rgba(0,0,0,0.18);transition:transform 0.15s ease;padding:0;}" +
      ".HIKA-bubble:hover{transform:scale(1.05);}" +
      ".HIKA-bubble:focus-visible{outline:2px solid " + config.color + ";outline-offset:3px;}" +
      ".HIKA-panel{position:absolute;bottom:72px;right:0;width:340px;max-width:calc(100vw - 40px);" +
      "height:420px;max-height:calc(100vh - 120px);background:#fff;border-radius:18px;" +
      "box-shadow:0 12px 40px rgba(0,0,0,0.2);display:flex;flex-direction:column;overflow:hidden;}" +
      ".HIKA-widget-bottom-left .HIKA-panel{right:auto;left:0;}" +
      ".HIKA-panel[hidden]{display:none;}" +
      ".HIKA-panel-header{background:" + config.color + ";color:#fff;padding:14px 16px;" +
      "display:flex;align-items:center;justify-content:space-between;flex-shrink:0;}" +
      ".HIKA-panel-title{font-weight:600;font-size:15px;letter-spacing:-0.01em;}" +
      ".HIKA-header-actions{display:flex;align-items:center;gap:8px;}" +
      ".HIKA-end-btn{background:rgba(255,255,255,0.2);border:none;color:#fff;font-size:11.5px;" +
      "font-weight:500;padding:4px 8px;border-radius:12px;cursor:pointer;transition:background 0.2s;}" +
      ".HIKA-end-btn:hover{background:rgba(255,255,255,0.35);}" +
      ".HIKA-close{background:none;border:none;color:#fff;cursor:pointer;padding:2px;display:flex;opacity:0.85;}" +
      ".HIKA-close:hover{opacity:1;}" +
      ".HIKA-panel-body{flex:1;padding:16px;overflow-y:auto;background:#fafafb;display:flex;flex-direction:column;}" +
      ".HIKA-messages{display:flex;flex-direction:column;gap:12px;flex:1;}" +
      ".HIKA-msg-wrap{display:flex;flex-direction:column;max-width:82%;}" +
      ".HIKA-msg-wrap-bot{align-self:flex-start;align-items:flex-start;}" +
      ".HIKA-msg-wrap-user{align-self:flex-end;align-items:flex-end;}" +
      ".HIKA-msg{padding:10px 14px;border-radius:16px;font-size:13.5px;" +
      "line-height:1.45;word-wrap:break-word;white-space:pre-wrap;letter-spacing:-0.003em;}" +
      ".HIKA-msg-bot{background:linear-gradient(180deg,#ffffff,#f5f5f8);color:#242430;" +
      "border:1px solid #ececf1;border-bottom-left-radius:5px;" +
      "box-shadow:0 1px 2px rgba(0,0,0,0.04);}" +
      ".HIKA-msg-user{background:" + config.color + ";color:#fff;" +
      "border-bottom-right-radius:5px;box-shadow:0 2px 8px " + config.color + "40;}" +
      ".HIKA-timestamp{font-size:10.5px;color:#a5a5b0;margin-top:3px;padding:0 4px;}" +
      ".HIKA-typing-dots{display:inline-flex;gap:4px;align-items:center;padding:2px 0;}" +
      ".HIKA-typing-dots .HIKA-dot{width:6px;height:6px;border-radius:50%;background:#b0b0ba;" +
      "animation:HIKA-bounce 1.2s infinite ease-in-out;}" +
      ".HIKA-typing-dots .HIKA-dot:nth-child(2){animation-delay:0.15s;}" +
      ".HIKA-typing-dots .HIKA-dot:nth-child(3){animation-delay:0.3s;}" +
      "@keyframes HIKA-bounce{0%,60%,100%{transform:translateY(0);opacity:.4;}30%{transform:translateY(-4px);opacity:1;}}" +
      ".HIKA-csat-view{display:flex;flex-direction:column;align-items:center;justify-content:center;" +
      "height:100%;text-align:center;padding:20px 10px;box-sizing:border-box;margin:auto;}" +
      ".HIKA-csat-view[hidden]{display:none;}" +
      ".HIKA-csat-title{font-size:16px;font-weight:600;color:#1e1e24;margin-bottom:18px;}" +
      ".HIKA-stars{display:flex;gap:8px;margin-bottom:20px;}" +
      ".HIKA-star{background:none;border:none;font-size:28px;color:#d0d0d8;cursor:pointer;" +
      "padding:2px;transition:color 0.15s, transform 0.15s;line-height:1;}" +
      ".HIKA-star:hover,.HIKA-star.hover{color:#ffb400;transform:scale(1.2);}" +
      ".HIKA-csat-skip{background:none;border:none;color:#71717a;font-size:12.5px;cursor:pointer;" +
      "text-decoration:underline;padding:4px 8px;}" +
      ".HIKA-csat-skip:hover{color:#1e1e24;}" +
      ".HIKA-panel-footer{flex-shrink:0;display:flex;align-items:center;gap:8px;" +
      "padding:10px 12px;border-top:1px solid #ececef;background:#fff;}" +
      ".HIKA-input{flex:1;border:1px solid #dcdce2;border-radius:20px;padding:9px 14px;" +
      "font-size:13.5px;outline:none;font-family:inherit;box-sizing:border-box;}" +
      ".HIKA-input:focus{border-color:" + config.color + ";}" +
      ".HIKA-input:disabled{background:#f7f7f9;cursor:not-allowed;}" +
      ".HIKA-send{flex-shrink:0;width:34px;height:34px;border-radius:50%;border:none;" +
      "background:" + config.color + ";color:#fff;display:flex;align-items:center;" +
      "justify-content:center;cursor:pointer;padding:0;box-shadow:0 2px 6px " + config.color + "40;}" +
      ".HIKA-send:hover{opacity:0.9;}" +
      ".HIKA-send:disabled{opacity:.5;cursor:not-allowed;box-shadow:none;}"
    );
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();