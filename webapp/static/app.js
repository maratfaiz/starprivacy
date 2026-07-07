(function () {
  "use strict";

  const tg = window.Telegram && window.Telegram.WebApp;
  if (tg) {
    tg.ready();
    tg.expand();
    try { tg.setBackgroundColor && tg.setBackgroundColor("#05070A"); } catch (e) {}
    try { tg.setHeaderColor && tg.setHeaderColor("#05070A"); } catch (e) {}
  }

  const initData = tg ? tg.initData : "";
  const STAR_ICON =
    '<svg width="13" height="13" viewBox="0 0 24 24" fill="#F7CE68"><path d="M12 1l3.09 6.26L22 8.27l-5 4.87 1.18 6.88L12 16.9l-6.18 3.12L7 13.14 2 8.27l6.91-1.01L12 1z"/></svg>';

  async function api(path, options) {
    options = options || {};
    options.headers = Object.assign({}, options.headers, { Authorization: "tma " + initData });
    if (options.body && typeof options.body !== "string") {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(options.body);
    }
    const res = await fetch(path, options);
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error("API " + res.status + ": " + text);
    }
    return res.status === 204 ? null : res.json();
  }

  async function fetchMediaUrl(messageId) {
    const res = await fetch("/api/media/" + messageId, { headers: { Authorization: "tma " + initData } });
    if (!res.ok) return null;
    const blob = await res.blob();
    return URL.createObjectURL(blob);
  }

  function fmtDate(iso) {
    if (!iso) return "";
    return new Date(iso).toLocaleString("ru-RU", {
      day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
    });
  }

  function el(html) {
    const t = document.createElement("template");
    t.innerHTML = html.trim();
    return t.content.firstElementChild;
  }

  // ---------------------------------------------------------------- sheet
  const sheetOverlay = document.getElementById("sheet-overlay");
  const sheetEl = document.getElementById("sheet");

  function openSheet(contentNode) {
    sheetEl.innerHTML = "";
    sheetEl.appendChild(el('<div class="sheet-handle"></div>'));
    sheetEl.appendChild(contentNode);
    sheetOverlay.hidden = false;
  }

  function closeSheet() {
    sheetOverlay.hidden = true;
  }

  sheetOverlay.addEventListener("click", (e) => {
    if (e.target === sheetOverlay) closeSheet();
  });

  function sheetHeader(title, iconSvg) {
    const header = el(
      '<div class="sheet-header">' +
        '<div style="display:flex; align-items:center; gap:9px;">' +
        (iconSvg || "") +
        '<span class="sheet-title">' + title + "</span>" +
        "</div>" +
        '<button class="sheet-close">&times;</button>' +
        "</div>"
    );
    header.querySelector(".sheet-close").addEventListener("click", closeSheet);
    return header;
  }

  // ---------------------------------------------------------------- state
  const content = document.getElementById("content");
  const tierPill = document.getElementById("tier-pill");
  const tierPillText = document.getElementById("tier-pill-text");
  let meCache = null;
  let tariffsCache = null;

  function tierPillLabel(me) {
    if (!me) return "…";
    if (me.tier === "admin") return "Admin";
    if (me.tier_title) return me.tier_title;
    return "Нет тарифа";
  }

  async function loadMe(force) {
    if (meCache && !force) return meCache;
    meCache = await api("/api/me");
    tierPillText.textContent = tierPillLabel(meCache);
    return meCache;
  }

  async function loadTariffs() {
    if (tariffsCache) return tariffsCache;
    tariffsCache = await api("/api/tariffs");
    return tariffsCache;
  }

  tierPill.addEventListener("click", async () => {
    const me = await loadMe();
    if (me.is_admin) return;
    openTariffSheet(me);
  });

  // ---------------------------------------------------------------- tabs
  const tabButtons = document.querySelectorAll(".tab-btn");
  for (const btn of tabButtons) {
    btn.addEventListener("click", () => {
      for (const b of tabButtons) b.classList.toggle("active", b === btn);
      if (btn.dataset.tab === "dashboard") renderDashboard();
      else renderConnectionsList();
    });
  }

  // ---------------------------------------------------------------- dashboard
  async function renderDashboard() {
    content.innerHTML = '<p class="hint">Загрузка…</p>';
    try {
      const me = await loadMe(true);
      content.innerHTML = "";
      content.appendChild(buildHeroCard(me));
      content.appendChild(buildBento(me));
      content.appendChild(buildActionRow(me));
    } catch (err) {
      content.innerHTML = '<p class="error">Не удалось загрузить статус: ' + err.message + "</p>";
    }
  }

  function daysLeft(me) {
    if (!me.expires_at) return null;
    return Math.max(0, Math.ceil((new Date(me.expires_at) - new Date()) / 86400000));
  }

  function progressPercent(me) {
    if (!me.expires_at || !me.started_at || !me.duration_days) return 100;
    const totalMs = me.duration_days * 86400000;
    const remainingMs = new Date(me.expires_at) - new Date();
    return Math.max(3, Math.min(100, (remainingMs / totalMs) * 100));
  }

  function buildHeroCard(me) {
    const active = me.allowed;
    const isUnlimited = me.tier === "admin";
    const left = daysLeft(me);

    const statusLabel = active ? "Архивирование активно" : "Архивирование не активно";
    const dotClass = active ? "pulse-dot" : "pulse-dot off";
    const labelClass = active ? "hero-status-label" : "hero-status-label off";

    let daysBlock;
    if (isUnlimited) {
      daysBlock = '<span class="hero-days-number">∞</span><span class="hero-days-label">безлимитный доступ</span>';
    } else if (active && left !== null) {
      daysBlock = '<span class="hero-days-number">' + left + '</span><span class="hero-days-label">' + pluralDays(left) + "</span>";
    } else {
      daysBlock = '<span class="hero-days-number">0</span><span class="hero-days-label">дней осталось</span>';
    }

    const expiryText = isUnlimited
      ? "Постоянный доступ администратора"
      : me.expires_at
      ? "Действует до " + fmtDate(me.expires_at) + " UTC"
      : "Оформите подписку, чтобы начать архивирование";

    const pct = isUnlimited ? 100 : active ? progressPercent(me) : 3;

    const card = el(
      '<div class="hero-card">' +
        '<svg class="star-deco" style="top:14px; right:18px;" width="11" height="11" viewBox="0 0 24 24" fill="#F7CE68"><path d="M12 1l3.09 6.26L22 8.27l-5 4.87 1.18 6.88L12 16.9l-6.18 3.12L7 13.14 2 8.27l6.91-1.01L12 1z"/></svg>' +
        '<svg class="star-deco" style="top:46px; right:54px; animation-delay:.6s;" width="7" height="7" viewBox="0 0 24 24" fill="#F7CE68"><path d="M12 1l3.09 6.26L22 8.27l-5 4.87 1.18 6.88L12 16.9l-6.18 3.12L7 13.14 2 8.27l6.91-1.01L12 1z"/></svg>' +
        '<div class="hero-status-row">' +
        '<div class="' + dotClass + '"></div>' +
        '<span class="' + labelClass + '">' + statusLabel + "</span>" +
        (me.tier_title ? '<span class="tier-badge">' + me.tier_title + "</span>" : "") +
        "</div>" +
        '<div class="hero-days-row">' + daysBlock + "</div>" +
        '<div class="hero-expiry">' + expiryText + "</div>" +
        '<div class="progress-track"><div class="progress-fill" style="width:' + pct + '%;"></div></div>' +
        "</div>"
    );
    return card;
  }

  function pluralDays(n) {
    const mod10 = n % 10, mod100 = n % 100;
    let word = "дней";
    if (mod100 < 11 || mod100 > 14) {
      if (mod10 === 1) word = "день";
      else if (mod10 >= 2 && mod10 <= 4) word = "дня";
    }
    return word + " осталось";
  }

  function buildBento(me) {
    const activeConns = me.connections.filter((c) => c.is_enabled).length;
    const stats = me.archive_stats || { total_messages: 0, saved_originals: 0 };

    const bento = el(
      '<div class="bento">' +
        '<div class="bento-main">' +
        '<div class="eyebrow">' +
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-55)" stroke-width="2"><path d="M12 22s8-7.5 8-13a8 8 0 10-16 0c0 5.5 8 13 8 13z"/><circle cx="12" cy="9" r="2.5"/></svg>' +
        "<span>бизнес-подключения</span>" +
        "</div>" +
        "<div>" +
        '<div class="title">' + activeConns + " из " + me.connections.length + " активно</div>" +
        '<div class="subtitle">' + (me.connections.length ? "Нажмите, чтобы открыть архив" : "Подключите бота в Telegram") + "</div>" +
        "</div>" +
        '<span class="cta">Открыть архив →</span>' +
        "</div>" +
        '<div class="stat-card">' +
        '<div class="value">' + stats.total_messages + "</div>" +
        '<div class="label">сообщений заархивировано</div>' +
        "</div>" +
        '<div class="stat-card">' +
        '<div class="value">' + stats.saved_originals + "</div>" +
        '<div class="label">оригиналов сохранено</div>' +
        "</div>" +
        "</div>"
    );
    bento.querySelector(".bento-main").addEventListener("click", () => {
      document.querySelector('.tab-btn[data-tab="archive"]').click();
    });
    return bento;
  }

  function buildActionRow(me) {
    if (me.is_admin) {
      const row = el('<div class="action-row"></div>');
      const infoBtn = el(buttonHtml("outline", infoIcon(), "Как подключить бота"));
      infoBtn.addEventListener("click", openInfoSheet);
      row.appendChild(infoBtn);
      return row;
    }

    const primaryLabel = me.allowed ? "Продлить" : "Оформить подписку";
    const row = el('<div class="action-row"></div>');
    const primaryBtn = el(buttonHtml("gold", lightningIcon("#1A1408"), primaryLabel));
    primaryBtn.addEventListener("click", () => openTariffSheet(me));
    const infoBtn = el(buttonHtml("outline", infoIcon(), "Как подключить"));
    infoBtn.addEventListener("click", openInfoSheet);
    row.appendChild(primaryBtn);
    row.appendChild(infoBtn);
    return row;
  }

  function buttonHtml(kind, iconSvg, label) {
    return '<button class="btn ' + kind + '">' + iconSvg + "<span>" + label + "</span></button>";
  }

  function lightningIcon(color) {
    return '<svg width="15" height="15" viewBox="0 0 24 24" fill="' + color + '"><path d="M13 2L3 14h7l-1 8 11-13h-7l1-7z"/></svg>';
  }

  function infoIcon() {
    return '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#F7CE68" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>';
  }

  // ---------------------------------------------------------------- tariff sheet
  async function openTariffSheet(me) {
    const container = document.createElement("div");
    container.appendChild(sheetHeader(me.allowed ? "Продлить подписку" : "Оформить подписку", lightningIcon("#F7CE68")));

    const body = el('<div><p class="hint">Загрузка тарифов…</p></div>');
    container.appendChild(body);
    openSheet(container);

    try {
      const tariffs = await loadTariffs();
      let selectedKey = tariffs.some((t) => t.key === "premium") ? "premium" : tariffs[0].key;
      renderPlanForm();

      function renderPlanForm() {
        body.innerHTML = "";
        const list = el('<div></div>');
        for (const tariff of tariffs) {
          const selected = tariff.key === selectedKey;
          const perMonth = (tariff.stars_price / (tariff.duration_days / 30)).toFixed(0) + " ⭐/мес";
          const option = el(
            '<div class="plan-option' + (selected ? " selected" : "") + '">' +
              (tariff.key === "premium" ? '<span class="plan-badge">ВЫГОДНО</span>' : "") +
              "<div><div class=\"title\">" + tariff.title + '</div><div class="subtitle">' + perMonth + "</div></div>" +
              '<div class="price">' + STAR_ICON + " " + tariff.stars_price + "</div>" +
              "</div>"
          );
          option.addEventListener("click", () => {
            selectedKey = tariff.key;
            renderPlanForm();
          });
          list.appendChild(option);
        }
        body.appendChild(list);

        const selectedTariff = tariffs.find((t) => t.key === selectedKey);
        const payBtn = el(
          '<button class="btn gold" style="width:100%; margin-top:8px;">' +
            lightningIcon("#1A1408") +
            "<span>Оплатить " + selectedTariff.stars_price + " ⭐</span>" +
            "</button>"
        );
        payBtn.addEventListener("click", () => submitTariff(selectedTariff, payBtn));
        body.appendChild(payBtn);
        body.appendChild(el('<div class="hint" style="text-align:center; margin-top:10px;">Оплата через Telegram Stars</div>'));
      }

      async function submitTariff(tariff, payBtn) {
        payBtn.disabled = true;
        try {
          const { invoice_url } = await api("/api/subscribe", { method: "POST", body: { tariff: tariff.key } });
          const onResult = async (status) => {
            payBtn.disabled = false;
            if (status === "paid") {
              await loadMe(true);
              body.innerHTML = "";
              body.appendChild(
                el(
                  '<div class="sheet-success">' +
                    '<div class="icon"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#2ED9A6" stroke-width="2.4"><polyline points="20 6 9 17 4 12"/></svg></div>' +
                    '<div class="title">Подписка активна!</div>' +
                    '<div class="subtitle">Тариф «' + tariff.title + '» активирован на ' + tariff.duration_days + " дней.</div>" +
                    "</div>"
                )
              );
              const doneBtn = el('<button class="btn gold" style="width:100%; margin-top:20px;"><span>Готово</span></button>');
              doneBtn.addEventListener("click", () => {
                closeSheet();
                renderDashboard();
              });
              body.appendChild(doneBtn);
            }
          };
          if (tg && tg.openInvoiceLink) {
            tg.openInvoiceLink(invoice_url, onResult);
          } else {
            window.open(invoice_url, "_blank");
            payBtn.disabled = false;
          }
        } catch (err) {
          payBtn.disabled = false;
          alert("Не удалось создать счёт: " + err.message);
        }
      }
    } catch (err) {
      body.innerHTML = '<p class="error">Не удалось загрузить тарифы: ' + err.message + "</p>";
    }
  }

  function openInfoSheet() {
    const container = document.createElement("div");
    container.appendChild(sheetHeader("Как подключить бота", infoIcon()));
    container.appendChild(
      el(
        '<div class="sheet-info">' +
          "<p>1. Откройте <b>Настройки Telegram → Бизнес → Чат-боты</b>.</p>" +
          "<p>2. Выберите <b>StarPrivacyBot</b> и включите его для нужных чатов.</p>" +
          "<p>3. С этого момента входящие сообщения в этих чатах архивируются, а при их редактировании или удалении вы получите уведомление с оригиналом.</p>" +
          "<p>⚠️ Включайте бота только для чатов, где у вас есть право хранить переписку.</p>" +
          "</div>"
      )
    );
    const doneBtn = el('<button class="btn outline" style="width:100%; margin-top:8px;"><span>Готово</span></button>');
    doneBtn.addEventListener("click", closeSheet);
    container.appendChild(doneBtn);
    openSheet(container);
  }

  // ---------------------------------------------------------------- archive
  async function renderConnectionsList() {
    content.innerHTML = '<p class="hint">Загрузка…</p>';
    try {
      const me = await loadMe(true);
      content.innerHTML = "";
      content.appendChild(el('<div class="section-title">Подключения</div>'));

      if (me.connections.length === 0) {
        content.appendChild(el('<p class="hint">Пока нет бизнес-подключений. Подключите бота в Настройках Telegram → Бизнес.</p>'));
        return;
      }

      for (const conn of me.connections) {
        const row = el(
          '<div class="row-card">' +
            '<div class="row-left">' +
            '<div class="row-icon">' +
            '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--text)" stroke-width="2"><path d="M12 22s8-7.5 8-13a8 8 0 10-16 0c0 5.5 8 13 8 13z"/><circle cx="12" cy="9" r="2.5"/></svg>' +
            "</div>" +
            '<div><div class="row-title">' + conn.connection_id + "</div></div>" +
            "</div>" +
            '<div style="display:flex; align-items:center;">' +
            '<span class="badge ' + (conn.is_enabled ? "online" : "offline") + '">' + (conn.is_enabled ? "активно" : "отключено") + "</span>" +
            '<svg class="row-chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>' +
            "</div>" +
            "</div>"
        );
        row.addEventListener("click", () => renderChatsList(conn.connection_id));
        content.appendChild(row);
      }
    } catch (err) {
      content.innerHTML = '<p class="error">Не удалось загрузить подключения: ' + err.message + "</p>";
    }
  }

  async function renderChatsList(connectionId) {
    content.innerHTML = '<p class="hint">Загрузка чатов…</p>';
    try {
      const chats = await api("/api/connections/" + encodeURIComponent(connectionId) + "/chats");
      content.innerHTML = "";
      const back = el('<span class="breadcrumb">← Ко всем подключениям</span>');
      back.addEventListener("click", renderConnectionsList);
      content.appendChild(back);
      content.appendChild(el('<div class="section-title">Чаты</div>'));

      if (chats.length === 0) {
        content.appendChild(el('<p class="hint">В этом подключении пока нет архивных сообщений.</p>'));
        return;
      }

      for (const chat of chats) {
        const badges =
          (chat.edited_count ? '<span class="badge edited">✏️ ' + chat.edited_count + "</span>" : "") +
          (chat.deleted_count ? '<span class="badge deleted">🗑️ ' + chat.deleted_count + "</span>" : "");
        const row = el(
          '<div class="row-card">' +
            '<div class="row-left">' +
            '<div class="row-icon">' +
            '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--text)" stroke-width="2"><circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7"/></svg>' +
            "</div>" +
            '<div style="min-width:0;">' +
            '<div class="row-title">' + (chat.sender_name || chat.chat_id) + "</div>" +
            '<div class="row-subtitle">' + (chat.last_message_preview || "") + "</div>" +
            "</div></div>" +
            '<div style="display:flex; align-items:center; flex-shrink:0;">' + badges +
            '<svg class="row-chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>' +
            "</div></div>"
        );
        row.addEventListener("click", () => renderMessages(connectionId, chat.chat_id));
        content.appendChild(row);
      }
    } catch (err) {
      content.innerHTML = '<p class="error">Не удалось загрузить чаты: ' + err.message + "</p>";
    }
  }

  async function renderMessages(connectionId, chatId) {
    content.innerHTML = '<p class="hint">Загрузка сообщений…</p>';
    try {
      const messages = await api(
        "/api/connections/" + encodeURIComponent(connectionId) + "/chats/" + chatId + "/messages?limit=100"
      );
      content.innerHTML = "";
      const back = el('<span class="breadcrumb">← К списку чатов</span>');
      back.addEventListener("click", () => renderChatsList(connectionId));
      content.appendChild(back);

      for (const msg of messages) {
        content.appendChild(buildMessageCard(msg));
      }
    } catch (err) {
      content.innerHTML = '<p class="error">Не удалось загрузить сообщения: ' + err.message + "</p>";
    }
  }

  function buildMessageCard(msg) {
    const badges =
      (msg.is_edited ? '<span class="badge edited">изменено</span>' : "") +
      (msg.is_deleted ? '<span class="badge deleted">удалено</span>' : "");

    const card = el(
      '<div class="message">' +
        '<div class="meta">' + (msg.sender_name || "") + " · " + fmtDate(msg.sent_at) + badges + "</div>" +
        '<div class="body">' + (msg.text || msg.caption || "<i>[" + msg.content_type + "]</i>") + "</div>" +
        "</div>"
    );

    if (msg.is_edited && msg.previous_text) {
      card.appendChild(el('<div class="diff"><b>Было:</b> ' + msg.previous_text + "</div>"));
    }

    if (msg.has_media) {
      const img = document.createElement("img");
      img.className = "media-preview";
      img.alt = msg.content_type;
      fetchMediaUrl(msg.id).then((url) => { if (url) img.src = url; });
      card.appendChild(img);
    }

    return card;
  }

  renderDashboard();
})();
