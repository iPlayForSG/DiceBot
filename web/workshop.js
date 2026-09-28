"use strict";

window.startWorkshopRoom = function startWorkshopRoom({api, code, initial, notify}) {
  const root = document.getElementById("workshop");
  const game = initial.game;
  const names = {"love-letter":"情书", "once-upon-a-time":"从前从前", "sushi-go":"寿司 Go！",
    "azul":"花砖物语", "flip-city":"翻转城市", "hanamikoji":"花见小路"};
  const colors = {w:"白",u:"蓝",g:"绿",r:"红",b:"黑"};
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"})[c]);
  const card = (c, controls = false, interrupt = false) => `<figure class="workshop-card"><img src="./${esc(c.image)}" alt="${esc(c.name)}" loading="lazy"><figcaption>${esc(c.name)}</figcaption>${controls || interrupt ? `<div class="workshop-card-actions">${game === "sushi-go" ? `<button data-action="pick" data-card="${c.id}">暗选</button>` : interrupt ? `<button data-action="interrupt" data-card="${c.id}">打断</button>` : `<button data-action="play" data-card="${c.id}">打出</button><button data-action="discard" data-card="${c.id}">弃掉</button><button data-action="pass" data-card="${c.id}">传牌</button>`}</div>` : ""}</figure>`;
  let view = initial;
  let token = localStorage.getItem(`dicebot:${code}`);
  let socket = null;

  async function request(path, method = "GET", body = null) {
    let response;
    try { response = await fetch(`${api}${path}`, {method, headers:{"Content-Type":"application/json", ...(token ? {Authorization:`Bearer ${token}`} : {})}, ...(body ? {body:JSON.stringify(body)} : {})}); }
    catch { throw new Error("无法连接实时服务。"); }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "操作失败。");
    return data;
  }
  async function send(action) {
    try { view = await request(`/api/rooms/${code}/actions`, "POST", action); render(); }
    catch (error) { notify(error.message); }
  }
  function connect() {
    if (!token) return;
    if (socket) socket.close();
    socket = new WebSocket(`${api.replace(/^http/,"ws")}/ws/${code}`);
    socket.onopen = () => socket.send(token);
    socket.onmessage = (event) => { view = JSON.parse(event.data); render(); };
    socket.onclose = (event) => {
      if (event.code === 1008) { token = null; localStorage.removeItem(`dicebot:${code}`); view.me = null; render(); }
      else if (token) setTimeout(connect, 2500);
    };
  }
  const tiles = (list) => list.map(c => `<span class="workshop-tile tile-${esc(c)}" title="${colors[c] || c}">${colors[c] || c}</span>`).join("");
  function render() {
    const me = view.me;
    const canAct = view.phase === "playing" && view.current === me?.id;
    const owner = me && view.players[0]?.id === me.id;
    const targets = view.players.filter(p => p.id !== me?.id);
    root.innerHTML = `<header class="workshop-header"><a href="./" class="workshop-back">← 游戏库</a><div><span class="eyebrow">${esc(code)} · 第 ${view.round} 轮</span><h1>${esc(names[game])}</h1></div><a class="workshop-rules" href="./public/rules/${game}.pdf" target="_blank" rel="noopener">阅读 PDF 规则书 ↗</a></header>
      <div class="workshop-note">这是一张与朋友共用的数字牌桌。牌堆与手牌由服务器保管；牌面效果、计分和胜负请依据规则书一起结算。</div>
      <div class="workshop-layout"><aside class="workshop-panel"><h2>玩家</h2>${view.players.map(p => `<div class="workshop-player"><strong>${esc(p.name)}</strong><span>${p.cards} 张手牌 · ${p.score} 分</span>${p.id === view.current ? `<small>当前行动</small>` : ""}</div>`).join("")}
      ${!me ? `<form data-action="claim" class="workshop-claim"><h3>认领座位</h3><p>输入 Bot 私聊的身份码。</p><input name="claim_code" maxlength="10" minlength="10" autocomplete="one-time-code" required><button class="primary-action">认领</button></form>` : `<p class="workshop-you">你的座位：${esc(view.players.find(p => p.id === me.id)?.name)}</p>`}
      <h2>最近动态</h2><ol class="workshop-log">${view.log.slice().reverse().map(x => `<li>${esc(x)}</li>`).join("")}</ol></aside>
      <section class="workshop-main">${view.phase === "lobby" ? `<section class="workshop-panel"><h2>等待开局</h2><p>在 QQ 群发送「/桌游 加入 ${esc(code)}」，房主随后发送「/桌游 开始」。未开始的房间 5 分钟后自动取消。</p></section>` : `
      <section class="workshop-panel workshop-controls"><h2>公共操作</h2><span>${game === "flip-city" ? "我的牌堆" : "牌堆"} ${view.deckCount} 张 · ${game === "flip-city" ? "我的弃牌" : "弃牌"} ${view.discardCount} 张</span>
      ${game !== "sushi-go" && game !== "azul" ? `<button data-action="draw" ${!canAct ? "disabled" : ""}>抽 1 张</button><button data-action="turn" ${!canAct ? "disabled" : ""}>结束回合</button>` : ""}
      ${me ? `<select id="workshop-target"><option value="">选择其他玩家</option>${targets.map(p => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join("")}</select><button data-action="score-plus">+1 分</button><button data-action="score-minus">−1 分</button>` : ""}
      ${game === "love-letter" && canAct ? `<button data-action="eliminate">使选中玩家出局</button>` : ""}
      ${game === "once-upon-a-time" && canAct ? `<button data-action="declare_win">以结局牌结束故事</button>` : ""}
      ${owner && ["sushi-go","love-letter","azul","hanamikoji"].includes(game) ? `<button data-action="next-round">开始下一轮</button>` : ""}</section>
      ${game === "azul" ? `<section class="workshop-panel"><h2>花砖工厂</h2><p>选择一处及一种颜色，拿取该处全部同色花砖；对照规则书在自己的图板上摆放、计分。</p><div class="workshop-factories">${view.factories.map((f,i)=> `<div><strong>工厂 ${i+1}</strong><div>${tiles(f)}</div>${[...new Set(f)].map(c=>`<button data-action="tile" data-source="${i}" data-color="${c}" ${!canAct?"disabled":""}>取${colors[c]}</button>`).join("")}</div>`).join("")}<div><strong>中央</strong><div>${tiles(view.center)}</div>${[...new Set(view.center)].map(c=>`<button data-action="tile" data-source="-1" data-color="${c}" ${!canAct?"disabled":""}>取${colors[c]}</button>`).join("")}</div></div><h3>我已取的花砖</h3><div>${tiles(view.myTiles)}</div><div class="workshop-controls"><select id="workshop-color"><option value="">选择颜色</option>${Object.entries(colors).map(([c,n])=>`<option value="${c}">${n}</option>`).join("")}</select><select id="workshop-row">${[1,2,3,4,5].map(n=>`<option value="${n-1}">第 ${n} 行</option>`).join("")}</select><button data-action="place_tile">放到图板</button><button data-action="resolve_pattern">完成整行</button></div><h3>我的图板</h3>${view.myPattern.map((r,i)=>`<p>第 ${i+1} 行：${tiles(r)} ${r.length}/${i+1}</p>`).join("")}<p>墙面：${tiles(view.myWall)}</p></section>` : ""}
      ${game === "sushi-go" ? `<section class="workshop-panel"><h2>同步选牌</h2><p>${view.picked ? "你已暗选，等待其他玩家。" : "从下方手牌选一张。所有玩家选好后会同时亮牌并传手牌。"} 已选 ${view.pickedCount}/${view.players.length} 人。</p></section>` : ""}
      ${game === "flip-city" ? `<section class="workshop-panel"><h2>公共供应</h2><p>购买或开发的费用请按牌面核对；本桌保管个人牌堆、弃牌堆和卡牌两面。</p><div class="workshop-cards">${view.market.map(({card:c,count})=>`<figure class="workshop-card"><img src="./${esc(c.image)}" alt="城市卡"><figcaption>剩余 ${count} 张</figcaption>${canAct?`<div class="workshop-card-actions"><button data-action="buy" data-card="${c.id}">购买</button>${c.alternate_image?`<button data-action="develop" data-card="${c.id}">开发</button>`:""}</div>`:""}</figure>`).join("")}</div><h3>我的弃牌堆</h3><div class="workshop-cards">${(me?.discard||[]).map(c=>`<figure class="workshop-card"><img src="./${esc(c.image)}" alt="弃牌"><figcaption>城市卡</figcaption>${canAct&&c.alternate_image?`<div class="workshop-card-actions"><button data-action="flip_card" data-card="${c.id}">翻面</button></div>`:""}</figure>`).join("")||"暂无弃牌"}</div></section>` : ""}
      <section class="workshop-panel"><h2>桌面上的牌</h2>${view.players.map(p=> `<div class="workshop-table-row"><h3>${esc(p.name)}</h3><div class="workshop-cards">${p.table.map(c=>card(c)).join("") || `<p>暂无公开的牌</p>`}</div></div>`).join("")}</section>
      ${me && game !== "flip-city" && game !== "azul" ? `<section class="workshop-panel"><h2>我的手牌 <small>仅你可见</small></h2><div class="workshop-cards">${me.hand.map(c=>card(c,!view.picked && view.phase === "playing" && (game === "sushi-go" || canAct), game === "once-upon-a-time" && !canAct && c.group !== "ending" && view.phase === "playing")).join("") || `<p>手中暂无卡牌</p>`}</div></section>` : ""}`}</section></div>`;
  }
  root.addEventListener("click", async event => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const kind = button.dataset.action;
    const target = root.querySelector("#workshop-target")?.value || "";
    if (["pass","eliminate"].includes(kind) && !target) return notify("请先选择其他玩家。");
    const action = {type:kind, card_id:button.dataset.card, target};
    if (kind === "score-plus" || kind === "score-minus") {action.type="score"; action.delta=kind === "score-plus" ? 1 : -1;}
    if (kind === "next-round") action.type="next_round";
    if (kind === "tile") {action.source=Number(button.dataset.source);action.color=button.dataset.color;}
    if (["place_tile","resolve_pattern"].includes(kind)) { action.color=root.querySelector("#workshop-color")?.value;action.row=Number(root.querySelector("#workshop-row")?.value); }
    await send(action);
  });
  root.addEventListener("submit", async event => {
    if (!event.target.matches('form[data-action="claim"]')) return;
    event.preventDefault();
    try { const data = await request(`/api/rooms/${code}/claim`, "POST", {claim_code:String(new FormData(event.target).get("claim_code")).trim().toUpperCase()});
      token=data.token; localStorage.setItem(`dicebot:${code}`,token); view=await request(`/api/rooms/${code}/me`); connect(); render(); }
    catch (error) { notify(error.message); }
  });
  if (token) request(`/api/rooms/${code}/me`).then(data=>{view=data;render();connect();}).catch(()=>render());
  else render();
};
