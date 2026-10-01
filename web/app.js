const API = (window.TABLETOP_API_URL || "http://127.0.0.1:8765").replace(/\/$/, "");
const params = new URLSearchParams(location.search);
const code = (params.get("room") || "").trim().toUpperCase();
const $ = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"})[c]);
const asset = (file) => `./public/assets/exploding-kittens/${file}`;
const labels = {bomb:"炸弹猫咪",defuse:"拆弹",attack:"攻击",skip:"跳过",shuffle:"洗牌",see:"预知",favor:"帮帮忙",nope:"不行",cat:"猫牌",pair:"两张组合",triple:"三张组合",five:"五张组合"};
const catNames = {4:"西瓜猫",5:"饼猫饼",6:"土豆猫",7:"胡子猫",8:"彩虹猫"};
const signature = (id) => cards[id].kind === "cat" ? `cat:${cards[id].face}` : cards[id].kind;
const signatureLabel = (value) => value.startsWith("cat:") ? catNames[Number(value.slice(4))] : labels[value];
let manifest = null;
let cards = {};
let state = null;
let kittenSession = null;
let selected = [];
let toastTimer = null;

function notify(message) {
  const element = $("toast");
  element.textContent = message;
  element.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => element.hidden = true, 4000);
}

async function request(path, options = {}) {
  const headers = {"Content-Type":"application/json", ...(options.headers || {})};
  let response;
  try { response = await fetch(`${API}${path}`, {...options, headers}); }
  catch { throw new Error("无法连接实时服务，请稍后重试。"); }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(typeof body.detail === "string" ? body.detail : "操作失败，请稍后重试。");
  }
  return body;
}

function avatar(player, size = "normal") {
  const initial = escapeHtml(player.name?.charAt(0) || "猫");
  return player.avatar
    ? `<img class="avatar ${size}" src="${API}/api/avatars/${encodeURIComponent(player.id)}" alt="${escapeHtml(player.name)} 的 QQ 头像">`
    : `<span class="avatar ${size}" aria-label="${escapeHtml(player.name)} 的头像">${initial}</span>`;
}

function renderPlayers() {
  $("player-count").textContent = `${state.players.length}/5`;
  $("players").innerHTML = state.players.map((player) => `
    <div class="player ${state.current === player.id ? "current" : ""} ${player.alive ? "" : "dead"}">
      ${avatar(player)}<div class="player-meta"><strong>${escapeHtml(player.name)}</strong>
      <small>${!player.alive ? "已出局" : state.current === player.id ? (state.me?.id === player.id ? "轮到我" : "正在行动") : `${player.cards} 张手牌`}</small></div>
    </div>`).join("");
  const eligible = state.players.filter((player) => player.alive && player.id !== state.me?.id);
  const oldTarget = $("target").value;
  $("target").innerHTML = `<option value="">选择玩家</option>${eligible.map((player) => `<option value="${escapeHtml(player.id)}">${escapeHtml(player.name)}</option>`).join("")}`;
  if (eligible.some((player) => player.id === oldTarget)) $("target").value = oldTarget;
}

function renderClaim() {
  $("claim-panel").hidden = Boolean(state.me);
}

function renderHand() {
  const hand = state.me?.hand || [];
  selected = selected.filter((id) => hand.includes(id));
  $("hand-area").hidden = !state.me;
  $("hand-hint").textContent = !hand.length ? "暂无手牌" : `共 ${hand.length} 张 · 点击选择`;
  $("zoom-card").hidden = selected.length === 0;
  $("hand").innerHTML = hand.map((id) => {
    const card = cards[id];
    return `<button type="button" class="hand-card ${selected.includes(id) ? "selected" : ""}" data-id="${id}" title="${labels[card.kind]}">
      <img src="${asset(card.image)}" alt="${labels[card.kind]}"></button>`;
  }).join("");
  $("hand").querySelectorAll("button").forEach((button) => button.addEventListener("click", () => {
    const id = button.dataset.id;
    if (selected.includes(id)) selected = selected.filter((value) => value !== id);
    else if (selected.length === 0) selected = [id];
    else if (state.mode === "advanced" && selected.length < 5) selected.push(id);
    else if (state.mode !== "advanced" && selected.length === 1 && cards[id].kind === "cat" && cards[selected[0]].kind === "cat") selected.push(id);
    else selected = [id];
    renderHand();
    renderActions();
  }));
  $("hand").querySelectorAll("button").forEach((button) => button.addEventListener("dblclick", () => showCard(button.dataset.id)));
}

function showCard(id) {
  const card = cards[id];
  if (!card) return;
  $("card-title").textContent = labels[card.kind];
  $("card-full").src = asset(card.image);
  $("card-full").alt = `${labels[card.kind]}卡牌大图`;
  $("card-dialog").showModal();
}

