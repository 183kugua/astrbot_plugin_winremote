// pages/settings/app.js - 高级配置页前端逻辑
const $ = (s) => document.querySelector(s);

// 分组元数据
const GROUPS = [
  { key: "server", title: "① 服务端连接", desc: "WebSocket 服务端的监听地址与端口。强烈建议监听 127.0.0.1 并配合 SSH 隧道使用。" },
  { key: "auth", title: "② 认证与安全", desc: "Token 校验 + 二次密码 + 防暴力破解。" },
  { key: "admin", title: "③ 管理员与 Agent", desc: "哪些 QQ 号可以使用 /win 指令，以及 Agent 心跳与并发控制。" },
  { key: "commands", title: "④ 指令白/黑名单", desc: "控制哪些命令可以被执行。建议开启严格白名单模式。" },
  { key: "files", title: "⑤ 文件读写", desc: "限制 Agent 可读写的文件路径范围。" },
  { key: "output", title: "⑥ 输出与截图", desc: "控制命令输出截断、流式分块以及截图格式与质量。" },
  { key: "security_warnings", title: "⑧ 安全警告", desc: "请务必阅读以下安全自检提示。", readonly: true },
];

const FIELD_TYPES = {
  ws_host: "select", ws_port: "number", ws_path: "text",
  secret_token: "password", admin_password: "password",
  password_max_attempts: "number", password_ban_duration: "number",
  require_encryption: "checkbox",
  admin_qq: "array", allow_group: "checkbox",
  heartbeat_interval: "number", heartbeat_timeout: "number", max_agents: "number",
  allow_commands: "array", deny_commands: "array", deny_regex: "array",
  allow_powershell: "checkbox", strict_whitelist: "checkbox",
  file_whitelist_paths: "array", file_blacklist_keywords: "array",
  file_max_read_bytes: "number", file_allow_write: "checkbox",
  auto_screenshot: "checkbox",
  screenshot_format: "select", screenshot_quality: "number",
  max_output_bytes: "number", stream_chunk_size: "number",
  stream_interval_ms: "number", shell_timeout: "number",
};

const FIELD_OPTIONS = {
  ws_host: ["127.0.0.1", "0.0.0.0", "::1"],
  screenshot_format: ["JPEG", "PNG", "WebP"],
};

const FIELD_HINTS = {
  ws_host: "127.0.0.1=仅本机(推荐) | 0.0.0.0=所有网卡 | ::1=IPv6回环",
  ws_port: "1024-65535",
  secret_token: "至少8位，建议32位随机字符串",
  admin_password: "留空=不启用二次密码",
  admin_qq: "可触发 /win 指令的 QQ 号列表",
  allow_commands: "仅允许列表中的命令前缀",
  deny_commands: "无论白名单如何，命中即拒绝",
  file_whitelist_paths: "Agent 仅可访问这些目录",
  screenshot_quality: "1-100，越大越清晰体积越大",
};

let configData = {};

// 初始化
(async () => {
  try {
    const ctx = await window.AstrBotPluginPage.ready();
    applyTheme(ctx);
    window.AstrBotPluginPage.onContext((c) => applyTheme(c));
    await loadConfig();
  } catch (e) {
    console.error("[Settings] 初始化失败", e);
    showToast(`初始化失败: ${e.message}`, "error");
  }
})();

function applyTheme(c) {
  document.documentElement.setAttribute("data-theme", c?.isDark ? "dark" : "light");
}

async function loadConfig() {
  try {
    const res = await window.AstrBotPluginPage.apiGet("settings/load");
    configData = res || {};
    renderGroups();
    $("#statusText").textContent = "✅ 配置已加载";
    $("#statusText").style.color = "var(--success)";
  } catch (e) {
    $("#statusText").textContent = `⚠️ 加载失败: ${e.message}`;
    $("#statusText").style.color = "var(--danger)";
    renderGroups(); // 用默认值
  }
}

function renderGroups() {
  const container = $("#groups");
  container.innerHTML = GROUPS.map(g => {
    const fields = getGroupFields(g.key);
    const readonly = g.readonly ? "disabled" : "";
    return `
    <div class="group" id="grp-${g.key}">
      <div class="group-header" onclick="toggleGroup('${g.key}')">
        <span class="arrow">▼</span>
        <h2>${g.title}</h2>
      </div>
      <div class="group-desc">${g.desc}</div>
      <div class="group-body">
        ${fields.map(f => renderField(g.key, f, g.readonly)).join("")}
      </div>
    </div>`;
  }).join("");
  bindArrayEvents();
}

function getGroupFields(groupKey) {
  const map = {
    server: ["ws_host", "ws_port", "ws_path"],
    auth: ["secret_token", "admin_password", "password_max_attempts", "password_ban_duration", "require_encryption"],
    admin: ["admin_qq", "allow_group", "heartbeat_interval", "heartbeat_timeout", "max_agents"],
    commands: ["allow_commands", "deny_commands", "deny_regex", "allow_powershell", "strict_whitelist"],
    files: ["file_whitelist_paths", "file_blacklist_keywords", "file_max_read_bytes", "file_allow_write"],
    output: ["auto_screenshot", "screenshot_format", "screenshot_quality", "max_output_bytes", "stream_chunk_size", "stream_interval_ms", "shell_timeout"],
    security_warnings: ["_warn_ssh_tunnel", "_warn_short_token", "_warn_no_password", "_warn_require_encryption"],
  };
  return map[groupKey] || [];
}

