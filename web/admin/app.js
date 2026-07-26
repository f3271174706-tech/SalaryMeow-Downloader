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
  detailDateFilter: document.querySelector("#detailDateFilter"),
  recordSearch: document.querySelector("#recordSearch"),
  summaryDateFilter: document.querySelector("#summaryDateFilter"),
  summaryIpFilter: document.querySelector("#summaryIpFilter"),
  mobileOverviewButton: document.querySelector("#mobileOverviewButton"),
  recordsMessage: document.querySelector("#recordsMessage"),
  recordRows: document.querySelector("#recordRows"),
  previousPage: document.querySelector("#previousPage"),
  nextPage: document.querySelector("#nextPage"),
  pageStatus: document.querySelector("#pageStatus"),
};

let spatialModulePromise;
let records = [];
let refreshTimer;
let currentPage = 1;

function loadScript(source) {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${source}"]`);
    if (existing) {
      if (existing.dataset.loaded === "true") resolve();
      else existing.addEventListener("load", resolve, { once: true });
      return;
    }
    const script = document.createElement("script");
    script.src = source;
    script.addEventListener("load", () => {
      script.dataset.loaded = "true";
      resolve();
    }, { once: true });
    script.addEventListener("error", reject, { once: true });
    document.head.append(script);
  });
}

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
  const desktopEffects = window.matchMedia(
    "(min-width: 769px) and (prefers-reduced-motion: no-preference)",
  ).matches;
  if (!desktopEffects) {
    addCssLiquidLayer(panel);
    panel.dataset.fzpWebgl = "fallback";
    panel.dataset.fzpWebglReason = "mobile-performance-policy";
    return;
  }
  try {
    await Promise.all([
      loadScript("/admin-assets/design-system/spatial-liquid/vendor/html2canvas.min.js"),
      loadScript("/admin-assets/design-system/spatial-liquid/vendor/liquidGL.js"),
    ]);
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
    await Promise.all([
      spatial.ready,
      import("/admin-assets/specular-button.js"),
    ]);
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

function appendCell(row, value, className = "", label = "") {
  const cell = document.createElement("td");
  if (className) cell.className = className;
  if (label) cell.dataset.label = label;
  cell.textContent = String(value ?? "");
  row.append(cell);
  return cell;
}

function displayTime(item) {
  const value = item.timestamp || (item.ts ? new Date(item.ts * 1000).toLocaleString() : "");
  const match = String(value).match(/\d{4}[/-](\d{1,2})[/-](\d{1,2})\s+(\d{1,2}):(\d{2})/);
  return match
    ? `${match[1].padStart(2, "0")}/${match[2].padStart(2, "0")} ${match[3].padStart(2, "0")}:${match[4]}`
    : value;
}

function recordDate(item) {
  const value = String(item.timestamp || "");
  const match = value.match(/^(\d{4})[/-](\d{1,2})[/-](\d{1,2})/);
  if (match) {
    return `${match[1]}-${match[2].padStart(2, "0")}-${match[3].padStart(2, "0")}`;
  }
  if (!item.ts) return "";
  return new Date((Number(item.ts) + 8 * 3600) * 1000).toISOString().slice(0, 10);
}

function populateFilterPresets() {
  const dates = [...new Set(records.map(recordDate).filter(Boolean))].sort().reverse();
  for (const select of [elements.detailDateFilter, elements.summaryDateFilter]) {
    const currentDate = select.value;
    select.replaceChildren(
      new Option("全部日期", ""),
      ...dates.map((date) => new Option(date, date)),
    );
    if (dates.includes(currentDate)) select.value = currentDate;
  }

  const currentIp = elements.summaryIpFilter.value;
  const ipLabels = new Map();
  for (const item of records) {
    if (!item.ip) continue;
    const label = item.location ? `${item.ip} · ${item.location}` : item.ip;
    if (!ipLabels.has(item.ip) || item.location) ipLabels.set(item.ip, label);
  }
  const ips = [...ipLabels.entries()].sort(([left], [right]) => left.localeCompare(right));
  elements.summaryIpFilter.replaceChildren(
    new Option("全部 IP / 地址", ""),
    ...ips.map(([ip, label]) => new Option(label, ip)),
  );
  if (ipLabels.has(currentIp)) elements.summaryIpFilter.value = currentIp;
}

function renderRecords() {
  const summaryMode = elements.dashboardView.classList.contains("legacy-admin--summary");
  const platform = summaryMode ? "" : elements.platformFilter.value;
  const type = summaryMode ? "" : elements.typeFilter.value;
  const query = summaryMode ? "" : elements.recordSearch.value.trim().toLowerCase();
  const selectedDate = summaryMode ? elements.summaryDateFilter.value : elements.detailDateFilter.value;
  const selectedIp = summaryMode ? elements.summaryIpFilter.value : "";
  const filtered = records.filter((item) => {
    if (platform && item.platform !== platform) return false;
    if (type && item.type !== type) return false;
    if (query && !String(item.title ?? "").toLowerCase().includes(query)) return false;
    if (selectedDate && recordDate(item) !== selectedDate) return false;
    if (selectedIp && item.ip !== selectedIp) return false;
    return true;
  });
  if (!filtered.length) {
    const row = document.createElement("tr");
    const cell = appendCell(row, "暂无记录", "legacy-empty");
    cell.colSpan = 6;
    elements.recordRows.replaceChildren(row);
    elements.recordsMessage.textContent = "";
    elements.pageStatus.textContent = "第 1 / 1 页";
    elements.previousPage.disabled = true;
    elements.nextPage.disabled = true;
    return;
  }
  const pageSize = window.matchMedia("(max-width: 768px)").matches ? 20 : 50;
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  currentPage = Math.min(Math.max(1, currentPage), pageCount);
  const start = (currentPage - 1) * pageSize;
  const visible = filtered.slice(start, start + pageSize);
  elements.recordRows.replaceChildren(
    ...visible.map((item) => {
      const row = document.createElement("tr");
      appendCell(row, displayTime(item), "legacy-time", "时间");
      const ipCell = appendCell(row, item.ip || "-", "legacy-ip", "IP / 地址");
      if (item.location) {
        const location = document.createElement("small");
        location.className = "legacy-location";
        location.textContent = item.location;
        ipCell.append(document.createElement("br"), location);
      }
      const platformCell = document.createElement("td");
      platformCell.dataset.label = "平台";
      const platformBadge = document.createElement("span");
      platformBadge.className = `legacy-platform legacy-platform--${item.platform || "unknown"}`;
      platformBadge.textContent = item.platform || "-";
      platformCell.append(platformBadge);
      row.append(platformCell);
      const typeCell = document.createElement("td");
      typeCell.dataset.label = "类型";
      const typeBadge = document.createElement("span");
      typeBadge.className = "legacy-type";
      typeBadge.textContent = { video: "视频", photo: "图片", live_photo: "动图" }[item.type] || item.type || "-";
      typeCell.append(typeBadge);
      row.append(typeCell);
      const titleCell = appendCell(row, item.title || "-", "legacy-title", "标题");
      titleCell.title = item.title || "";
      const linkCell = document.createElement("td");
      linkCell.dataset.label = "链接";
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
  elements.pageStatus.textContent = `第 ${currentPage} / ${pageCount} 页`;
  elements.previousPage.disabled = currentPage <= 1;
  elements.nextPage.disabled = currentPage >= pageCount;
}

async function loadRecords() {
  try {
    records = await api("/api/admin/records?limit=1000");
    populateFilterPresets();
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
    elements.dashboardView.classList.remove("legacy-admin--summary");
    elements.mobileOverviewButton.setAttribute("aria-pressed", "false");
    elements.mobileOverviewButton.textContent = "总览";
    elements.summaryDateFilter.value = "";
    elements.summaryIpFilter.value = "";
    records = [];
    elements.password.value = "";
    elements.logoutButton.disabled = false;
    elements.username.focus();
  }
});

for (const input of [
  elements.platformFilter,
  elements.typeFilter,
  elements.detailDateFilter,
  elements.recordSearch,
]) {
  input.addEventListener(input === elements.recordSearch ? "input" : "change", () => {
    currentPage = 1;
    renderRecords();
  });
}
for (const input of [elements.summaryDateFilter, elements.summaryIpFilter]) {
  input.addEventListener("change", () => {
    currentPage = 1;
    renderRecords();
  });
}
elements.previousPage.addEventListener("click", () => {
  currentPage -= 1;
  renderRecords();
});
elements.nextPage.addEventListener("click", () => {
  currentPage += 1;
  renderRecords();
});
elements.mobileOverviewButton.addEventListener("click", () => {
  const enabled = elements.dashboardView.classList.toggle("legacy-admin--summary");
  elements.mobileOverviewButton.setAttribute("aria-pressed", String(enabled));
  elements.mobileOverviewButton.textContent = enabled ? "详细" : "总览";
  currentPage = 1;
  renderRecords();
  if (enabled) elements.summaryDateFilter.focus();
});
window.matchMedia("(max-width: 768px)").addEventListener("change", () => {
  if (!window.matchMedia("(max-width: 768px)").matches) {
    elements.dashboardView.classList.remove("legacy-admin--summary");
    elements.mobileOverviewButton.setAttribute("aria-pressed", "false");
    elements.mobileOverviewButton.textContent = "总览";
  }
  currentPage = 1;
  renderRecords();
});

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