function renderCombo() {
  const combo = selected.length > 1;
  const count = selected.length;
  $("combo-panel").hidden = !combo || state.mode !== "advanced";
  $("declared-row").hidden = count !== 3;
  $("retrieve-row").hidden = count !== 5;
  if (count === 3) {
    const old = $("declared").value;
    const unique = [...new Set(manifest.cards.filter((card) => card.kind !== "bomb").map((card) => signature(card.id)))];
    $("declared").innerHTML = `<option value="">选择牌名</option>${unique.map((name) => `<option value="${name}">${signatureLabel(name)}</option>`).join("")}`;
    if (unique.includes(old)) $("declared").value = old;
  }
  if (count === 5) {
    const old = $("retrieve").value;
    $("retrieve").innerHTML = `<option value="">选择弃牌</option>${state.discardCards.map((id, index) => `<option value="${id}">${labels[cards[id].kind]} · 第 ${index + 1} 张</option>`).join("")}`;
    if (state.discardCards.includes(old)) $("retrieve").value = old;
    const preview = cards[$("retrieve").value];
    $("retrieve-preview").hidden = !preview;
    if (preview) $("retrieve-preview").src = asset(preview.image);
  }
  $("combo-hint").textContent = count === 2 ? "两张相同牌：随机抽对方一张。" : count === 3 ? "三张相同牌：声明牌名，若对方有则交出。" : count === 5 ? "五张不同牌：取回弃牌堆中一张。" : "继续选择至五张不同的牌。";
}

function renderActions() {
  $("action-panel").hidden = !state.me || state.phase !== "playing" || !state.me.hand;
  const primary = $("primary-action"), secondary = $("secondary-action"), hint = $("action-hint");
  const myTurn = state.current === state.me?.id;
  const pending = state.pending, awaiting = state.awaiting;
  const card = selected.length ? cards[selected[0]] : null;
  renderCombo();
  $("position-row").hidden = awaiting?.kind !== "defuse" || awaiting.actor !== state.me?.id;
  $("position").max = state.deckCount;
  primary.disabled = false;
  secondary.hidden = true;
  if (awaiting?.kind === "defuse" && awaiting.actor === state.me?.id) {
    primary.textContent = "放回炸弹"; hint.textContent = "只有你能选择位置，其他玩家看不到。";
  } else if (awaiting?.kind === "favor" && awaiting.target === state.me?.id) {
    primary.textContent = "交出所选手牌"; primary.disabled = !card; hint.textContent = "请选择一张手牌交给索取者。";
  } else if (pending) {
    primary.textContent = pending.actor === state.me?.id ? "确认结算" : "等待出牌者结算";
    primary.disabled = pending.actor !== state.me?.id;
    const nope = state.me?.hand.find((id) => cards[id].kind === "nope");
    if (nope) {secondary.hidden = false; secondary.textContent = "打出「不行」反制";}
    hint.textContent = `「${labels[pending.kind]}」${pending.nopes % 2 ? "目前被反制" : "目前生效"}。`;
  } else {
    primary.textContent = state.drawsDue > 1 ? `抽一张（还需 ${state.drawsDue} 次）` : "抽一张";
    primary.disabled = !myTurn;
    const comboCount = selected.length;
    const signatures = selected.map(signature);
    const validCombo = comboCount === 2 && new Set(signatures).size === 1 && (state.mode === "advanced" || card?.kind === "cat")
      || comboCount === 3 && state.mode === "advanced" && new Set(signatures).size === 1
      || comboCount === 5 && state.mode === "advanced" && new Set(signatures).size === 5 && state.discardCards.length > 0;
    secondary.hidden = !myTurn || !card || (comboCount === 1 && ["bomb","defuse","nope","cat"].includes(card.kind)) || (comboCount > 1 && !validCombo);
    secondary.textContent = comboCount > 1 ? `打出 ${comboCount} 张组合` : `打出「${card ? labels[card.kind] : "卡牌"}」`;
    hint.textContent = myTurn ? "可以连续出牌，抽牌才会结束一次回合。" : "等待当前玩家行动。";
  }
}

function render(next) {
  state = next;
  $("room-code").textContent = code;
  $("phase-label").textContent = `${state.mode === "advanced" ? "进阶" : "基础"} · ${state.phase === "lobby" ? "等待开局" : state.phase === "playing" ? "游戏进行中" : "游戏结束"}`;
  $("deck-count").textContent = `${state.deckCount} 张`;
  $("discard-count").textContent = `${state.discardCount} 张`;
  const top = state.discard ? cards[state.discard] : null;
  $("discard-card").outerHTML = top
    ? `<img id="discard-card" src="${asset(top.image)}" alt="弃牌堆顶：${labels[top.kind]}">`
    : `<div id="discard-card" class="discard-empty">弃牌<br>堆</div>`;
  const active = state.players.find((player) => player.id === state.current);
  $("turn-name").textContent = state.phase === "lobby" ? "等待玩家" : state.phase === "finished" ? "胜负已定" : active?.name || "—";
  $("turn-detail").textContent = state.phase === "lobby" ? `在 QQ 群发送 /桌游 加入 ${code}；5 分钟内未开局会自动取消` : state.phase === "finished" ? "这一局已经结束" : `需要完成 ${state.drawsDue} 次回合`;
  $("log").innerHTML = [...state.log].reverse().map((line) => `<div class="log-item">${escapeHtml(line)}</div>`).join("");
  renderPlayers(); renderClaim(); renderHand(); renderActions();
  if (state.me?.peek?.length) {
    $("peek-cards").innerHTML = state.me.peek.map((id) => `<img src="${asset(cards[id].image)}" alt="牌堆顶：${labels[cards[id].kind]}">`).join("");
    $("peek-dialog").showModal();
  }
}

