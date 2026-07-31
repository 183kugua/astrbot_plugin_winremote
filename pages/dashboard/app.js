// pages/dashboard/app.js - WinRemote 远控面板前端逻辑
const $ = (s) => document.querySelector(s);
const grid = $("#agentsGrid");
const statsRow = $("#statsRow");
const lastUpdate = $("#lastUpdate");

// 时间格式化
function nowStr() { return new Date().toLocaleTimeString(); }

// 渲染 Agent 卡片
function render(agents) {
  lastUpdate.textContent = `最后更新: ${nowStr()}`;
  if (!agents.length) {
    grid.innerHTML = `<div class="empty-state"><div class="icon">😴</div><div>暂无在线 Agent</div></div>`;
    statsRow.innerHTML = "";
    return;
  }
  const online = agents.filter(a => a.online).length;
  const busy = agents.filter(a => a.busy).length;
  statsRow.innerHTML = `
    <div class="stat-card"><div class="stat-value" style="color:var(--success)">${online}</div><div class="stat-label">在线</div></div>
    <div class="stat-card"><div class="stat-value" style="color:var(--warn)">${busy}</div><div class="stat-label">忙碌</div></div>
    <div class="stat-card"><div class="stat-value">${agents.length}</div><div class="stat-label">总数</div></div>
  `;
  grid.innerHTML = agents.map(a => {
    const status = !a.online ? "offline" : a.busy ? "busy" : "online";
    const dotClass = `status-${status}`;
    const statusText = !a.online ? "离线" : a.busy ? "忙碌" : "在线";
    const colorVar = status === "online" ? "success" : status === "busy" ? "warn" : "muted";
    return `
    <div class="agent-card">
      <div class="agent-header">
        <div class="agent-name"><span class="status-dot ${dotClass}"></span>${a.id}</div>
        <div style="font-size:0.8rem;color:var(--muted)">心跳 ${a.heartbeat_age}s</div>
      </div>
      <div class="agent-info">
        <div class="info-item"><div class="info-label">状态</div><div class="info-value" style="color:var(--${colorVar})">${statusText}</div></div>
        <div class="info-item"><div class="info-label">心跳</div><div class="info-value">${a.heartbeat_age}s</div></div>
        ${a.info?.hostname ? `<div class="info-item"><div class="info-label">主机名</div><div class="info-value">${a.info.hostname}</div></div>` : ""}
        ${a.info?.username ? `<div class="info-item"><div class="info-label">用户</div><div class="info-value">${a.info.username}</div></div>` : ""}
      </div>
      ${a.task ? `<div class="task-bar"><span class="label">当前任务:</span>${a.task}</div>` : ""}
    </div>`;
  }).join("");
}

// 初始化
(async () => {
  try {
    const ctx = await window.AstrBotPluginPage.ready();
    // 主题
    const applyTheme = (c) => {
      document.documentElement.setAttribute("data-theme", c?.isDark ? "dark" : "light");
    };
    applyTheme(ctx);
    window.AstrBotPluginPage.onContext((c) => applyTheme(c));

    // SSE 订阅
    const sub = window.AstrBotPluginPage.subscribeSSE("agents", {
      onOpen: () => console.log("[Dashboard] SSE 已连接"),
      onMessage: (ev) => {
        try {
          const data = ev.parsed || JSON.parse(ev.raw);
          render(data);
        } catch (e) { console.warn("[Dashboard] 解析失败", e); }
      },
      onError: (err) => { console.error("[Dashboard] SSE 错误", err); },
    });
    window.addEventListener("beforeunload", () => sub.unsubscribe?.());
  } catch (e) {
    grid.innerHTML = `<div class="empty-state"><div class="icon">⚠️</div><div>SSE 连接失败: ${e.message}</div></div>`;
  }
})();
