"use strict";

// One authenticated seat lifecycle shared by every game renderer.
window.createRoomSession = function createRoomSession({api, code, initial, onView, onStatus = () => {}, onError = () => {}}) {
  const key = `dicebot:${code}`;
  let token = localStorage.getItem(key);
  let view = initial;
  let socket = null;
  let retry = null;
  let generation = 0;
  let disposed = false;

  function emit(next) {
    view = next;
    onView(next);
  }
  function detachSocket() {
    clearTimeout(retry);
    if (!socket) return;
    const previous = socket;
    socket = null;
    previous.onopen = previous.onmessage = previous.onclose = previous.onerror = null;
    previous.close();
  }
  function revoke(usedToken) {
    if (usedToken !== token) return;
    detachSocket();
    if (localStorage.getItem(key) === usedToken) localStorage.removeItem(key);
    token = null;
    generation += 1;
    emit({...view, me:null});
    onStatus("请重新输入身份码");
  }
  async function request(path, method = "GET", body = null) {
    const usedToken = token;
    let response;
    try {
      response = await fetch(`${api}${path}`, {method,
        headers:{"Content-Type":"application/json", ...(usedToken ? {Authorization:`Bearer ${usedToken}`} : {})},
        ...(body ? {body:JSON.stringify(body)} : {}), cache:"no-store"});
    } catch { throw new Error("无法连接实时服务，请稍后重试。"); }
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 401) revoke(usedToken);
      const error = new Error(typeof result.detail === "string" ? result.detail : "操作失败，请重试。");
      error.status = response.status;
      throw error;
    }
    return result;
  }
  async function refresh() {
    const started = generation;
    try {
      const next = await request(`/api/rooms/${code}${token ? "/me" : ""}`);
      if (!disposed && started === generation) emit(next);
    } catch (error) {
      if (error.status === 401) {
        const next = await request(`/api/rooms/${code}`);
        if (!disposed && !token) emit(next);
      } else throw error;
    }
  }
  function connect() {
    detachSocket();
    if (!token || disposed) return;
    const usedToken = token;
    const current = new WebSocket(`${api.replace(/^http/, "ws")}/ws/${code}`);
    socket = current;
    onStatus("连接中…");
    current.onopen = () => {
      if (socket !== current || token !== usedToken) return;
      current.send(usedToken);
      onStatus("● 实时在线");
    };
    current.onmessage = (event) => {
      if (socket !== current || token !== usedToken) return;
      emit(JSON.parse(event.data));
    };
    current.onclose = (event) => {
      if (socket !== current || token !== usedToken || disposed) return;
      socket = null;
      if (event.code === 1008) {
        const saved = localStorage.getItem(key);
        if (saved && saved !== usedToken) {
          token = saved;
          generation += 1;
          refresh().then(connect).catch(error => onError(error.message));
        } else {
          revoke(usedToken);
          onError("座位需要重新认领，请输入 Bot 私聊的身份码。");
        }
      } else if (event.code === 1001) {
        onStatus("房间已关闭");
        onError(event.reason || "房间已关闭，请在 QQ 群重新组局。");
      } else {
        onStatus("● 连接中断，正在重连");
        retry = setTimeout(() => {
          refresh().catch(error => onError(error.message)).finally(connect);
        }, 2500);
      }
    };
  }
  return {
    async start() {
      onStatus(token ? "恢复我的座位…" : "输入身份码查看自己的手牌");
      await refresh();
      connect();
    },
    async claim(claimCode) {
      generation += 1;
      detachSocket();
      const result = await request(`/api/rooms/${code}/claim`, "POST", {claim_code:claimCode});
      token = result.token;
      localStorage.setItem(key, token);
      await refresh();
      connect();
      return view;
    },
    async action(payload) {
      const next = await request(`/api/rooms/${code}/actions`, "POST", payload);
      emit(next);
      return next;
    },
    dispose() { disposed = true; generation += 1; detachSocket(); },
  };
};
