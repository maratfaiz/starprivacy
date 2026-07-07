(function () {
  "use strict";

  const tg = window.Telegram && window.Telegram.WebApp;
  if (tg) {
    tg.ready();
    tg.expand();
  }

  function applyTheme() {
    if (!tg || !tg.themeParams) return;
    const root = document.documentElement.style;
    const map = {
      bg_color: "--tg-theme-bg-color",
      text_color: "--tg-theme-text-color",
      hint_color: "--tg-theme-hint-color",
      link_color: "--tg-theme-link-color",
      button_color: "--tg-theme-button-color",
      button_text_color: "--tg-theme-button-text-color",
      secondary_bg_color: "--tg-theme-secondary-bg-color",
    };
    for (const [key, cssVar] of Object.entries(map)) {
      if (tg.themeParams[key]) root.setProperty(cssVar, tg.themeParams[key]);
    }
  }
  applyTheme();
  if (tg) tg.onEvent("themeChanged", applyTheme);

  const initData = tg ? tg.initData : "";

  async function api(path, options) {
    options = options || {};
    options.headers = Object.assign({}, options.headers, {
      Authorization: "tma " + initData,
    });
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
    const res = await fetch("/api/media/" + messageId, {
      headers: { Authorization: "tma " + initData },
    });
    if (!res.ok) return null;
    const blob = await res.blob();
    return URL.createObjectURL(blob);
  }

  function fmtDate(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    return d.toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  }

  function el(html) {
    const template = document.createElement("template");
    template.innerHTML = html.trim();
    return template.content.firstElementChild;
  }

  // ---------------------------------------------------------------------
  // Tabs
  // ---------------------------------------------------------------------
  const tabButtons = document.querySelectorAll(".tab-button");
  const panels = {
    dashboard: document.getElementById("tab-dashboard"),
    archive: document.getElementById("tab-archive"),
  };

  function showTab(name) {
    for (const btn of tabButtons) btn.classList.toggle("active", btn.dataset.tab === name);
    for (const [key, panel] of Object.entries(panels)) panel.hidden = key !== name;
    if (name === "dashboard") renderDashboard();
    if (name === "archive") renderConnectionsList();
  }

  for (const btn of tabButtons) {
    btn.addEventListener("click", () => showTab(btn.dataset.tab));
  }

  // ---------------------------------------------------------------------
  // Dashboard tab
  // ---------------------------------------------------------------------
  async function renderDashboard() {
    const panel = panels.dashboard;
    panel.innerHTML = '<p class="hint">Загрузка…</p>';
    try {
      const [me, tariffs] = await Promise.all([api("/api/me"), api("/api/tariffs")]);
      panel.innerHTML = "";
      panel.appendChild(buildStatusCard(me));
      if (!me.is_admin) {
        for (const tariff of tariffs) {
          panel.appendChild(buildTariffCard(tariff, me));
        }
      }
    } catch (err) {
      panel.innerHTML = '<p class="error">Не удалось загрузить данные: ' + err.message + "</p>";
    }
  }

  function buildStatusCard(me) {
    let tierLabel = "не активен";
    if (me.tier === "admin") tierLabel = "администратор (бесплатно навсегда)";
    else if (me.tier_title) tierLabel = me.tier_title;

    const retention = me.max_stored_days == null ? "без ограничений" : me.max_stored_days + " дней";
    const expiry = me.expires_at ? "Действует до " + fmtDate(me.expires_at) + " UTC" : "";
    const connCount = me.connections.filter((c) => c.is_enabled).length;

    return el(
      '<div class="card">' +
        "<h2>Ваш статус</h2>" +
        "<p>Тариф: <b>" + tierLabel + "</b></p>" +
        "<p>История сообщений: " + retention + "</p>" +
        (expiry ? '<p class="hint">' + expiry + "</p>" : "") +
        "<p>Бизнес-подключений активно: " + connCount + " из " + me.connections.length + "</p>" +
        "</div>"
    );
  }

  function buildTariffCard(tariff, me) {
    const card = el(
      '<div class="card">' +
        "<h3>" + tariff.title + " — " + tariff.stars_price + "⭐/мес</h3>" +
        '<p class="hint">' + tariff.description + "</p>" +
        '<button class="button">Купить</button>' +
        "</div>"
    );
    const button = card.querySelector("button");
    button.addEventListener("click", () => buyTariff(tariff.key, button));
    return card;
  }

  async function buyTariff(tariffKey, button) {
    button.disabled = true;
    button.textContent = "Открываем оплату…";
    try {
      const { invoice_url } = await api("/api/subscribe", { method: "POST", body: { tariff: tariffKey } });
      if (tg && tg.openInvoiceLink) {
        tg.openInvoiceLink(invoice_url, (status) => {
          button.disabled = false;
          button.textContent = "Купить";
          if (status === "paid") renderDashboard();
        });
      } else {
        window.open(invoice_url, "_blank");
        button.disabled = false;
        button.textContent = "Купить";
      }
    } catch (err) {
      button.disabled = false;
      button.textContent = "Купить";
      alert("Не удалось создать счёт: " + err.message);
    }
  }

  // ---------------------------------------------------------------------
  // Archive tab: connections -> chats -> messages
  // ---------------------------------------------------------------------
  async function renderConnectionsList() {
    const panel = panels.archive;
    panel.innerHTML = '<p class="hint">Загрузка…</p>';
    try {
      const me = await api("/api/me");
      panel.innerHTML = "";
      if (me.connections.length === 0) {
        panel.appendChild(el('<p class="hint">Пока нет бизнес-подключений. Подключите бота в Настройках Telegram → Бизнес.</p>'));
        return;
      }
      const card = el('<div class="card"><h2>Подключения</h2></div>');
      for (const conn of me.connections) {
        const item = el(
          '<div class="list-item"><div class="title">' +
            conn.connection_id +
            "</div><div class=\"hint\">" +
            (conn.is_enabled ? "активно" : "отключено") +
            "</div></div>"
        );
        item.addEventListener("click", () => renderChatsList(conn.connection_id));
        card.appendChild(item);
      }
      panel.appendChild(card);
    } catch (err) {
      panel.innerHTML = '<p class="error">Не удалось загрузить подключения: ' + err.message + "</p>";
    }
  }

  async function renderChatsList(connectionId) {
    const panel = panels.archive;
    panel.innerHTML = '<p class="hint">Загрузка чатов…</p>';
    try {
      const chats = await api("/api/connections/" + encodeURIComponent(connectionId) + "/chats");
      panel.innerHTML = "";
      const back = el('<span class="breadcrumb">← Ко всем подключениям</span>');
      back.addEventListener("click", renderConnectionsList);
      panel.appendChild(back);

      if (chats.length === 0) {
        panel.appendChild(el('<p class="hint">В этом подключении пока нет архивных сообщений.</p>'));
        return;
      }

      const card = el('<div class="card"><h2>Чаты</h2></div>');
      for (const chat of chats) {
        const item = el(
          '<div class="list-item">' +
            '<div class="title">' + (chat.sender_name || chat.chat_id) + "</div>" +
            '<div class="hint">' + (chat.last_message_preview || "") + "</div>" +
            '<div class="hint">' + fmtDate(chat.last_sent_at) +
            (chat.edited_count ? '<span class="badge edited">✏️ ' + chat.edited_count + "</span>" : "") +
            (chat.deleted_count ? '<span class="badge deleted">🗑️ ' + chat.deleted_count + "</span>" : "") +
            "</div></div>"
        );
        item.addEventListener("click", () => renderMessages(connectionId, chat.chat_id));
        card.appendChild(item);
      }
      panel.appendChild(card);
    } catch (err) {
      panel.innerHTML = '<p class="error">Не удалось загрузить чаты: ' + err.message + "</p>";
    }
  }

  async function renderMessages(connectionId, chatId) {
    const panel = panels.archive;
    panel.innerHTML = '<p class="hint">Загрузка сообщений…</p>';
    try {
      const messages = await api(
        "/api/connections/" + encodeURIComponent(connectionId) + "/chats/" + chatId + "/messages?limit=100"
      );
      panel.innerHTML = "";
      const back = el('<span class="breadcrumb">← К списку чатов</span>');
      back.addEventListener("click", () => renderChatsList(connectionId));
      panel.appendChild(back);

      const thread = el('<div></div>');
      for (const msg of messages) {
        thread.appendChild(buildMessageCard(msg));
      }
      panel.appendChild(thread);
    } catch (err) {
      panel.innerHTML = '<p class="error">Не удалось загрузить сообщения: ' + err.message + "</p>";
    }
  }

  function buildMessageCard(msg) {
    const badges =
      (msg.is_edited ? '<span class="badge edited">изменено</span>' : "") +
      (msg.is_deleted ? '<span class="badge deleted">удалено</span>' : "");

    const card = el(
      '<div class="message">' +
        '<div class="meta">' + (msg.sender_name || "") + " · " + fmtDate(msg.sent_at) + badges + "</div>" +
        "<div>" + (msg.text || msg.caption || "<i>[" + msg.content_type + "]</i>") + "</div>" +
        "</div>"
    );

    if (msg.is_edited && msg.previous_text) {
      card.appendChild(el('<div class="diff"><b>Было:</b> ' + msg.previous_text + "</div>"));
    }

    if (msg.has_media) {
      const img = document.createElement("img");
      img.className = "media-preview";
      img.alt = msg.content_type;
      fetchMediaUrl(msg.id).then((url) => {
        if (url) img.src = url;
      });
      card.appendChild(img);
    }

    return card;
  }

  showTab("dashboard");
})();
