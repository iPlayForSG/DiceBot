let snapshot = null,
  busy = false,
  timer = null;
const $ = (id) => document.getElementById(id);
// 登录凭据由 HttpOnly Cookie 持有，页面只接收状态与脱敏后的模型结果。
async function request(path, body) {
  let response;
  try {
    response = await fetch(path, {
      method: body ? "POST" : "GET",
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error("控制台连接中断，请检查本机任务或刷新页面。");
  }
  const value = await response.json();
  if (!response.ok) {
    if (response.status === 401) showLogin();
    throw new Error(value.detail || "操作失败，请稍后重试。");
  }
  return value;
}
function showLogin() {
  clearInterval(timer);
  timer = null;
  $("workspace").hidden = true;
  $("login").hidden = false;
  setTimeout(() => $("password").focus(), 0);
}
function showWorkspace() {
  $("login").hidden = true;
  $("workspace").hidden = false;
  if (!timer) timer = setInterval(() => refresh(false), 6000);
}
function render(value) {
  snapshot = value;
  document.querySelectorAll("[data-mode]").forEach((b) => {
    b.classList.toggle("active", b.dataset.mode === value.mode);
    b.setAttribute("aria-pressed", String(b.dataset.mode === value.mode));
  });
  for (const name of ["tabletop", "ai"]) {
    const bot = value.bots[name],
      badge = $(name + "-status"),
      toggle = $(name + "-toggle");
    badge.textContent = bot.reachable
      ? bot.enabled
        ? "运行中"
        : "已关闭"
      : "连接异常";
    badge.className =
      "badge " + (!bot.reachable ? "pending" : bot.enabled ? "on" : "off");
    toggle.setAttribute("aria-checked", String(bot.enabled));
    toggle.setAttribute(
      "aria-label",
      (bot.enabled ? "关闭" : "启用") +
        (name === "ai" ? " AI Bot" : "桌游 Bot"),
    );
    $(name + "-error").hidden = !bot.error;
    $(name + "-error").textContent = bot.error || "";
  }
  $("napcat-dot").classList.toggle("on", value.napcat);
  $("napcat-state").textContent = value.napcat
    ? "NapCat 运行中"
    : "NapCat 未连接";
  $("proxy-status").textContent = value.proxy.ready ? "网关就绪" : "网关未就绪";
  $("proxy-status").className =
    "badge " + (value.proxy.ready ? "on" : "pending");
  $("proxy-model").textContent = value.proxy.model;
  $("proxy-base").textContent = value.proxy.base;
  const list = $("events");
  list.replaceChildren();
  for (const entry of value.events) {
    const li = document.createElement("li"),
      time = document.createElement("time"),
      message = document.createElement("span");
    time.textContent = entry.time;
    message.textContent = entry.message;
    li.append(time, message);
    list.append(li);
  }
  if (!value.events.length) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = "还没有切换记录。";
    list.append(li);
  }
  $("updated").textContent =
    "上次检查 " +
    new Date(value.checkedAt).toLocaleTimeString("zh-CN", { hour12: false });
}
async function refresh(manual = true) {
  if (busy) return;
  try {
    const value = await request("/api/status");
    showWorkspace();
    render(value);
    if (manual) {
      $("operation").className = "operation";
      $("operation").textContent = "已读取实际运行状态。";
    }
  } catch (error) {
    if (!$("workspace").hidden) {
      $("operation").className = "operation error";
      $("operation").textContent = error.message;
    }
  }
}
function disableControls(value) {
  document
    .querySelectorAll("[data-mode],.toggle,#refresh")
    .forEach((button) => (button.disabled = value));
}
async function changeMode(mode) {
  if (busy || !snapshot) return;
  busy = true;
  disableControls(true);
  $("operation").className = "operation";
  $("operation").textContent = "正在切换，请稍候…";
  try {
    render(await request("/api/mode", { mode }));
    $("operation").textContent = "切换已完成，网页牌局继续运行。";
  } catch (error) {
    $("operation").className = "operation error";
    $("operation").textContent = error.message;
  } finally {
    busy = false;
    disableControls(false);
  }
}
document
  .querySelectorAll("[data-mode]")
  .forEach((button) =>
    button.addEventListener("click", () => changeMode(button.dataset.mode)),
  );
for (const name of ["tabletop", "ai"])
  $(name + "-toggle").addEventListener("click", () => {
    if (!snapshot) return;
    const flags = {
      tabletop: snapshot.bots.tabletop.enabled,
      ai: snapshot.bots.ai.enabled,
    };
    flags[name] = !flags[name];
    changeMode(
      flags.tabletop
        ? flags.ai
          ? "both"
          : "tabletop"
        : flags.ai
          ? "ai"
          : "off",
    );
  });
$("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true;
  $("login-error").textContent = "";
  try {
    await request("/api/login", { password: $("password").value });
    $("password").value = "";
    await refresh();
  } catch (error) {
    $("login-error").textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
$("logout").addEventListener("click", async () => {
  await request("/api/logout", {});
  showLogin();
});
$("refresh").addEventListener("click", () => refresh());
document.querySelectorAll("[data-page]").forEach((button) =>
  button.addEventListener("click", () => {
    document
      .querySelectorAll("[data-page]")
      .forEach((item) => item.classList.toggle("active", item === button));
    $("control-page").hidden = button.dataset.page !== "control";
    $("proxy-page").hidden = button.dataset.page !== "proxy";
  }),
);
$("proxy-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("proxy-submit").disabled = true;
  $("proxy-submit").textContent = "等待模型回复…";
  $("proxy-result").hidden = false;
  $("result-meta").textContent = "正在发送测试请求";
  $("result-content").textContent = "";
  try {
    const value = await request("/api/proxy/test", {
      prompt: $("prompt").value,
    });
    $("result-meta").textContent =
      `${value.model} · ${value.elapsed} 秒${value.tokens ? ` · ${value.tokens} tokens` : ""}`;
    $("result-content").textContent = value.content || "模型未返回文本。";
  } catch (error) {
    $("result-meta").textContent = "未完成";
    $("result-content").textContent = error.message;
  } finally {
    $("proxy-submit").disabled = false;
    $("proxy-submit").textContent = "发送测试";
  }
});
refresh();
