"use strict";

window.startWorkshopRoom = async function startWorkshopRoom({api, code, initial, notify}) {
  const root = document.getElementById("workshop");
  const game = initial.game;
  const artwork = (await window.tabletopArtReady)[game];
  const names = {"love-letter":"情书", "once-upon-a-time":"从前从前", "sushi-go":"寿司 Go！",
    "azul":"花砖物语", "flip-city":"翻转城市", "hanamikoji":"花见小路"};
  const colors = {w:"白",u:"蓝",g:"黄",r:"红",b:"黑"};
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"})[c]);
  const card = (c, controls = false, interrupt = false) => `<figure class="workshop-card"><img src="./${esc(c.image)}" alt="${esc(c.name)}" loading="lazy" data-card-preview tabindex="0" role="button" title="点击查看大图"><figcaption>${esc(c.name)}</figcaption>${controls || interrupt ? `<div class="workshop-card-actions">${game === "sushi-go" ? `<button data-action="pick" data-card="${c.id}">暗选</button><label><input type="checkbox" data-sushi-choice value="${c.id}">筷子选牌</label>` : interrupt ? `<button data-action="interrupt" data-card="${c.id}">打断</button>` : `<button data-action="play" data-card="${c.id}">打出</button><button data-action="discard" data-card="${c.id}">弃掉</button><button data-action="pass" data-card="${c.id}">传牌</button>`}</div>` : ""}</figure>`;
  let view = initial;
  let connectionLabel = "恢复座位…";
  const session = window.createRoomSession({api, code, initial,
    onView:next => {view=next;render();},
    onStatus:message => {connectionLabel=message;const node=root.querySelector("[data-room-connection]");if(node)node.textContent=message;},
    onError:notify});
  async function send(action) {
    try { await session.action(action); }
    catch (error) { notify(error.message); }
  }
  const tiles = (list) => list.map(c => `<span class="workshop-tile tile-${esc(c)}" title="${colors[c] || c}"><img src="./${esc(artwork.tiles[c])}" alt="${colors[c]}色花砖" data-card-preview tabindex="0" role="button"><small>${colors[c]}</small></span>`).join("");
  function render() {
    const me = view.me;
    const canAct = view.phase === "playing" && view.current === me?.id;
    const owner = me && view.players[0]?.id === me.id;
    const myTable = view.players.find(p => p.id === me?.id)?.table || [];
    const targets = view.players.filter(p => p.id !== me?.id);
    const myself = view.players.find(p => p.id === me?.id);
    const privateContent = !me ? `<p>当前浏览器尚未认领身份。输入 Bot 私聊的身份码后，会显示你的手牌图片。</p>` : game === "azul" ? `<p>你取得、等待摆放的花砖</p><div>${tiles(view.myTiles)}</div>` : game === "flip-city" ? `<p>我的个人牌堆 ${myself.deckCount} 张 · 顶牌与本回合打出的牌</p><div class="workshop-cards">${myself.deckTop?card(myself.deckTop):""}${myself.table.map(c=>card(c)).join("")}</div>` : `<div class="workshop-cards">${me.hand.map(c=>card(c,!view.picked && view.phase === "playing" && (game === "sushi-go" || canAct), game === "once-upon-a-time" && !canAct && c.group !== "ending" && view.phase === "playing")).join("") || "<p>手中暂无卡牌</p>"}</div>`;
    const privatePanel = `<section class="workshop-panel private-hand-panel" data-private-hand><h2>${game === "azul" ? "我的花砖" : game === "flip-city" ? "我的个人牌区" : "我的手牌"} <small>${["azul","flip-city"].includes(game)?"自己的操作区":"仅自己可见"}</small></h2>${me?`<p>你的座位：${esc(me.name || myself?.name || "")}</p>`:""}${privateContent}</section>`;
    root.innerHTML = `<header class="workshop-header"><a href="./" class="workshop-back">← 游戏库</a><div><span class="eyebrow">${esc(code)} · 第 ${view.round} 轮</span><h1>${esc(names[game])}</h1></div><span data-room-connection>${esc(connectionLabel)}</span><a class="workshop-rules" href="./public/rules/${game}.pdf" target="_blank" rel="noopener">阅读 PDF 规则书 ↗</a></header>
      <div class="workshop-note">这是一张与朋友共用的数字牌桌。牌堆与手牌由服务器保管；牌面效果、计分和胜负请依据规则书一起结算。</div>
      <div class="workshop-layout"><aside class="workshop-panel"><h2>玩家</h2>${view.players.map(p => `<div class="workshop-player"><strong>${esc(p.name)}</strong><span>${p.cards} 张手牌 · ${p.score} 分${game === "sushi-go" ? ` · ${p.puddings} 张布丁` : ""}</span>${p.id === view.current ? `<small>当前行动</small>` : ""}</div>`).join("")}
      ${!me ? `<form data-action="claim" class="workshop-claim"><h3>认领座位</h3><p>输入 Bot 私聊的身份码。</p><input name="claim_code" maxlength="10" minlength="10" autocomplete="one-time-code" required><button class="primary-action">认领</button></form>` : `<p class="workshop-you">你的座位：${esc(view.players.find(p => p.id === me.id)?.name)}</p>`}
      <h2>最近动态</h2><ol class="workshop-log">${view.log.slice().reverse().map(x => `<li>${esc(x)}</li>`).join("")}</ol></aside>
      <section class="workshop-main">${view.phase === "lobby" ? `<section class="workshop-panel"><h2>等待开局</h2><p>在 QQ 群发送「/桌游 加入 ${esc(code)}」，房主随后发送「/桌游 开始」。未开始的房间 5 分钟后自动取消。</p></section>` : `
      ${privatePanel}<section class="workshop-panel workshop-controls"><h2>公共操作</h2><span>${game === "flip-city" ? "我的牌堆" : "牌堆"} ${view.deckCount} 张 · ${game === "flip-city" ? "我的弃牌" : "弃牌"} ${view.discardCount} 张</span>
      ${game !== "sushi-go" && game !== "azul" ? `<button data-action="draw" ${!canAct ? "disabled" : ""}>抽 1 张</button><button data-action="turn" ${!canAct ? "disabled" : ""}>结束回合</button>` : ""}
      ${me ? `<select id="workshop-target"><option value="">选择其他玩家</option>${targets.map(p => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join("")}</select><button data-action="score-plus">+1 分</button><button data-action="score-minus">−1 分</button>` : ""}
      ${game === "love-letter" && canAct ? `<button data-action="eliminate">使选中玩家出局</button>` : ""}
      ${game === "once-upon-a-time" && canAct ? `<button data-action="declare_win">以结局牌结束故事</button>` : ""}
      ${owner && ["sushi-go","love-letter","azul","hanamikoji"].includes(game) ? `<button data-action="next-round">开始下一轮</button>` : ""}</section>
      ${game === "azul" ? `<section class="workshop-panel"><h2>花砖工厂</h2><p>选择一处及一种颜色，拿取该处全部同色花砖；对照规则书在自己的图板上摆放、计分。</p><div class="workshop-factories">${view.factories.map((f,i)=> `<div><strong>工厂 ${i+1}</strong><div>${tiles(f)}</div>${[...new Set(f)].map(c=>`<button data-action="tile" data-source="${i}" data-color="${c}" ${!canAct?"disabled":""}>取${colors[c]}</button>`).join("")}</div>`).join("")}<div><strong>中央</strong><div>${tiles(view.center)}</div>${[...new Set(view.center)].map(c=>`<button data-action="tile" data-source="-1" data-color="${c}" ${!canAct?"disabled":""}>取${colors[c]}</button>`).join("")}</div></div><h3>我已取的花砖</h3><div>${tiles(view.myTiles)}</div><div class="workshop-controls"><select id="workshop-color"><option value="">选择颜色</option>${Object.entries(colors).map(([c,n])=>`<option value="${c}">${n}</option>`).join("")}</select><select id="workshop-row">${[1,2,3,4,5].map(n=>`<option value="${n-1}">第 ${n} 行</option>`).join("")}</select><button data-action="place_tile">放到图板</button><button data-action="resolve_pattern">完成整行</button></div><h3>我的图板</h3>${view.myPattern.map((r,i)=>`<p>第 ${i+1} 行：${tiles(r)} ${r.length}/${i+1}</p>`).join("")}<p>墙面：${tiles(view.myWall)}</p></section>` : ""}
      ${game === "sushi-go" ? `<section class="workshop-panel"><h2>同步选牌</h2><p>${view.picked ? "你已暗选，等待其他玩家。" : "从下方手牌选一张。所有玩家选好后会同时亮牌并传手牌。"} 已选 ${view.pickedCount}/${view.players.length} 人。</p>${me && !view.picked && myTable.some(c=>c.name === "筷子") && me.hand.length >= 2 ? `<p>已在先前回合打出筷子？勾选下方两张牌，再使用筷子。</p><button data-action="pick-two">使用筷子暗选两张</button>` : ""}</section>` : ""}
      ${game === "flip-city" ? `<section class="workshop-panel"><h2>公共供应</h2><p>购买或开发的费用请按牌面核对；本桌保管个人牌堆、弃牌堆和卡牌两面。</p><div class="workshop-cards">${view.market.map(({card:c,count})=>`<figure class="workshop-card"><img src="./${esc(c.image)}" alt="城市卡" data-card-preview tabindex="0" role="button"><figcaption>剩余 ${count} 张</figcaption>${canAct?`<div class="workshop-card-actions"><button data-action="buy" data-card="${c.id}">购买</button>${c.alternate_image?`<button data-action="develop" data-card="${c.id}">开发</button>`:""}</div>`:""}</figure>`).join("")}</div><h3>我的弃牌堆</h3><div class="workshop-cards">${(me?.discard||[]).map(c=>`<figure class="workshop-card"><img src="./${esc(c.image)}" alt="弃牌" data-card-preview tabindex="0" role="button"><figcaption>城市卡</figcaption>${canAct&&c.alternate_image?`<div class="workshop-card-actions"><button data-action="flip_card" data-card="${c.id}">翻面</button></div>`:""}</figure>`).join("")||"暂无弃牌"}</div></section>` : ""}
      <section class="workshop-panel" data-public-table><h2>${game === "azul" ? "玩家图板" : "桌面上的牌"}</h2>${view.players.map(p=> `<div class="workshop-table-row"><h3>${esc(p.name)}</h3>${game !== "azul" && game !== "flip-city" ? `<div class="workshop-cards hidden-hand-strip">${Array.from({length:p.cards},()=>`<figure class="workshop-back-card"><img src="./${esc(artwork.back)}" alt="未公开手牌"></figure>`).join("")}</div><p>${p.cards} 张手牌尚未公开</p>` : ""}${game === "azul" ? `<div class="workshop-public-board">${p.pattern.map((r,i)=>`<div><strong>第 ${i+1} 行</strong>${tiles(r)}<small>${r.length}/${i+1}</small></div>`).join("")}<p>墙面：${tiles(p.wall)}</p><p>待摆放：${tiles(p.tiles)}</p></div>` : `<div class="workshop-cards">${p.table.concat(p.puddingCards||[]).map(c=>card(c)).join("") || `<p>暂无公开的牌</p>`}${game === "flip-city" ? `<div class="workshop-personal-piles"><h4>个人牌堆 ${p.deckCount} 张 · 公开顶牌</h4>${p.deckTop?card(p.deckTop):""}<h4>个人弃牌</h4><div class="workshop-cards">${(p.discard||[]).map(c=>card(c)).join("")||"暂无弃牌"}</div></div>`:""}</div>`}</div>`).join("")}</section>
      ${view.discardCards.length ? `<section class="workshop-panel"><h2>公开弃牌</h2><div class="workshop-cards">${view.discardCards.map(c=>card(c)).join("")}</div></section>` : ""}
      ${game === "hanamikoji" ? `<section class="workshop-panel"><h2>七位艺者与公开献礼</h2><div class="geisha-table">${artwork.geishas.map(g=>{const name=g.name.split("※")[1].split("/")[0];return `<figure><img src="./${esc(g.image)}" alt="${esc(g.name)}" data-card-preview tabindex="0" role="button"><figcaption>${esc(g.name)}</figcaption>${view.players.map(p=>`<p>${esc(p.name)}：${p.table.filter(c=>c.name.endsWith("/"+name)).length} 件礼物</p>`).join("")}</figure>`;}).join("")}</div><h3>四种行动标记</h3><div class="workshop-cards">${Object.entries(artwork.actions).map(([name,image])=>`<figure class="workshop-card"><img src="./${esc(image)}" alt="${esc(name)}" data-card-preview tabindex="0" role="button"><figcaption>${esc(name)}</figcaption></figure>`).join("")}</div></section>` : ""}
      ${game === "azul" ? `<section class="workshop-panel"><h2>工坊图板</h2><img class="azul-board-art" src="./${esc(artwork.board)}" alt="花砖物语图板原图" data-card-preview tabindex="0" role="button"><p>上方玩家图板显示每位玩家当前的图案线、已砌墙砖和待摆放花砖。</p></section>` : ""}
      ${(view.removedCards||[]).length ? `<section class="workshop-panel"><h2>开局公开移出的牌</h2><div class="workshop-cards">${view.removedCards.map(c=>card(c)).join("")}</div></section>` : ""}
      `}</section></div>`;
  }
  root.addEventListener("click", async event => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const kind = button.dataset.action;
    if (kind === "pick-two") {
      const cards = [...root.querySelectorAll("[data-sushi-choice]:checked")].map(input => input.value);
      if (cards.length !== 2) return notify("请勾选两张不同的手牌。");
      await send({type:"pick_two",cards});
      return;
    }
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
    try { await session.claim(String(new FormData(event.target).get("claim_code")).trim().toUpperCase()); }
    catch (error) { notify(error.message); }
  });
  await session.start();
};