function renderField(groupKey, fieldKey, readonly) {
  const type = FIELD_TYPES[fieldKey] || "text";
  const value = configData[fieldKey];
  const hint = FIELD_HINTS[fieldKey];
  const roAttr = readonly ? "disabled" : "";

  if (type === "checkbox") {
    const checked = value ? "checked" : "";
    return `<div class="field"><label><div class="toggle"><input type="checkbox" data-key="${fieldKey}" ${checked} ${roAttr}> ${fieldKey}</div></label>${hint ? `<div class="hint">${hint}</div>` : ""}</div>`;
  }
  if (type === "select") {
    const opts = FIELD_OPTIONS[fieldKey] || [];
    const optionsHtml = opts.map(o => `<option value="${o}" ${value === o ? "selected" : ""}>${o}</option>`).join("");
    return `<div class="field"><label>${fieldKey}</label><select data-key="${fieldKey}" ${roAttr}>${optionsHtml}</select>${hint ? `<div class="hint">${hint}</div>` : ""}</div>`;
  }
  if (type === "array") {
    const items = Array.isArray(value) ? value : [];
    const itemsHtml = items.map((v, i) => `<span class="array-item">${v} <span class="remove" onclick="removeArrayItem('${fieldKey}',${i})">×</span></span>`).join("");
    return `<div class="field"><label>${fieldKey}</label><div class="array-field"><div class="items" id="arr-${fieldKey}">${itemsHtml}</div><input type="text" id="arr-input-${fieldKey}" placeholder="添加新项..." ${roAttr}><button class="btn btn-primary" onclick="addArrayItem('${fieldKey}')">+</button></div>${hint ? `<div class="hint">${hint}</div>` : ""}</div>`;
  }
  if (type === "number") {
    return `<div class="field"><label>${fieldKey}</label><input type="number" data-key="${fieldKey}" value="${value || 0}" ${roAttr}>${hint ? `<div class="hint">${hint}</div>` : ""}</div>`;
  }
  const inputType = type === "password" ? "password" : "text";
  return `<div class="field"><label>${fieldKey}</label><input type="${inputType}" data-key="${fieldKey}" value="${(value || "").toString().replace(/"/g, '&quot;')}" ${roAttr}>${hint ? `<div class="hint">${hint}</div>` : ""}</div>`;
}

// 数组操作
window.addArrayItem = function (key) {
  const input = $(`#arr-input-${key}`);
  const val = input.value.trim();
  if (!val) return;
  if (!Array.isArray(configData[key])) configData[key] = [];
  configData[key].push(val);
  input.value = "";
  refreshArrayDisplay(key);
};
window.removeArrayItem = function (key, idx) {
  configData[key].splice(idx, 1);
  refreshArrayDisplay(key);
};
function refreshArrayDisplay(key) {
  const container = $(`#arr-${key}`);
  if (!container) return;
  container.innerHTML = (configData[key] || []).map((v, i) => `<span class="array-item">${v} <span class="remove" onclick="removeArrayItem('${key}',${i})">×</span></span>`).join("");
}

function bindArrayEvents() {
  document.querySelectorAll('[id^="arr-input-"]').forEach(input => {
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        const key = input.id.replace("arr-input-", "");
        window.addArrayItem(key);
      }
    });
  });
}

// 收集表单
function collectForm() {
  const form = {};
  document.querySelectorAll('input[type="checkbox"][data-key]').forEach(el => { form[el.dataset.key] = el.checked; });
  document.querySelectorAll('select[data-key]').forEach(el => { form[el.dataset.key] = el.value; });
  document.querySelectorAll('input[type="number"][data-key]').forEach(el => { form[el.dataset.key] = Number(el.value); });
  document.querySelectorAll('input[type="text"][data-key], input[type="password"][data-key]').forEach(el => { form[el.dataset.key] = el.value; });
  Object.keys(configData).forEach(key => {
    if (Array.isArray(configData[key])) form[key] = configData[key];
  });
  return form;
}

// 保存
window.saveConfig = async function () {
  const btn = $("#saveBtn");
  btn.disabled = true;
  btn.textContent = "💾 保存中...";
  try {
    const data = collectForm();
    const res = await window.AstrBotPluginPage.apiPost("settings/save", data);
    if (res.ok) {
      showToast("✅ 配置已保存", "success");
      configData = { ...configData, ...data };
    } else {
      showToast(`❌ 保存失败: ${res.msg}`, "error");
    }
  } catch (e) {
    showToast(`❌ 错误: ${e.message}`, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "💾 保存配置";
  }
};

// 测试连接
window.testConnection = async function () {
  const btn = $("#testBtn");
  const result = $("#testResult");
  btn.disabled = true;
  btn.textContent = "🔌 测试中...";
  result.className = "test-result info";
  result.textContent = "测试中...";
  result.style.display = "inline-block";
  try {
    const res = await window.AstrBotPluginPage.apiGet("settings/test");
    if (res.ok) {
      result.className = "test-result ok";
      result.textContent = `✅ 连接成功 | Agent: ${res.agent} | 延迟: ${res.latency_ms}ms`;
    } else {
      result.className = "test-result fail";
      result.textContent = `❌ ${res.msg}`;
    }
  } catch (e) {
    result.className = "test-result fail";
    result.textContent = `❌ ${e.message}`;
  } finally {
    btn.disabled = false;
    btn.textContent = "🔌 测试连接";
  }
};

// 分组折叠
window.toggleGroup = function (key) {
  const el = $(`#grp-${key}`);
  if (el) el.classList.toggle("collapsed");
};

// Toast
function showToast(msg, type) {
  const t = document.createElement("div");
  t.className = `toast ${type}`;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3000);
}
