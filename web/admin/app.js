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
  dashboardBrandName: document.querySelector("#dashboardBrandName"),
  brandDescription: document.querySelector("#brandDescription"),
  currentUser: document.querySelector("#currentUser"),
  userAvatar: document.querySelector("#userAvatar"),
  dashboardGreeting: document.querySelector("#dashboardGreeting"),
  statsGrid: document.querySelector("#statsGrid"),
  logoutButton: document.querySelector("#logoutButton"),
  refreshButton: document.querySelector("#refreshButton"),
  platformFilter: document.querySelector("#platformFilter"),
  typeFilter: document.querySelector("#typeFilter"),
  recordSearch: document.querySelector("#recordSearch"),
  recordsMessage: document.querySelector("#recordsMessage"),
  recordRows: document.querySelector("#recordRows"),
  previousPage: document.querySelector("#previousPage"),
  nextPage: document.querySelector("#nextPage"),
  pageStatus: document.querySelector("#pageStatus"),
};

let spatialModulePromise;
let records = [];
let currentPage = 1;
const pageSize = 50;

function addCssLiquidLayer(panel) {
  panel.classList.add("fzp-spatial-panel");
  if (panel.querySelector(":scope > .fzp-spatial-panel__glass")) return;
  const layer = document.createElement("div");
  layer.className = "fzp-liquid-target fzp-spatial-panel__glass";
  layer.setAttribute("aria-hidden", "true");
  panel.prepend(layer);
}

async function enhanceSpatialPanel(panel) {
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
    panel.dataset.fzpWebglReason = "design-system-unavailable";
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
  document.title = isAuthenticated ? `工作台 · ${elements.brandName.textContent}` : elements.brandName.textContent;
  void enhanceSpatialPanel(isAuthenticated ? elements.dashboardView : elements.loginView);
}

function setBusy(isBusy) {
  elements.submitButton.disabled = isBusy;
  elements.submitButton.querySelector(".fzp-button__label").textContent = isBusy ? "正在验证…" : "进入工作台";
}

function renderStats(stats) {
  elements.statsGrid.replaceChildren(
    ...stats.map((item) => {
      const card = document.createElement("article");
      card.className = "fzp-stat";
      card.dataset.tone = item.tone || "neutral";
      const label = document.createElement("span");
      label.className = "fzp-stat__label";
      label.textContent = item.label;
      const value = document.createElement("strong");
      value.className = "fzp-stat__value";
      value.textContent = item.value;
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

function fillFilter(select, values, label) {
  const current = select.value;
  const options = [new Option(label, "")];
  for (const value of [...new Set(values.filter(Boolean))].sort()) {
    options.push(new Option(value, value));
  }
  select.replaceChildren(...options);
  select.value = current;
}

function renderRecords() {
  const platform = elements.platformFilter.value;
  const type = elements.typeFilter.value;
  const query = elements.recordSearch.value.trim().toLowerCase();
  const filtered = records.filter((item) => {
    if (platform && item.platform !== platform) return false;
    if (type && item.type !== type) return false;
    if (!query) return true;
    return [item.title, item.ip, item.location, item.url, item.platform, item.type]
      .some((value) => String(value ?? "").toLowerCase().includes(query));
  });
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  currentPage = Math.min(currentPage, pageCount);
  const start = (currentPage - 1) * pageSize;
  const visible = filtered.slice(start, start + pageSize);
  elements.recordRows.replaceChildren(
    ...visible.map((item) => {
      const row = document.createElement("tr");
      appendCell(row, item.timestamp || (item.ts ? new Date(item.ts * 1000).toLocaleString() : ""));
      appendCell(row, item.platform);
      appendCell(row, item.type);
      appendCell(row, item.title, "fzp-title-cell");
      const ipCell = appendCell(row, item.ip);
      if (item.location) {
        const location = document.createElement("small");
        location.textContent = item.location;
        ipCell.append(document.createElement("br"), location);
      }
      const linkCell = document.createElement("td");
      const link = document.createElement("a");
      link.href = item.url || "#";
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = "打开";
      linkCell.append(link);
      row.append(linkCell);
      return row;
    }),
  );
  elements.recordsMessage.textContent = `匹配 ${filtered.length} 条，最近载入 ${records.length} 条`;
  elements.pageStatus.textContent = `第 ${currentPage} / ${pageCount} 页`;
  elements.previousPage.disabled = currentPage <= 1;
  elements.nextPage.disabled = currentPage >= pageCount;
}

async function loadRecords() {
  elements.refreshButton.disabled = true;
  elements.recordsMessage.textContent = "正在载入解析记录…";
  try {
    records = await api("/api/admin/records?limit=1000");
    fillFilter(elements.platformFilter, records.map((item) => item.platform), "全部平台");
    fillFilter(elements.typeFilter, records.map((item) => item.type), "全部类型");
    renderRecords();
  } catch (error) {
    if (error.status === 401) setView(false);
    elements.recordsMessage.textContent = error.message;
  } finally {
    elements.refreshButton.disabled = false;
  }
}

async function showDashboard(session) {
  elements.currentUser.textContent = session.username;
  elements.userAvatar.textContent = session.username.slice(0, 1).toUpperCase();
  setView(true);
  try {
    const overview = await api("/api/admin/overview");
    elements.dashboardGreeting.textContent = overview.greeting;
    renderStats(overview.stats);
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

elements.refreshButton.addEventListener("click", loadRecords);
for (const input of [elements.platformFilter, elements.typeFilter, elements.recordSearch]) {
  input.addEventListener(input === elements.recordSearch ? "input" : "change", () => {
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

async function boot() {
  try {
    const config = await api("/api/public/config");
    elements.brandName.textContent = config.appName;
    elements.dashboardBrandName.textContent = config.appName;
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