async function submitAction(payload) {
  try { await kittenSession.action(payload); selected = []; if (state) {renderHand(); renderActions();} }
  catch (error) { notify(error.message); }
}

function selectedCard() { return selected[0] ? cards[selected[0]] : null; }

$("room-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const room = $("room-input").value.trim().toUpperCase();
  if (room) location.href = `?room=${encodeURIComponent(room)}`;
});
$("claim-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const claimCode = $("claim-code").value.trim().toUpperCase();
    await kittenSession.claim(claimCode);
    notify("已进入你的座位。");
  } catch (error) { notify(error.message); }
});
document.querySelectorAll("[data-copy-command]").forEach((button) => button.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(button.dataset.copyCommand);
    notify("组局命令已复制，粘贴到 QQ 群发送即可。");
  } catch { notify("复制失败，请手动复制命令。"); }
}));
$("copy-command").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText("/桌游 创建 炸弹猫"); notify("组局命令已复制，粘贴到 QQ 群发送即可。"); }
  catch { notify("复制失败，请手动复制命令。"); }
});
$("copy-link").addEventListener("click", async () => {try {await navigator.clipboard.writeText(location.href); notify("链接已复制。");} catch {notify("复制失败，请从地址栏复制链接。");}});
$("zoom-card").addEventListener("click", () => showCard(selected[0]));
$("retrieve").addEventListener("change", () => {
  const card = cards[$("retrieve").value];
  $("retrieve-preview").hidden = !card;
  if (card) $("retrieve-preview").src = asset(card.image);
});
$("deck").addEventListener("click", () => {if (state?.current === state.me?.id && !state.pending && !state.awaiting) submitAction({type:"draw"});});
$("primary-action").addEventListener("click", () => {
  if (!state?.me) return;
  if (state.awaiting?.kind === "defuse") return submitAction({type:"defuse",position:Number($("position").value)});
  if (state.awaiting?.kind === "favor") return submitAction({type:"give",card_id:selected[0]});
  if (state.pending) return submitAction({type:"resolve"});
  submitAction({type:"draw"});
});
$("secondary-action").addEventListener("click", () => {
  if (state.pending) {
    const nope = state.me?.hand.find((id) => cards[id].kind === "nope");
    if (nope) submitAction({type:"nope",card_id:nope});
    return;
  }
  const card = selectedCard();
  if (!card) return;
  const target = $("target").value || null;
  if (selected.length > 1) {
    if (selected.length !== 5 && !target) return notify("请先指定一位玩家。");
    if (selected.length === 3 && !$("declared").value) return notify("请声明要索取的牌名。");
    if (selected.length === 5 && !$("retrieve").value) return notify("请选择要取回的弃牌。");
    return submitAction({type:"combo",cards:selected,target,declared:$("declared").value || null,retrieve:$("retrieve").value || null});
  }
  if (card.kind === "favor" && !target) return notify("请先指定一位玩家。");
  submitAction({type:"play",card_id:selected[0],target});
});

(async () => {
  if (!code) {$("landing").hidden = false; return;}
  try {
    const preview = await request(`/api/rooms/${code}`);
    if (["love-letter","once-upon-a-time","sushi-go","azul","flip-city","hanamikoji"].includes(preview.game)) {
      $("workshop").hidden = false;
      await window.startWorkshopRoom({api: API, code, initial: preview, notify});
      return;
    }
    if (preview.game && preview.game !== "exploding-kittens") {
      $("party").hidden = false;
      await window.startPartyRoom({api: API, code, initial: preview, notify});
      return;
    }
    $("game").hidden = false;
    manifest = await fetch(asset("manifest.json")).then((response) => response.json());
    cards = Object.fromEntries(manifest.cards.map((card) => [card.id,card]));
    kittenSession = window.createRoomSession({api:API, code, initial:preview,
      onView:render, onStatus:message => {$("connection").textContent=message;}, onError:notify});
    await kittenSession.start();
  } catch (error) {
    $("game").hidden = true;
    $("party").hidden = true;
    $("workshop").hidden = true;
    $("landing").hidden = false;
    $("room-input").value = code;
    notify(error.message || "房间加载失败，请检查房间号后重试。");
  }
})();
