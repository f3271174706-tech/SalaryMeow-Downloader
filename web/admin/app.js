"use strict";

const elements = {
  loginView: document.querySelector("#loginView"),
  dashboardView: document.querySelector("#dashboardView"),
  loginForm: document.querySelector("#loginForm"),
  username: document.querySelector("#username"),
  password: document.querySelector("#password"),
  togglePassword: document.querySelector("#togglePassword"),
  submitButton: document.querySelector("#submitButton"),
  formMessage: document.querySelector("#formMessage"),
  brandName: document.querySelector("#brandName"),
  brandDescription: document.querySelector("#brandDescription"),
  statsGrid: document.querySelector("#statsGrid"),
  logoutButton: document.querySelector("#logoutButton"),
  platformFilter: document.querySelector("#platformFilter"),
  typeFilter: document.querySelector("#typeFilter"),
  recordSearch: document.querySelector("#recordSearch"),
  recordsMessage: document.querySelector("#recordsMessage"),
  recordRows: document.querySelector("#recordRows"),
};

let spatialModulePromise;
let records = [];
let refreshTimer;

function addCssLiquidLayer(panel) {
  panel.classList.add("fzp-spatial-panel");
  if (panel.querySelector(":scope > .fzp-spatial-panel__glass")) return;
  const layer = document.createElement("div");
  layer.className = "fzp-liquid-target fzp-spatial-panel__glass";
  layer.setAttribute("aria-hidden", "true");
  panel.prepend(layer);
}

async function enhanceLogin() {
  const panel = elements.loginView;
  if (!panel || panel.dataset.fzpSpatialReady === "true") return;
  panel.dataset.fzpSpatialReady = "true";
  try {
    spatialModulePromise ||= import("/admin-assets/design-system/spatial-liquid/spatial-liquid.js");
    const { initSpatialLiquid } = await spatialModulePromise;
    const spatial = initSpatialLiquid({
      root: panel,
      timeout: 15000,
      snapshot: ".fzp-spatial-background",
      resolution: 2,
      refraction: 0.01,
      bevelDepth: 0.35,
      bevelWidth: 0.211,
      frost: 0.1,
      shadow: true,
      specular: true,
      tilt: true,
      tiltFactor: 2,
      reveal: "fade",
    });
    await spatial.ready;
  } catch {
    addCssLiquidLayer(panel);
    panel.dataset.fzpWebgl = "fallback";
  }
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (response.status === 204) return null;
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload.detail || "请求失败，请稍后重试。");
    error.status = response.status;
    throw error;
  }
  return payload;
}

function setView(isAuthenticated) {
  elements.loginView.hidden = isAuthenticated;
  elements.dashboardView.hidden = !isAuthenticated;
  document.body.classList.toggle("is-admin", isAuthenticated);
  document.title = isAuthenticated ? "后台管理 - 解析记录" : elements.brandName.textContent;
  if (isAuthenticated) {
    window.clearInterval(refreshTimer);
    refreshTimer = window.setInterval(loadRecords, 30000);
  } else {
    window.clearInterval(refreshTimer);
    void enhanceLogin();
  }
}

function setBusy(isBusy) {
  elements.submitButton.disabled = isBusy;
  elements.submitButton.querySelector(".fzp-button__label").textContent = isBusy ? "正在验证…" : "进入工作台";
}

function renderStats() {
  const counts = records.reduce((result, item) => {
    result[item.platform] = (result[item.platform] || 0) + 1;
    return result;
  }, {});
  const stats = [
    ["总解析", records.length],
    ["抖音", counts.douyin || 0],
    ["TikTok", counts.tiktok || 0],
    ["Twitter", counts.twitter || 0],
    ["B站", counts.bilibili || 0],
    ["快手", counts.kuaishou || 0],
  ];
  elements.statsGrid.replaceChildren(
    ...stats.map(([labelText, valueText]) => {
      const card = document.createElement("article");
      card.className = "legacy-stat-card";
      const label = document.createElement("span");
      label.className = "legacy-stat-card__label";
      label.textContent = labelText;
      const value = document.createElement("strong");
      value.className = "legacy-stat-card__value";
      value.textContent = valueText;
      card.append(label, value);
      return card;
    }),
  );
}

function appendCell(row, value, className = "") {
  const cell = document.createElement("td");
  if (className) cell.className = className;
  cell.textContent = String(value ?? "");
  row.append(cell);
  return cell;
}

function displayTime(item) {
  const value = item.timestamp || (item.ts ? new Date(item.ts * 1000).toLocaleString() : "");
  const match = String(value).match(/\d{4}-(\d{2})-(\d{2}) (\d{2}):(\d{2})/);
  return match ? `${match[1]}/${match[2]} ${match[3]}:${match[4]}` : value;
}

