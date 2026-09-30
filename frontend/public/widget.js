(function () {
  "use strict";

  /* ------------------------------------------------------------------ *
   *  Constants
   * ------------------------------------------------------------------ */
  var CURRENT_SCRIPT = document.currentScript;
  var DEFAULT_COLOR = "#5B5BF0";
  var DEFAULT_ERROR_MESSAGE = "Sorry, something went wrong reaching the server. Please try again.";
  var MAX_RENDER_CHARS = 30000; // hard cap on how much of a bot reply we ever parse/render
  var MAX_COLS = 20;
  var MAX_ROWS = 200;
  var MAX_INLINE_DEPTH = 4;
  var MAX_BLOCK_DEPTH = 3;

  /* ------------------------------------------------------------------ *
   *  Config sanitisers (values come from script attributes AND from the
   *  remote widget-config, so they are treated as untrusted)
   * ------------------------------------------------------------------ */
  function normalizeColor(input, fallback) {
    if (typeof input !== "string") return fallback;
    var s = input.trim();
    var m = /^#([0-9a-f]{3})$/i.exec(s);
    if (m) {
      return ("#" + m[1].split("").map(function (c) { return c + c; }).join("")).toLowerCase();
    }
    if (/^#[0-9a-f]{6}$/i.test(s)) return s.toLowerCase();
    m = /^rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)$/i.exec(s);
    if (m) {
      var parts = [Number(m[1]), Number(m[2]), Number(m[3])];
      if (parts.every(function (v) { return v <= 255; })) {
        return "#" + parts.map(function (v) { return (v < 16 ? "0" : "") + v.toString(16); }).join("");
      }
    }
    return fallback;
  }

  function relativeLuminance(hex) {
    var channels = [1, 3, 5].map(function (i) {
      var v = parseInt(hex.substr(i, 2), 16) / 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
  }

  function sanitizePosition(pos) {
    return pos === "bottom-left" ? "bottom-left" : "bottom-right";
  }

  function cleanText(value, maxLen, fallback) {
    if (typeof value !== "string") return fallback;
    var s = value.trim();
    if (!s) return fallback;
    return s.length > maxLen ? s.slice(0, maxLen) : s;
  }

  function cleanApiUrl(url) {
    if (typeof url !== "string") return "";
    return url.trim().replace(/\/+$/, "");
  }

  /* ------------------------------------------------------------------ *
   *  Theme persistence (manual toggle only, no OS detection)
   * ------------------------------------------------------------------ */
  function loadTheme(tenantId) {
    try {
      return window.localStorage.getItem("HIKA-theme:" + tenantId) === "dark" ? "dark" : "light";
    } catch (e) {
      return "light";
    }
  }

  function saveTheme(tenantId, theme) {
    try {
      window.localStorage.setItem("HIKA-theme:" + tenantId, theme);
    } catch (e) {
      /* storage blocked: toggle still works for this page view */
    }
  }

  /* ------------------------------------------------------------------ *
   *  Remote settings
   * ------------------------------------------------------------------ */
  function fetchLiveSettingsOnce(config, timeoutMs) {
    var controller = new AbortController();
    var timeoutId = setTimeout(function () { controller.abort(); }, timeoutMs);

    return fetch(config.apiUrl + "/tenants/" + encodeURIComponent(config.tenantId) + "/widget-config", {
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
      console.warn("[HIKA Widget] widget-config failed, using embed snippet defaults.", err);
      throw err;
    });
  }

  /* ================================================================== *
   *  SAFE MARKDOWN RENDERER
   *
   *  Security model:
   *   - The output is built ONLY with createElement / createTextNode /
   *     textContent. innerHTML is never used with bot text, so raw HTML in
   *     a reply is displayed as plain text and can never execute.
   *   - Only a fixed allow-list of tags is ever created.
   *   - The only attribute derived from bot text is <a href>, and it must
   *     parse as an absolute http:, https: or mailto: URL with no
   *     credentials, whitespace or control characters.
   *   - Markdown images are NEVER rendered as <img> (no tracking pixels /
   *     remote loads); they degrade to a normal link.
   *   - Input length, nesting depth, table size and scan windows are capped
   *     and no regex with nested quantifiers touches untrusted text, so
   *     hostile input cannot hang the page.
   * ================================================================== */

  var RE_FENCE = /^\s{0,3}(```|~~~)/;
  var RE_QUOTE = /^\s{0,3}>\s?/;
  var RE_LIST = /^(\s*)([-*+\u2022\u2013]|\d{1,9}[.)])\s+(.*)$/;

  function isSpace(c) {
    return !c || /\s/.test(c);
  }

  function isWordChar(c) {
    return !!c && /[A-Za-z0-9]/.test(c);
  }

  /* ---- URL safety ---- */
  function safeHref(raw) {
    if (typeof raw !== "string") return null;
    var s = raw.trim();
    if (s.charAt(0) === "<" && s.charAt(s.length - 1) === ">") s = s.slice(1, -1).trim();
    if (!s || s.length > 2048) return null;
    if (/[\u0000-\u0020\u007f-\u009f\u202a-\u202e\u2066-\u2069"<>`\\]/.test(s)) return null;
    var u;
    try {
      u = new URL(s);
    } catch (e) {
      return null;
    }
    if (u.protocol !== "http:" && u.protocol !== "https:" && u.protocol !== "mailto:") return null;
    if (u.username || u.password) return null; // blocks https://trusted.com@evil.com tricks
    return u.href;
  }

  function looksLikeUrl(label) {
    return label.length < 400 && /^(https?:\/\/)?[a-z0-9-]+(\.[a-z0-9-]+)+(:\d+)?(\/\S*)?$/i.test(label);
  }

  function sameHost(label, href) {
    try {
      var a = new URL(/^https?:\/\//i.test(label) ? label : "http://" + label).hostname;
      var b = new URL(href).hostname;
      return a.replace(/^www\./i, "").toLowerCase() === b.replace(/^www\./i, "").toLowerCase();
    } catch (e) {
      return false;
    }
  }

  function appendLink(parent, labelText, rawUrl, depth, bareDisplay) {
    var href = safeHref(rawUrl);
    if (!href) {
      // unsafe / unparseable target: show the label as plain text, never a link
      if (labelText) parseInline(labelText, parent, depth + 1, true);
      return;
    }
    var a = document.createElement("a");
    var label = (labelText || "").trim();

    // If the visible text looks like a URL that points somewhere else, show the real target instead.
    if (label && looksLikeUrl(label) && !sameHost(label, href)) label = "";

    a.setAttribute("href", href);
    a.setAttribute("target", "_blank");
    a.setAttribute("rel", "noopener noreferrer nofollow");
    a.setAttribute("title", href);

    if (label) {
      parseInline(label, a, depth + 1, true);
    } else if (bareDisplay && href.indexOf("xn--") === -1) {
      a.textContent = bareDisplay; // exactly what the author typed
    } else {
      a.textContent = href.replace(/^mailto:/i, ""); // punycode/IDN shown in real form
    }
    parent.appendChild(a);
  }

  /* ---- plain text with e-mail auto-linking (manual scan, no backtracking) ---- */
  function appendPlain(parent, s) {
    if (!s) return;
    if (s.indexOf("@") === -1) {
      parent.appendChild(document.createTextNode(s));
      return;
    }
    var cursor = 0;
    var at = s.indexOf("@");
    while (at !== -1) {
      var ls = at;
      while (ls > cursor && at - ls < 64 && /[A-Za-z0-9._%+\-]/.test(s.charAt(ls - 1))) ls--;
      var re = at + 1;
      while (re < s.length && re - at < 255 && /[A-Za-z0-9.\-]/.test(s.charAt(re))) re++;
      var domain = s.slice(at + 1, re).replace(/[.\-]+$/, "");
      var local = s.slice(ls, at);
      var tld = domain.slice(domain.lastIndexOf(".") + 1);
      if (local && domain.indexOf(".") > 0 && /^[A-Za-z]{2,}$/.test(tld) && domain.charAt(0) !== "." && domain.charAt(0) !== "-") {
        var email = local + "@" + domain;
        if (ls > cursor) parent.appendChild(document.createTextNode(s.slice(cursor, ls)));
        appendLink(parent, "", "mailto:" + email, 0, email);
        cursor = at + 1 + domain.length;
        at = s.indexOf("@", cursor);
      } else {
        at = s.indexOf("@", at + 1);
      }
    }
    if (cursor < s.length) parent.appendChild(document.createTextNode(s.slice(cursor)));
  }

  /* ---- link syntax: [label](url "optional title") with bounded scan windows ---- */
  function parseLinkAt(text, i) {
    var n = text.length;
    var depth = 0;
    var j = i;
    var limit = Math.min(n, i + 400);
    for (; j < limit; j++) {
      var c = text.charAt(j);
      if (c === "\\") { j++; continue; }
      if (c === "[") depth++;
      else if (c === "]") { depth--; if (depth === 0) break; }
    }
    if (j >= limit || text.charAt(j) !== "]" || text.charAt(j + 1) !== "(") return null;
    var label = text.slice(i + 1, j);
    var k = j + 2;
    var paren = 1;
    var ulimit = Math.min(n, k + 2200);
    for (; k < ulimit; k++) {
      var d = text.charAt(k);
      if (d === "(") paren++;
      else if (d === ")") { paren--; if (paren === 0) break; }
    }
    if (k >= ulimit || text.charAt(k) !== ")") return null;
    var inner = text.slice(j + 2, k).trim();
    return { label: label, url: inner.split(/\s+/)[0] || "", end: k + 1 };
  }

  function trimUrlEnd(url) {
    var changed = true;
    while (changed && url.length) {
      changed = false;
      var last = url.charAt(url.length - 1);
      if (".,;:!?*_'\"]}".indexOf(last) !== -1) {
        url = url.slice(0, -1);
        changed = true;
      } else if (last === ")") {
        var open = url.split("(").length - 1;
        var close = url.split(")").length - 1;
        if (close > open) { url = url.slice(0, -1); changed = true; }
      }
    }
    return url;
  }

  function findClose(text, from, marker) {
    var j = text.indexOf(marker, from);
    var tries = 0;
    var ch = marker.charAt(0);
    while (j !== -1 && tries < 40) {
      tries++;
      var before = text.charAt(j - 1);
      var after = text.charAt(j + marker.length);
      var ok = j > from && !isSpace(before);
      if (marker.length === 1) {
        ok = ok && before !== ch && after !== ch && !(ch === "_" && isWordChar(after));
      } else if (ch === "_") {
        ok = ok && !isWordChar(after);
      }
      if (ok) return j;
      j = text.indexOf(marker, j + 1);
    }
    return -1;
  }

  /* ---- inline formatting ---- */
  function parseInline(text, parent, depth, inLink) {
    var buf = "";
    var i = 0;
    var n = text.length;
    var allowNest = depth < MAX_INLINE_DEPTH;

    function flush() {
      if (buf) { appendPlain(parent, buf); buf = ""; }
    }

    while (i < n) {
      var ch = text.charAt(i);

      // backslash escapes
      if (ch === "\\" && i + 1 < n && "\\`*_{}[]()#+-.!|~>".indexOf(text.charAt(i + 1)) !== -1) {
        buf += text.charAt(i + 1);
        i += 2;
        continue;
      }

      // inline code
      if (ch === "`") {
        var run = 1;
        while (text.charAt(i + run) === "`") run++;
        var fence = new Array(run + 1).join("`");
        var end = text.indexOf(fence, i + run);
        if (end > i + run) {
          flush();
          var code = document.createElement("code");
          code.textContent = text.slice(i + run, end).trim();
          parent.appendChild(code);
          i = end + run;
          continue;
        }
        buf += fence;
        i += run;
        continue;
      }

      // images -> plain link (never <img>)
      if (ch === "!" && text.charAt(i + 1) === "[" && !inLink) {
        var img = parseLinkAt(text, i + 1);
        if (img) {
          flush();
          appendLink(parent, img.label || img.url, img.url, depth);
          i = img.end;
          continue;
        }
      }

      // links
      if (ch === "[" && !inLink) {
        var lk = parseLinkAt(text, i);
        if (lk) {
          flush();
          appendLink(parent, lk.label, lk.url, depth);
          i = lk.end;
          continue;
        }
      }

      // bare URLs
      if (ch === "h" && !inLink && (text.substr(i, 7) === "http://" || text.substr(i, 8) === "https://") && !isWordChar(text.charAt(i - 1))) {
        var m = /^https?:\/\/[^\s<>"'`]+/.exec(text.substr(i, 2100));
        if (m) {
          var urlText = trimUrlEnd(m[0]);
          if (safeHref(urlText)) {
            flush();
            appendLink(parent, "", urlText, depth, urlText);
            i += urlText.length;
            continue;
          }
        }
      }

      // bold / italic / strike
      if ((ch === "*" || ch === "_") && allowNest && (ch === "*" || !isWordChar(text.charAt(i - 1)))) {
        if (text.substr(i, 3) === ch + ch + ch && !isSpace(text.charAt(i + 3))) {
          var c3 = findClose(text, i + 3, ch + ch + ch);
          if (c3 !== -1) {
            flush();
            var s3 = document.createElement("strong");
            var e3 = document.createElement("em");
            s3.appendChild(e3);
            parseInline(text.slice(i + 3, c3), e3, depth + 1, inLink);
            parent.appendChild(s3);
            i = c3 + 3;
            continue;
          }
        }
        if (text.charAt(i + 1) === ch && !isSpace(text.charAt(i + 2))) {
          var c2 = findClose(text, i + 2, ch + ch);
          if (c2 !== -1) {
            flush();
            var st = document.createElement("strong");
            parseInline(text.slice(i + 2, c2), st, depth + 1, inLink);
            parent.appendChild(st);
            i = c2 + 2;
            continue;
          }
        } else if (text.charAt(i + 1) !== ch && !isSpace(text.charAt(i + 1))) {
          var c1 = findClose(text, i + 1, ch);
          if (c1 !== -1) {
            flush();
            var em = document.createElement("em");
            parseInline(text.slice(i + 1, c1), em, depth + 1, inLink);
            parent.appendChild(em);
            i = c1 + 1;
            continue;
          }
        }
      }
      if (ch === "~" && text.charAt(i + 1) === "~" && allowNest && !isSpace(text.charAt(i + 2))) {
        var cs = text.indexOf("~~", i + 2);
        if (cs > i + 2) {
          flush();
          var del = document.createElement("del");
          parseInline(text.slice(i + 2, cs), del, depth + 1, inLink);
          parent.appendChild(del);
          i = cs + 2;
          continue;
        }
      }

      buf += ch;
      i++;
    }
    flush();
  }

  /* ---- block helpers ---- */
  function isHr(line) {
    if (!/^[-*_ ]+$/.test(line)) return false;
    var t = line.replace(/ /g, "");
    return t.length >= 3 && /^(-+|\*+|_+)$/.test(t);
  }

  function headingMatch(line) {
    var m = /^\s{0,3}(#{1,6})\s+(\S.*)$/.exec(line);
    if (!m) return null;
    var t = m[2].trim();
    var sp = t.lastIndexOf(" ");
    if (sp > 0 && /^#+$/.test(t.slice(sp + 1))) t = t.slice(0, sp).trim();
    return { level: m[1].length, text: t };
  }

  function splitRow(line) {
    var s = line.trim();
    if (s.charAt(0) === "|") s = s.slice(1);
    if (s.length && s.charAt(s.length - 1) === "|" && s.charAt(s.length - 2) !== "\\") s = s.slice(0, -1);
    var cells = [];
    var cur = "";
    for (var i = 0; i < s.length; i++) {
      var c = s.charAt(i);
      if (c === "\\" && s.charAt(i + 1) === "|") { cur += "|"; i++; continue; }
      if (c === "|") { cells.push(cur.trim()); cur = ""; if (cells.length >= MAX_COLS) return cells; continue; }
      cur += c;
    }
    cells.push(cur.trim());
    return cells.slice(0, MAX_COLS);
  }

  function isSepRow(line, cols) {
    if (line.indexOf("-") === -1 || line.indexOf("|") === -1) return false;
    var cells = splitRow(line);
    if (cells.length !== cols) return false;
    return cells.every(function (c) { return /^:?-+:?$/.test(c); });
  }

  function isTableStart(line, next) {
    if (next === undefined || line.indexOf("|") === -1) return false;
    var head = splitRow(line);
    return head.length >= 2 && isSepRow(next, head.length);
  }

  function isBlockStart(line, next) {
    return RE_FENCE.test(line) || !!headingMatch(line) || isHr(line) || RE_QUOTE.test(line) || RE_LIST.test(line) || isTableStart(line, next);
  }

  function appendInlineLines(el, lines) {
    for (var i = 0; i < lines.length; i++) {
      if (i > 0) el.appendChild(document.createElement("br"));
      parseInline(lines[i].trim(), el, 0, false);
    }
  }

  function parseList(lines, start, container) {
    var stack = [];
    var i = start;
    while (i < lines.length) {
      var line = lines[i];
      if (!line.trim()) {
        // a blank line between items keeps the same list going
        var j = i + 1;
        while (j < lines.length && !lines[j].trim()) j++;
        if (j < lines.length && RE_LIST.test(lines[j]) && !isHr(lines[j]) && stack.length) { i = j; continue; }
        break;
      }
      var m = RE_LIST.exec(line);
      if (m && !isHr(line)) {
        var indent = m[1].length;
        var ordered = /\d/.test(m[2].charAt(0));
        while (stack.length && indent < stack[stack.length - 1].indent) stack.pop();
        var top = stack[stack.length - 1];

        if (top && indent === top.indent && ordered !== top.ordered && stack.length === 1) break; // new top-level list type

        if (!top || (indent > top.indent && stack.length < 6)) {
          var listEl = document.createElement(ordered ? "ol" : "ul");
          if (ordered) {
            var num = parseInt(m[2], 10);
            if (num > 1 && num < 1000000) listEl.setAttribute("start", String(num));
          }
          (top && top.lastLi ? top.lastLi : container).appendChild(listEl);
          top = { indent: indent, ordered: ordered, el: listEl, lastLi: null };
          stack.push(top);
        }
        var li = document.createElement("li");
        parseInline(m[3].trim(), li, 0, false);
        top.el.appendChild(li);
        top.lastLi = li;
        i++;
        continue;
      }
      // indented continuation line belongs to the previous item
      if (stack.length && /^\s{2,}\S/.test(line) && !RE_FENCE.test(line) && !headingMatch(line)) {
        var last = stack[stack.length - 1].lastLi;
        if (last) {
          last.appendChild(document.createElement("br"));
          parseInline(line.trim(), last, 0, false);
          i++;
          continue;
        }
      }
      break;
    }
    return i;
  }

  function parseTable(lines, start, container) {
    var head = splitRow(lines[start]);
    var cols = head.length;
    var aligns = splitRow(lines[start + 1]).map(function (c) {
      var l = c.charAt(0) === ":";
      var r = c.charAt(c.length - 1) === ":";
      return l && r ? "center" : r ? "right" : l ? "left" : "";
    });

    var wrap = document.createElement("div");
    wrap.className = "HIKA-table-wrap";
    var table = document.createElement("table");
    var thead = document.createElement("thead");
    var trh = document.createElement("tr");

    function cell(tag, text, idx) {
      var td = document.createElement(tag);
      if (aligns[idx]) td.className = "HIKA-al-" + aligns[idx];
      parseInline(text, td, 0, false);
      return td;
    }

    head.forEach(function (h, idx) { trh.appendChild(cell("th", h, idx)); });
    thead.appendChild(trh);
    table.appendChild(thead);

    var tbody = document.createElement("tbody");
    var i = start + 2;
    var rows = 0;
    while (i < lines.length && lines[i].trim() && lines[i].indexOf("|") !== -1 && rows < MAX_ROWS) {
      var cells = splitRow(lines[i]);
      var tr = document.createElement("tr");
      for (var c = 0; c < cols; c++) tr.appendChild(cell("td", cells[c] || "", c));
      tbody.appendChild(tr);
      i++;
      rows++;
    }
    table.appendChild(tbody);
    wrap.appendChild(table);
    container.appendChild(wrap);
    return i;
  }

  function renderBlocks(lines, container, depth) {
    var i = 0;
    while (i < lines.length) {
      var line = lines[i];
      if (!line.trim()) { i++; continue; }

      // fenced code
      var fm = RE_FENCE.exec(line);
      if (fm) {
        var marker = fm[1].charAt(0);
        var body = [];
        var j = i + 1;
        while (j < lines.length) {
          var t = lines[j].trim();
          if (t.length >= 3 && t.charAt(0) === marker && new RegExp("^\\" + marker + "{3,}$").test(t)) break;
          body.push(lines[j]);
          j++;
        }
        var pre = document.createElement("pre");
        var codeEl = document.createElement("code");
        codeEl.textContent = body.join("\n");
        pre.appendChild(codeEl);
        container.appendChild(pre);
        i = j + 1;
        continue;
      }

      // heading
      var hm = headingMatch(line);
      if (hm) {
        var h = document.createElement("h" + Math.min(Math.max(hm.level + 2, 3), 5));
        h.className = "HIKA-h";
        parseInline(hm.text, h, 0, false);
        container.appendChild(h);
        i++;
        continue;
      }

      // horizontal rule
      if (isHr(line)) {
        container.appendChild(document.createElement("hr"));
        i++;
        continue;
      }

      // table
      if (isTableStart(line, lines[i + 1])) {
        i = parseTable(lines, i, container);
        continue;
      }

      // blockquote
      if (RE_QUOTE.test(line) && depth < MAX_BLOCK_DEPTH) {
        var q = [];
        while (i < lines.length && RE_QUOTE.test(lines[i])) {
          q.push(lines[i].replace(RE_QUOTE, ""));
          i++;
        }
        var bq = document.createElement("blockquote");
        renderBlocks(q, bq, depth + 1);
        container.appendChild(bq);
        continue;
      }

      // list
      if (RE_LIST.test(line)) {
        var next = parseList(lines, i, container);
        if (next > i) { i = next; continue; }
      }

      // paragraph (single newlines become line breaks, which suits chat)
      var para = [line];
      i++;
      while (i < lines.length && lines[i].trim() && !isBlockStart(lines[i], lines[i + 1])) {
        para.push(lines[i]);
        i++;
      }
      var p = document.createElement("p");
      appendInlineLines(p, para);
      container.appendChild(p);
    }
  }

  function renderMarkdown(src) {
    var root = document.createElement("div");
    root.className = "HIKA-md";
    var text = String(src == null ? "" : src).replace(/\r\n?/g, "\n");
    if (text.length > MAX_RENDER_CHARS) text = text.slice(0, MAX_RENDER_CHARS) + "\u2026";
    // strip control chars (keep \n, \t) and bidi-override characters used for spoofing
    text = text.replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f\u202a-\u202e\u2066-\u2069]/g, "");
    text = text.replace(/\t/g, "    ");
    renderBlocks(text.split("\n"), root, 0);
    return root;
  }

  /* ================================================================== *
   *  WIDGET
   * ================================================================== */
  function mountWidget(config) {
    var host = document.createElement("div");
    var shadow = host.attachShadow({ mode: "open" });
    document.body.appendChild(host);

    var style = document.createElement("style");
    style.textContent = buildCSS(config);
    shadow.appendChild(style);

    var root = document.createElement("div");
    root.className = "HIKA-widget-root HIKA-widget-" + config.position;

    // Static markup only. Every dynamic value is inserted afterwards with textContent / setAttribute.
    root.innerHTML =
      '<button class="HIKA-bubble" type="button" aria-label="Open chat" aria-expanded="false">' +
        bubbleIcon() +
      "</button>" +
      '<div class="HIKA-panel" role="dialog" hidden>' +
        '<div class="HIKA-panel-header">' +
          '<div class="HIKA-header-main">' +
            '<div class="HIKA-avatar" aria-hidden="true"><span class="HIKA-avatar-letter"></span><span class="HIKA-status"></span></div>' +
            '<span class="HIKA-panel-title"></span>' +
          "</div>" +
          '<div class="HIKA-header-actions">' +
            '<button class="HIKA-end-btn" type="button" title="End Chat">End Chat</button>' +
            '<button class="HIKA-theme" type="button" aria-label="Switch to dark mode" title="Switch to dark mode">' + moonIcon() + sunIcon() + "</button>" +
            '<button class="HIKA-close" type="button" aria-label="Close chat">' + closeIcon() + "</button>" +
          "</div>" +
        "</div>" +
        '<div class="HIKA-panel-body">' +
          '<div class="HIKA-messages" role="log" aria-live="polite"></div>' +
          '<div class="HIKA-csat-view" hidden>' +
            '<div class="HIKA-csat-title">How was your experience?</div>' +
            '<div class="HIKA-stars">' +
              '<button type="button" class="HIKA-star" data-rating="1" aria-label="1 star">\u2605</button>' +
              '<button type="button" class="HIKA-star" data-rating="2" aria-label="2 stars">\u2605</button>' +
              '<button type="button" class="HIKA-star" data-rating="3" aria-label="3 stars">\u2605</button>' +
              '<button type="button" class="HIKA-star" data-rating="4" aria-label="4 stars">\u2605</button>' +
              '<button type="button" class="HIKA-star" data-rating="5" aria-label="5 stars">\u2605</button>' +
            "</div>" +
            '<button type="button" class="HIKA-csat-skip">Skip rating</button>' +
          "</div>" +
        "</div>" +
        '<div class="HIKA-panel-footer">' +
          '<input type="text" class="HIKA-input" placeholder="Type your question\u2026" aria-label="Message" maxlength="2000" autocomplete="off" />' +
          '<button class="HIKA-send" type="button" aria-label="Send message" disabled>' + sendIcon() + "</button>" +
        "</div>" +
      "</div>";
    shadow.appendChild(root);

    var bubble = root.querySelector(".HIKA-bubble");
    var panel = root.querySelector(".HIKA-panel");
    var closeBtn = root.querySelector(".HIKA-close");
    var endBtn = root.querySelector(".HIKA-end-btn");
    var themeBtn = root.querySelector(".HIKA-theme");
    var messagesEl = root.querySelector(".HIKA-messages");
    var panelBody = root.querySelector(".HIKA-panel-body");
    var inputEl = root.querySelector(".HIKA-input");
    var sendBtn = root.querySelector(".HIKA-send");
    var footerEl = root.querySelector(".HIKA-panel-footer");
    var csatView = root.querySelector(".HIKA-csat-view");
    var skipBtn = root.querySelector(".HIKA-csat-skip");
    var starBtns = root.querySelectorAll(".HIKA-star");

    // dynamic text: textContent only
    root.querySelector(".HIKA-panel-title").textContent = config.botName;
    root.querySelector(".HIKA-avatar-letter").textContent = (Array.from(config.botName)[0] || "?").toUpperCase();
    panel.setAttribute("aria-label", config.botName);

    var hasGreeted = false;
    var sessionId = null;
    var isSending = false;
    var closing = false;
    var closeTimer = null;
    var theme = loadTheme(config.tenantId);

    /* ---------- theme ---------- */
    function applyTheme() {
      var dark = theme === "dark";
      root.classList.toggle("HIKA-dark", dark);
      var label = dark ? "Switch to light mode" : "Switch to dark mode";
      themeBtn.setAttribute("aria-label", label);
      themeBtn.setAttribute("title", label);
    }

    function toggleTheme() {
      theme = theme === "dark" ? "light" : "dark";
      saveTheme(config.tenantId, theme);
      applyTheme();
    }

    applyTheme();

    /* ---------- helpers ---------- */
    function formatTime(date) {
      var hours = date.getHours();
      var minutes = date.getMinutes();
      var ampm = hours >= 12 ? "PM" : "AM";
      hours = hours % 12 || 12;
      var minStr = minutes < 10 ? "0" + minutes : String(minutes);
      return hours + ":" + minStr + " " + ampm;
    }

    function legacyCopy(str) {
      var ta = document.createElement("textarea");
      ta.value = str;
      ta.setAttribute("readonly", "");
      ta.className = "HIKA-offscreen";
      shadow.appendChild(ta);
      ta.select();
      var ok = false;
      try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
      shadow.removeChild(ta);
      return ok;
    }

    function copyText(str, btn) {
      function done() {
        btn.classList.add("HIKA-copied");
        btn.setAttribute("aria-label", "Copied");
        btn.setAttribute("title", "Copied");
        setTimeout(function () {
          btn.classList.remove("HIKA-copied");
          btn.setAttribute("aria-label", "Copy reply");
          btn.setAttribute("title", "Copy reply");
        }, 1500);
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(str).then(done).catch(function () {
          if (legacyCopy(str)) done();
        });
      } else if (legacyCopy(str)) {
        done();
      }
    }

    function scrollToBottom() {
      function jump(smooth) {
        var top = panelBody.scrollHeight;
        if (smooth && typeof panelBody.scrollTo === "function") {
          panelBody.scrollTo({ top: top, behavior: "smooth" });
        } else {
          panelBody.scrollTop = top;
        }
      }
      // wait for layout, then glide down
      requestAnimationFrame(function () { jump(true); });
      // safety net: fonts / animations / late layout can change the height, so re-check once
      setTimeout(function () {
        if (panelBody.scrollHeight - panelBody.scrollTop - panelBody.clientHeight > 2) jump(false);
      }, 350);
    }

    function scrollToMessage() {
      scrollToBottom();
    }

    function appendMessage(text, sender) {
      var wrap = document.createElement("div");
      wrap.className = "HIKA-msg-wrap HIKA-msg-wrap-" + sender;

      var msg = document.createElement("div");
      msg.className = "HIKA-msg HIKA-msg-" + sender;
      if (sender === "bot") {
        msg.appendChild(renderMarkdown(text));
      } else {
        msg.textContent = text;
      }
      wrap.appendChild(msg);

      var meta = document.createElement("div");
      meta.className = "HIKA-meta";
      var time = document.createElement("span");
      time.className = "HIKA-timestamp";
      time.textContent = formatTime(new Date());
      meta.appendChild(time);

      if (sender === "bot") {
        var copyBtn = document.createElement("button");
        copyBtn.type = "button";
        copyBtn.className = "HIKA-copy";
        copyBtn.setAttribute("aria-label", "Copy reply");
        copyBtn.setAttribute("title", "Copy reply");
        copyBtn.innerHTML = copyIcon() + checkIcon(); // static markup
        copyBtn.addEventListener("click", function () { copyText(String(text), copyBtn); });
        meta.appendChild(copyBtn);
      }
      wrap.appendChild(meta);

      messagesEl.appendChild(wrap);
      scrollToMessage(wrap, sender);
      return msg;
    }

    function appendTyping() {
      var wrap = document.createElement("div");
      wrap.className = "HIKA-msg-wrap HIKA-msg-wrap-bot";
      wrap.innerHTML =
        '<div class="HIKA-msg HIKA-msg-bot HIKA-typing" aria-label="Typing">' +
          '<span class="HIKA-typing-dots">' +
            '<span class="HIKA-dot"></span><span class="HIKA-dot"></span><span class="HIKA-dot"></span>' +
          "</span>" +
        "</div>";
      messagesEl.appendChild(wrap);
      scrollToMessage(wrap, "user");
      return wrap;
    }

    function updateSendState() {
      sendBtn.disabled = isSending || !inputEl.value.trim();
    }

    function setBusy(busy) {
      isSending = busy;
      inputEl.disabled = busy;
      updateSendState();
    }

    /* ---------- open / close ---------- */
    function openPanel() {
      if (closing) {
        clearTimeout(closeTimer);
        closing = false;
        panel.classList.remove("HIKA-closing");
      }
      panel.hidden = false;
      bubble.setAttribute("aria-expanded", "true");
      bubble.setAttribute("aria-label", "Close chat");
      if (!hasGreeted) {
        appendMessage(config.greeting, "bot");
        hasGreeted = true;
      }
      if (csatView.hidden) {
        inputEl.focus();
      }
    }

    function closePanel() {
      if (panel.hidden || closing) return;
      bubble.setAttribute("aria-expanded", "false");
      bubble.setAttribute("aria-label", "Open chat");
      var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (reduce) {
        panel.hidden = true;
        return;
      }
      closing = true;
      panel.classList.add("HIKA-closing");
      closeTimer = setTimeout(function () {
        panel.hidden = true;
        panel.classList.remove("HIKA-closing");
        closing = false;
      }, 160);
    }

  function showCsatScreen() {
    messagesEl.hidden = true;
    footerEl.style.display = "none";
    endBtn.style.display = "none";
    csatView.hidden = false;

    // wait for layout, then scroll so the stars are fully visible
    requestAnimationFrame(function () {
      panelBody.scrollTo({ top: panelBody.scrollHeight, behavior: "smooth" });
    });
  }

    function resetWidgetState() {
      sessionId = null;
      hasGreeted = false;
      messagesEl.innerHTML = "";
      messagesEl.hidden = false;
      csatView.hidden = true;
      footerEl.style.display = "flex";
      endBtn.style.display = "block";
      starBtns.forEach(function (btn) { btn.classList.remove("selected"); });
      updateSendState();
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

    function errorText() {
      return config.fallbackMessage || DEFAULT_ERROR_MESSAGE;
    }

    /* ---------- sending ---------- */
    function handleSend() {
      if (isSending) return;
      var text = inputEl.value.trim();
      if (!text) return;

      appendMessage(text, "user");
      inputEl.value = "";
      updateSendState();

      if (!config.apiUrl) {
        appendMessage(
          "Chat isn't connected yet \u2014 missing data-api-url on the embed script.",
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
          var answer = data && typeof data.answer === "string" ? data.answer : "";
          appendMessage(answer.trim() ? answer : errorText(), "bot");
        })
        .catch(function (err) {
          console.error(
            "[HIKA Widget] /chat request failed. Target was: " + config.apiUrl + "/chat",
            err
          );
          typingEl.remove();
          appendMessage(errorText(), "bot");
        })
        .finally(function () {
          setBusy(false);
          inputEl.focus();
        });
    }

    /* ---------- events ---------- */
    bubble.addEventListener("click", function () {
      if (panel.hidden || closing) openPanel(); else closePanel();
    });
    closeBtn.addEventListener("click", closePanel);
    endBtn.addEventListener("click", showCsatScreen);
    themeBtn.addEventListener("click", toggleTheme);
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
    inputEl.addEventListener("input", updateSendState);
    inputEl.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.isComposing) handleSend();
    });
    root.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !panel.hidden) {
        closePanel();
        bubble.focus();
      }
    });

    window.__botaiWidget = { config: config, open: openPanel, close: closePanel };
  }

  /* ------------------------------------------------------------------ *
   *  Init
   * ------------------------------------------------------------------ */
  function init() {
    var scriptTag = CURRENT_SCRIPT || document.currentScript || document.querySelector("script[data-tenant-id]");

    if (!scriptTag) {
      console.error("[HIKA Widget] Could not locate its own <script> tag.");
      return;
    }

    var config = {
      tenantId: scriptTag.getAttribute("data-tenant-id"),
      botName: cleanText(scriptTag.getAttribute("data-name"), 60, "Chat"),
      apiUrl: cleanApiUrl(scriptTag.getAttribute("data-api-url")),
      color: normalizeColor(scriptTag.getAttribute("data-color"), DEFAULT_COLOR),
      position: sanitizePosition(scriptTag.getAttribute("data-position")),
      greeting: cleanText(scriptTag.getAttribute("data-greeting"), 500, "Hi! How can I help you today?"),
      fallbackMessage: null,
    };

    if (!config.tenantId) {
      console.error("[HIKA Widget] Missing required data-tenant-id attribute \u2014 widget not mounted.");
      return;
    }
    if (!config.apiUrl) {
      console.error("[HIKA Widget] Missing data-api-url attribute \u2014 widget will mount but /chat calls will fail.");
      mountWidget(config);
      return;
    }

    fetchLiveSettings(config)
      .then(function (remoteSettings) {
        if (remoteSettings && typeof remoteSettings === "object") {
          config.botName = cleanText(remoteSettings.bot_name, 60, config.botName);
          config.color = normalizeColor(remoteSettings.theme_color, config.color);
          config.greeting = cleanText(remoteSettings.greeting_message, 500, config.greeting);
          config.fallbackMessage = cleanText(remoteSettings.fallback_message, 500, null);
        }
      })
      .catch(function () {
        // Fallback already logged in fetchLiveSettings; continue mounting with local script config
      })
      .finally(function () {
        mountWidget(config);
      });
  }

  /* ------------------------------------------------------------------ *
   *  Icons (static strings only)
   * ------------------------------------------------------------------ */
  function svgOpen(size, cls) {
    return '<svg' + (cls ? ' class="' + cls + '"' : "") + ' width="' + size + '" height="' + size + '" viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">';
  }

  function bubbleIcon() {
    return (
      svgOpen(26) +
      '<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>' +
      "</svg>"
    );
  }

  function closeIcon() {
    return svgOpen(18) + '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
  }

  function sendIcon() {
    return svgOpen(18) + '<line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>';
  }

  function moonIcon() {
    return svgOpen(16, "HIKA-icon-moon") + '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';
  }

  function sunIcon() {
    return (
      svgOpen(16, "HIKA-icon-sun") +
      '<circle cx="12" cy="12" r="4"/>' +
      '<line x1="12" y1="2" x2="12" y2="5"/><line x1="12" y1="19" x2="12" y2="22"/>' +
      '<line x1="4.2" y1="4.2" x2="6.3" y2="6.3"/><line x1="17.7" y1="17.7" x2="19.8" y2="19.8"/>' +
      '<line x1="2" y1="12" x2="5" y2="12"/><line x1="19" y1="12" x2="22" y2="12"/>' +
      '<line x1="4.2" y1="19.8" x2="6.3" y2="17.7"/><line x1="17.7" y1="6.3" x2="19.8" y2="4.2"/>' +
      "</svg>"
    );
  }

  function copyIcon() {
    return svgOpen(13, "HIKA-icon-copy") + '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>';
  }

  function checkIcon() {
    return svgOpen(13, "HIKA-icon-check") + '<polyline points="20 6 9 17 4 12"/></svg>';
  }

  /* ------------------------------------------------------------------ *
   *  Styles
   * ------------------------------------------------------------------ */
  function buildCSS(config) {
    var brand = config.color; // already validated: #rrggbb
    var lightText = relativeLuminance(brand) < 0.179;
    var onBrand = lightText ? "#ffffff" : "#16161d";
    var onSoft = lightText ? "rgba(255,255,255,0.2)" : "rgba(0,0,0,0.12)";
    var onSoftHover = lightText ? "rgba(255,255,255,0.35)" : "rgba(0,0,0,0.2)";

    return [
      "@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');",
      ":host{all:initial;}",

      /* theme tokens */
      ".HIKA-widget-root{",
      "--brand:" + brand + ";--brand-shadow:" + brand + "40;--on-brand:" + onBrand + ";",
      "--on-brand-soft:" + onSoft + ";--on-brand-soft-hover:" + onSoftHover + ";",
      "--panel:#ffffff;--body:#fafafb;--bot-a:#ffffff;--bot-b:#f5f5f8;--bot-text:#242430;--bot-border:#ececf1;",
      "--muted:#8b8b98;--line:#ececef;--input-bg:#ffffff;--input-text:#242430;--input-border:#dcdce2;",
      "--input-off:#f7f7f9;--placeholder:#9a9aa6;--title:#1e1e24;--star:#d0d0d8;--skip:#71717a;",
      "--code-bg:rgba(20,20,40,0.07);--pre-bg:#f1f1f5;--link:#3b4fd8;--table-line:#e2e2ea;--table-head:#f1f1f6;",
      "--shadow:rgba(0,0,0,0.2);--thumb:rgba(0,0,0,0.22);color-scheme:light;}",
      ".HIKA-widget-root.HIKA-dark{",
      "--panel:#181a20;--body:#1e2027;--bot-a:#2a2d37;--bot-b:#262933;--bot-text:#e9eaf0;--bot-border:#363946;",
      "--muted:#8489a0;--line:#2d303b;--input-bg:#23252d;--input-text:#e9eaf0;--input-border:#3a3e4b;",
      "--input-off:#1f2128;--placeholder:#7f8394;--title:#f1f1f5;--star:#4a4d5a;--skip:#9a9eb0;",
      "--code-bg:rgba(255,255,255,0.1);--pre-bg:#14161b;--link:#9db0ff;--table-line:#3a3e4b;--table-head:#31343f;",
      "--shadow:rgba(0,0,0,0.55);--thumb:rgba(255,255,255,0.25);color-scheme:dark;}",

      ".HIKA-widget-root{position:fixed;z-index:2147483000;",
      "font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;}",
      ".HIKA-widget-root *{box-sizing:border-box;}",
      ".HIKA-widget-bottom-right{right:20px;bottom:20px;}",
      ".HIKA-widget-bottom-left{left:20px;bottom:20px;}",
      ".HIKA-widget-root button{font-family:inherit;}",
      ".HIKA-widget-root button:focus-visible{outline:2px solid var(--brand);outline-offset:2px;}",
      ".HIKA-panel-header button:focus-visible{outline-color:var(--on-brand);}",
      ".HIKA-offscreen{position:fixed;left:-9999px;top:0;opacity:0;}",

      /* launcher bubble */
      ".HIKA-bubble{width:56px;height:56px;border-radius:50%;border:none;cursor:pointer;",
      "background:var(--brand);color:var(--on-brand);display:flex;align-items:center;justify-content:center;",
      "box-shadow:0 8px 24px rgba(0,0,0,0.18);transition:transform 0.15s ease;padding:0;}",
      ".HIKA-bubble:hover{transform:scale(1.05);}",

      /* panel */
      ".HIKA-panel{position:absolute;bottom:72px;right:0;width:340px;max-width:calc(100vw - 40px);",
      "height:420px;max-height:calc(100vh - 120px);background:var(--panel);border-radius:18px;",
      "box-shadow:0 12px 40px var(--shadow);display:flex;flex-direction:column;overflow:hidden;",
      "transform-origin:bottom right;transition:background-color .2s ease;}",
      ".HIKA-widget-bottom-left .HIKA-panel{right:auto;left:0;transform-origin:bottom left;}",
      ".HIKA-panel[hidden]{display:none;}",
      ".HIKA-panel:not([hidden]){animation:HIKA-pop .18s ease-out;}",
      ".HIKA-panel.HIKA-closing{animation:HIKA-pop-out .16s ease-in forwards;}",
      "@keyframes HIKA-pop{from{opacity:0;transform:translateY(8px) scale(.97);}to{opacity:1;transform:none;}}",
      "@keyframes HIKA-pop-out{from{opacity:1;transform:none;}to{opacity:0;transform:translateY(8px) scale(.97);}}",

      /* header */
      ".HIKA-panel-header{background:var(--brand);color:var(--on-brand);padding:12px 14px;gap:10px;",
      "display:flex;align-items:center;justify-content:space-between;flex-shrink:0;}",
      ".HIKA-header-main{display:flex;align-items:center;gap:10px;min-width:0;}",
      ".HIKA-avatar{position:relative;flex-shrink:0;width:32px;height:32px;border-radius:50%;",
      "background:var(--on-brand-soft);display:flex;align-items:center;justify-content:center;",
      "font-weight:600;font-size:14px;}",
      ".HIKA-status{position:absolute;right:-1px;bottom:-1px;width:9px;height:9px;border-radius:50%;",
      "background:#3ddc84;border:2px solid var(--brand);}",
      ".HIKA-panel-title{font-weight:600;font-size:15px;letter-spacing:-0.01em;",
      "overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0;}",
      ".HIKA-header-actions{display:flex;align-items:center;gap:6px;flex-shrink:0;}",
      ".HIKA-end-btn{background:var(--on-brand-soft);border:none;color:var(--on-brand);font-size:11.5px;",
      "font-weight:500;padding:4px 9px;border-radius:12px;cursor:pointer;transition:background 0.2s;}",
      ".HIKA-end-btn:hover{background:var(--on-brand-soft-hover);}",
      ".HIKA-theme,.HIKA-close{background:none;border:none;color:var(--on-brand);cursor:pointer;",
      "padding:5px;display:flex;align-items:center;justify-content:center;border-radius:50%;opacity:0.85;transition:opacity .15s, background .15s;}",
      ".HIKA-theme:hover,.HIKA-close:hover{opacity:1;background:var(--on-brand-soft);}",
      ".HIKA-icon-sun{display:none;}",
      ".HIKA-dark .HIKA-icon-sun{display:block;}",
      ".HIKA-dark .HIKA-icon-moon{display:none;}",

      /* body + scrollbar */
      ".HIKA-panel-body{flex:1;padding:16px;overflow-y:auto;background:var(--body);display:flex;flex-direction:column;",
      "scrollbar-width:thin;scrollbar-color:var(--thumb) transparent;transition:background-color .2s ease;}",
      ".HIKA-panel-body::-webkit-scrollbar{width:6px;}",
      ".HIKA-panel-body::-webkit-scrollbar-track{background:transparent;}",
      ".HIKA-panel-body::-webkit-scrollbar-thumb{background:var(--thumb);border-radius:6px;}",
      ".HIKA-messages{display:flex;flex-direction:column;gap:12px;flex:1;}",
      ".HIKA-messages[hidden]{display:none;}",

      /* messages */
      ".HIKA-msg-wrap{display:flex;flex-direction:column;max-width:82%;min-width:0;animation:HIKA-in .2s ease-out;}",
      "@keyframes HIKA-in{from{opacity:0;transform:translateY(4px);}to{opacity:1;transform:none;}}",
      ".HIKA-msg-wrap-bot{align-self:flex-start;align-items:flex-start;max-width:92%;}",
      ".HIKA-msg-wrap-user{align-self:flex-end;align-items:flex-end;}",
      ".HIKA-msg{max-width:100%;padding:10px 14px;border-radius:16px;font-size:13.5px;",
      "line-height:1.5;overflow-wrap:anywhere;letter-spacing:-0.003em;}",
      ".HIKA-msg-user{white-space:pre-wrap;background:var(--brand);color:var(--on-brand);",
      "border-bottom-right-radius:5px;box-shadow:0 2px 8px var(--brand-shadow);}",
      ".HIKA-msg-bot{background:linear-gradient(180deg,var(--bot-a),var(--bot-b));color:var(--bot-text);",
      "border:1px solid var(--bot-border);border-bottom-left-radius:5px;",
      "box-shadow:0 1px 2px rgba(0,0,0,0.05);}",

      ".HIKA-meta{display:flex;align-items:center;gap:6px;margin-top:3px;padding:0 4px;min-height:18px;}",
      ".HIKA-timestamp{font-size:10.5px;color:var(--muted);}",
      ".HIKA-copy{background:none;border:none;color:var(--muted);cursor:pointer;padding:2px 3px;border-radius:5px;",
      "display:flex;align-items:center;opacity:0;transition:opacity .15s, color .15s;}",
      ".HIKA-msg-wrap:hover .HIKA-copy,.HIKA-copy:focus-visible,.HIKA-copy.HIKA-copied{opacity:1;}",
      ".HIKA-copy:hover{color:var(--bot-text);}",
      ".HIKA-icon-check{display:none;}",
      ".HIKA-copied .HIKA-icon-check{display:block;color:#2fb872;}",
      ".HIKA-copied .HIKA-icon-copy{display:none;}",
      "@media (hover:none){.HIKA-copy{opacity:.8;}}",

      /* rendered markdown */
      ".HIKA-md>*:first-child{margin-top:0;}",
      ".HIKA-md>*:last-child{margin-bottom:0;}",
      ".HIKA-md p{margin:0 0 8px;}",
      ".HIKA-md strong{font-weight:600;}",
      ".HIKA-md ul,.HIKA-md ol{margin:4px 0 8px;padding-left:20px;}",
      ".HIKA-md li{margin:2px 0;padding-left:2px;}",
      ".HIKA-md li>ul,.HIKA-md li>ol{margin:2px 0;}",
      ".HIKA-md .HIKA-h{margin:10px 0 6px;font-weight:600;line-height:1.3;letter-spacing:-0.01em;}",
      ".HIKA-md h3.HIKA-h{font-size:15px;}",
      ".HIKA-md h4.HIKA-h{font-size:14px;}",
      ".HIKA-md h5.HIKA-h{font-size:13.5px;}",
      ".HIKA-md a{color:var(--link);text-decoration:underline;text-underline-offset:2px;}",
      ".HIKA-md a:hover{text-decoration-thickness:2px;}",
      ".HIKA-md code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px;",
      "background:var(--code-bg);padding:1px 5px;border-radius:5px;}",
      ".HIKA-md pre{margin:6px 0 8px;padding:10px 12px;background:var(--pre-bg);border-radius:10px;overflow-x:auto;}",
      ".HIKA-md pre code{background:none;padding:0;font-size:12px;white-space:pre;overflow-wrap:normal;}",
      ".HIKA-md blockquote{margin:6px 0 8px;padding:2px 0 2px 10px;border-left:3px solid var(--brand);color:var(--muted);}",
      ".HIKA-md hr{border:none;border-top:1px solid var(--bot-border);margin:10px 0;}",
      ".HIKA-table-wrap{overflow-x:auto;margin:6px 0 8px;max-width:100%;border:1px solid var(--table-line);border-radius:8px;}",
      ".HIKA-md table{border-collapse:collapse;font-size:12.5px;width:100%;}",
      ".HIKA-md th,.HIKA-md td{padding:6px 10px;border-bottom:1px solid var(--table-line);text-align:left;overflow-wrap:normal;white-space:nowrap;}",
      ".HIKA-md th{background:var(--table-head);font-weight:600;}",
      ".HIKA-md tr:last-child td{border-bottom:none;}",
      ".HIKA-md .HIKA-al-center{text-align:center;}",
      ".HIKA-md .HIKA-al-right{text-align:right;}",

      /* typing */
      ".HIKA-typing-dots{display:inline-flex;gap:4px;align-items:center;padding:2px 0;}",
      ".HIKA-typing-dots .HIKA-dot{width:6px;height:6px;border-radius:50%;background:var(--muted);",
      "animation:HIKA-bounce 1.2s infinite ease-in-out;}",
      ".HIKA-typing-dots .HIKA-dot:nth-child(2){animation-delay:0.15s;}",
      ".HIKA-typing-dots .HIKA-dot:nth-child(3){animation-delay:0.3s;}",
      "@keyframes HIKA-bounce{0%,60%,100%{transform:translateY(0);opacity:.4;}30%{transform:translateY(-4px);opacity:1;}}",

      /* CSAT */
      ".HIKA-csat-view{display:flex;flex-direction:column;align-items:center;justify-content:center;",
      "height:100%;text-align:center;padding:20px 10px;margin:auto;}",
      ".HIKA-csat-view[hidden]{display:none;}",
      ".HIKA-csat-title{font-size:16px;font-weight:600;color:var(--title);margin-bottom:18px;}",
      ".HIKA-stars{display:flex;gap:8px;margin-bottom:20px;}",
      ".HIKA-star{background:none;border:none;font-size:28px;color:var(--star);cursor:pointer;",
      "padding:2px;transition:color 0.15s, transform 0.15s;line-height:1;}",
      ".HIKA-star:hover,.HIKA-star.hover{color:#ffb400;transform:scale(1.2);}",
      ".HIKA-csat-skip{background:none;border:none;color:var(--skip);font-size:12.5px;cursor:pointer;",
      "text-decoration:underline;padding:4px 8px;}",
      ".HIKA-csat-skip:hover{color:var(--title);}",

      /* footer */
      ".HIKA-panel-footer{flex-shrink:0;display:flex;align-items:center;gap:8px;",
      "padding:10px 12px;border-top:1px solid var(--line);background:var(--panel);transition:background-color .2s ease;}",
      ".HIKA-input{flex:1;min-width:0;border:1px solid var(--input-border);border-radius:20px;padding:9px 14px;",
      "font-size:13.5px;outline:none;font-family:inherit;background:var(--input-bg);color:var(--input-text);",
      "transition:border-color .15s, box-shadow .15s, background-color .2s;}",
      ".HIKA-input::placeholder{color:var(--placeholder);}",
      ".HIKA-input:focus{border-color:var(--brand);box-shadow:0 0 0 3px var(--brand-shadow);}",
      ".HIKA-input:disabled{background:var(--input-off);cursor:not-allowed;}",
      ".HIKA-send{flex-shrink:0;width:34px;height:34px;border-radius:50%;border:none;",
      "background:var(--brand);color:var(--on-brand);display:flex;align-items:center;",
      "justify-content:center;cursor:pointer;padding:0;box-shadow:0 2px 6px var(--brand-shadow);transition:opacity .15s, transform .15s;}",
      ".HIKA-send:hover:not(:disabled){transform:scale(1.06);}",
      ".HIKA-send:disabled{opacity:.45;cursor:not-allowed;box-shadow:none;}",

      /* small screens: near full-screen panel */
      "@media (max-width:480px){",
      ".HIKA-panel,.HIKA-widget-bottom-left .HIKA-panel{position:fixed;left:10px;right:10px;top:10px;bottom:88px;",
      "width:auto;max-width:none;height:auto;max-height:none;}",
      ".HIKA-input{font-size:16px;}",
      "}",

      /* motion preferences */
      "@media (prefers-reduced-motion:reduce){",
      ".HIKA-widget-root *{animation:none !important;transition:none !important;}",
      "}",
    ].join("");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();