function renderRecords() {
  const platform = elements.platformFilter.value;
  const type = elements.typeFilter.value;
  const query = elements.recordSearch.value.trim().toLowerCase();
  const filtered = records.filter((item) => {
    if (platform && item.platform !== platform) return false;
    if (type && item.type !== type) return false;
    if (!query) return true;
    return String(item.title ?? "").toLowerCase().includes(query);
  });
  if (!filtered.length) {
    const row = document.createElement("tr");
    const cell = appendCell(row, "暂无记录", "legacy-empty");
    cell.colSpan = 6;
    elements.recordRows.replaceChildren(row);
    elements.recordsMessage.textContent = "";
    return;
  }
  elements.recordRows.replaceChildren(
    ...filtered.map((item) => {
      const row = document.createElement("tr");
      appendCell(row, displayTime(item), "legacy-time");
      const ipCell = appendCell(row, item.ip || "-", "legacy-ip");
      if (item.location) {
        const location = document.createElement("small");
        location.className = "legacy-location";
        location.textContent = item.location;
        ipCell.append(document.createElement("br"), location);
      }
      const platformCell = document.createElement("td");
      const platformBadge = document.createElement("span");
      platformBadge.className = `legacy-platform legacy-platform--${item.platform || "unknown"}`;
      platformBadge.textContent = item.platform || "-";
      platformCell.append(platformBadge);
      row.append(platformCell);
      const typeCell = document.createElement("td");
      const typeBadge = document.createElement("span");
      typeBadge.className = "legacy-type";
      typeBadge.textContent = { video: "视频", photo: "图片", live_photo: "动图" }[item.type] || item.type || "-";
      typeCell.append(typeBadge);
      row.append(typeCell);
      const titleCell = appendCell(row, item.title || "-", "legacy-title");
      titleCell.title = item.title || "";
      const linkCell = document.createElement("td");
      const copyButton = document.createElement("button");
      copyButton.className = "legacy-copy";
      copyButton.type = "button";
      copyButton.textContent = "复制";
      copyButton.disabled = !item.url;
      copyButton.addEventListener("click", async () => {
        await navigator.clipboard.writeText(item.url);
        copyButton.textContent = "已复制";
        window.setTimeout(() => {
          copyButton.textContent = "复制";
        }, 2000);
      });
      linkCell.append(copyButton);
      row.append(linkCell);
      return row;
    }),
  );
  elements.recordsMessage.textContent = filtered.length === records.length ? "" : `匹配 ${filtered.length} 条记录`;
}

async function loadRecords() {
  try {
    records = await api("/api/admin/records?limit=1000");
    renderStats();
    renderRecords();
  } catch (error) {
    if (error.status === 401) setView(false);
    else elements.recordsMessage.textContent = `加载失败：${error.message}`;
  }
}

async function showDashboard() {
  setView(true);
  try {
    await loadRecords();
  } catch (error) {
    if (error.status === 401) setView(false);
  }
}

elements.loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  elements.formMessage.textContent = "";
  if (!elements.loginForm.reportValidity()) return;
  setBusy(true);
  try {
    const session = await api("/api/admin/login", {
      method: "POST",
      body: JSON.stringify({
        username: elements.username.value.trim(),
        password: elements.password.value,
      }),
    });
    elements.password.value = "";
    await showDashboard(session);
  } catch (error) {
    const messages = {
      401: "用户名或密码不正确。",
      429: "尝试次数过多，请稍后再试。",
      503: "管理入口尚未配置，请联系部署者。",
    };
    elements.formMessage.textContent = messages[error.status] || error.message;
    elements.password.focus();
    elements.password.select();
  } finally {
    setBusy(false);
  }
});

elements.togglePassword.addEventListener("click", () => {
  const isPassword = elements.password.type === "password";
  elements.password.type = isPassword ? "text" : "password";
  elements.togglePassword.setAttribute("aria-label", isPassword ? "隐藏密码" : "显示密码");
  elements.password.focus();
});

elements.logoutButton.addEventListener("click", async () => {
  elements.logoutButton.disabled = true;
  try {
    await api("/api/admin/logout", { method: "POST" });
  } finally {
    setView(false);
    elements.statsGrid.replaceChildren();
    elements.recordRows.replaceChildren();
    records = [];
    elements.password.value = "";
    elements.logoutButton.disabled = false;
    elements.username.focus();
  }
});

for (const input of [elements.platformFilter, elements.typeFilter, elements.recordSearch]) {
  input.addEventListener(input === elements.recordSearch ? "input" : "change", renderRecords);
}

async function boot() {
  try {
    const config = await api("/api/public/config");
    elements.brandName.textContent = config.appName;
    elements.brandDescription.textContent = config.appDescription;
    document.title = config.appName;
    if (!config.adminEnabled) {
      elements.formMessage.textContent = "管理入口尚未配置。";
    }
  } catch {
    elements.formMessage.textContent = "服务暂时不可用，请稍后重试。";
  }

  try {
    await showDashboard(await api("/api/admin/session"));
  } catch {
    setView(false);
    elements.username.focus();
  }
}

boot();
