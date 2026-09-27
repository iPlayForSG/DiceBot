"use strict";

window.startPartyRoom = async function startPartyRoom({api, code, initial, notify}) {
  const root = document.getElementById("party");
  const game = initial.game;
  const manifest = await fetch(`./public/assets/${game}/manifest.json`).then((response) => {
    if (!response.ok) throw new Error("游戏图包加载失败，请刷新页面。");
    return response.json();
  });
  const escape = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"})[c]);
  const img = (path, alt = "") => path ? `<img src="./${escape(path)}" alt="${escape(alt)}" loading="lazy">` : "";
  const avatar = (player) => player.avatar
    ? `<img class="party-avatar" src="${api}/api/avatars/${encodeURIComponent(player.id)}" alt="${escape(player.name)} 的头像">`
    : `<span class="party-avatar">${escape(player.name.charAt(0))}</span>`;
  const options = (items, placeholder = "请选择") => `<option value="">${placeholder}</option>${items.map(([value, label]) => `<option value="${escape(value)}">${escape(label)}</option>`).join("")}`;
  let token = localStorage.getItem(`dicebot:${code}`);
  let view = initial;
  let socket;

  async function request(path, method = "GET", body = null) {
    let response;
    try {
      response = await fetch(`${api}${path}`, {
        method,
        headers: {"Content-Type":"application/json", ...(token ? {Authorization:`Bearer ${token}`} : {})},
        ...(body ? {body:JSON.stringify(body)} : {}),
      });
    } catch { throw new Error("无法连接游戏服务，请稍后重试。"); }
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 401) {
        token = null;
        localStorage.removeItem(`dicebot:${code}`);
      }
      throw new Error(typeof result.detail === "string" ? result.detail : "操作失败，请重试。");
    }
    return result;
  }

  function connect() {
    if (!token) return;
    if (socket) socket.close();
    socket = new WebSocket(`${api.replace(/^http/, "ws")}/ws/${code}`);
    socket.onopen = () => socket.send(token);
    socket.onmessage = (event) => {view = JSON.parse(event.data); render();};
    socket.onclose = (event) => {
      if (event.code === 1008) {
        token = null;
        localStorage.removeItem(`dicebot:${code}`);
        view.me = null;
        render();
      } else if (token) setTimeout(connect, 2500);
    };
  }

  async function send(action) {
    try { view = await request(`/api/rooms/${code}/actions`, "POST", action); render(); }
    catch (error) { notify(error.message); }
  }

  const birdRanges = {
    "1": [[0,20,"长颈鸟",6,9],[20,27,"火烈鸟",2,3],[27,37,"巨嘴鸟",3,4],[37,54,"喜鹊",5,7],[54,64,"猫头鹰",3,4]],
    "2": [[0,13,"红鸟",4,6],[13,33,"黄鸟",6,9],[33,46,"绿鸟",4,6]],
  };
  const bird = (id) => {
    const deck = id.slice(1,2), index = Number(id.slice(3));
    const [, , species, small, large] = birdRanges[deck].find(([start, end]) => start <= index && index < end);
    return {species,small,large,image:`public/assets/cubirds/cards/deck-${deck}-${String(index).padStart(2,"0")}.webp`};
  };
  const splendorCards = {};
  const nobles = {};
  if (game === "splendor") manifest.objects.forEach((obj, index) => {
    if (obj.type === "Card" && obj.image && /^\d+\s+\d+\s+[wugrb]\s+/.test(obj.name)) {
      const [id, points, bonus, costText] = obj.name.split(" ");
      const cost = Object.fromEntries([...costText.matchAll(/(\d+)([wugrb])/g)].map((m) => [m[2],Number(m[1])]));
      splendorCards[`s${id}`] = {points:Number(points),bonus,cost,image:`public/assets/splendor/${obj.image}`};
    }
    if (obj.type === "Custom_Tile" && obj.custom_image && /\d+[wugrb]/.test(obj.name)) {
      nobles[`n${index}`] = {image:`public/assets/splendor/${obj.custom_image}`,cost:obj.name};
    }
  });
  const gemNames = {w:"白",u:"蓝",g:"绿",r:"红",b:"黑",j:"黄金"};
  const roleIndices = {"公爵":0,"上尉":1,"刺客":2,"女爵":3,"大使":4,"判官":5,"官僚":6,"投机者":7,"弄臣":8};

  function imageCard(id, details = "") {
    if (game === "cubirds") {
      const card = bird(id);
      return `<figure class="party-card">${img(card.image,card.species)}<figcaption>${escape(card.species)}${details}</figcaption></figure>`;
    }
    if (game === "splendor") {
      const card = splendorCards[id];
      return card ? `<figure class="party-card">${img(card.image,`${card.points} 分，${gemNames[card.bonus]}色奖励`)}<figcaption>${card.points} 分 · ${gemNames[card.bonus]}色${details}</figcaption></figure>` : "";
    }
    if (game === "coup") return `<figure class="party-card">${img(`public/assets/coup/cards/deck-3-${String(roleIndices[id]).padStart(2,"0")}.webp`,id)}<figcaption>${escape(id)}${details}</figcaption></figure>`;
    return "";
  }

  function cubirdsBoard() {
    const state = view.state, me = view.me, current = view.current === me?.id;
    const species = [...new Set((me?.hand || []).map((id) => bird(id).species))];
    const collection = state.collection || {};
    return `<section class="party-panel"><h2>篱笆上的鸟</h2><p>同种鸟放在一排的左端或右端，围住的鸟加入手牌。</p>
      <div class="bird-rows">${(state.rows || []).map((row, index) => `<div class="bird-row"><strong>第 ${index+1} 排</strong><div class="party-card-strip">${row.map((id) => imageCard(id)).join("")}</div></div>`).join("")}</div>
      <p>抽牌堆 ${state.deckCount ?? 0} 张 · 弃牌堆 ${state.discardCount ?? 0} 张</p></section>
      <section class="party-panel"><h2>收集进度</h2><div class="party-collection">${view.players.map((player) => `<div><strong>${escape(player.name)}</strong><div class="party-card-strip">${(collection[player.id] || []).map((id) => imageCard(id)).join("")}</div></div>`).join("")}</div></section>
      <section class="party-panel"><h2>我的手牌</h2>${me ? `<div class="party-card-strip">${me.hand.map((id) => imageCard(id)).join("")}</div>` : "<p>认领自己的 QQ 座位后可见手牌。</p>"}</section>
      ${current ? `<section class="party-panel party-controls"><h2>本回合操作</h2>${state.stage === "place" ? `<form data-action="bird-place"><label>鸟类<select name="species" required>${options(species.map((name) => [name,name]))}</select></label><label>排数<select name="row">${[0,1,2,3].map((n) => `<option value="${n}">第 ${n+1} 排</option>`).join("")}</select></label><label>方向<select name="side"><option value="left">左端</option><option value="right">右端</option></select></label><button class="primary-action">摆出这类鸟</button></form>` : `<div class="party-actions">${state.can_draw_two ? `<button data-action="bird-draw">额外摸 2 张</button>` : ""}${state.flock_done ? "" : `<form data-action="bird-flock"><label>完成鸟群<select name="species" required>${options(species.map((name) => [name,name]))}</select></label><button>收集鸟群</button></form>`}<button data-action="bird-end" class="primary-action">结束回合</button></div>`}</section>` : ""}`;
  }

  function splendorBoard() {
    const state = view.state, me = view.me, current = view.current === me?.id;
    const canAct = current && !state.pending_noble?.length;
    const cardBox = (id, tier, reserved = false) => `<div class="market-card">${imageCard(id)}${canAct ? `<div><button data-action="s-buy" data-card="${id}" data-tier="${tier}">购买</button>${reserved ? "" : `<button data-action="s-reserve" data-card="${id}" data-tier="${tier}">保留</button>`}</div>` : ""}</div>`;
    return `<section class="party-panel"><h2>宝石供应</h2><div class="gem-bank">${Object.entries(state.bank || {}).map(([color,count]) => `<span class="gem gem-${color}">${gemNames[color]} ${count}</span>`).join("")}</div></section>
      <section class="party-panel"><h2>发展卡市场</h2>${[3,2,1].map((tier) => `<div class="market-tier"><h3>${tier} 级 · 牌堆剩余 ${state.decks?.[tier] ?? 0} 张</h3><div class="market-grid">${(state.market?.[tier] || []).map((id) => cardBox(id,tier)).join("")}</div>${canAct ? `<button data-action="s-blind" data-tier="${tier}">盲抽保留</button>` : ""}</div>`).join("")}</section>
      <section class="party-panel"><h2>贵族</h2><div class="party-card-strip">${(state.nobles || []).map((id) => `<figure class="party-card">${img(nobles[id]?.image,"贵族卡")}</figure>`).join("")}</div></section>
      <section class="party-panel"><h2>玩家进度</h2><div class="party-stats">${view.players.map((p) => {const built=state.built?.[p.id] || [];const points=built.reduce((n,id)=>n+(splendorCards[id]?.points||0),0)+3*(state.claimed?.[p.id]?.length||0);return `<div><strong>${escape(p.name)} · ${points} 分</strong><span>${built.length} 张发展卡 · ${state.claimed?.[p.id]?.length||0} 位贵族 · ${typeof state.reserved?.[p.id] === "number" ? state.reserved[p.id] : state.reserved?.[p.id]?.length||0} 张保留牌</span></div>`;}).join("")}</div></section>
      ${me ? `<section class="party-panel"><h2>我的宝石与保留牌</h2><div class="gem-bank">${Object.entries(state.hold?.[me.id] || {}).map(([color,count]) => `<span class="gem gem-${color}">${gemNames[color]} ${count}</span>`).join("")}</div><div class="market-grid">${(state.reserved?.[me.id] || []).map((id) => cardBox(id,splendorCards[id]?.tier || 1,true)).join("")}</div></section>` : ""}
      ${current && state.pending_noble?.length ? `<section class="party-panel party-controls"><h2>选择访问你的贵族</h2><div class="party-actions">${state.pending_noble.map((id) => `<button data-action="s-noble" data-noble="${id}">${img(nobles[id]?.image,"贵族卡")}选择这位贵族</button>`).join("")}</div></section>` : ""}
      ${canAct ? `<section class="party-panel party-controls"><h2>领取宝石</h2><form data-action="s-take"><p>选至多 3 种不同颜色；要取 2 枚同色，请在前两项选同一种。</p><div class="party-form-row">${[1,2,3].map((n) => `<label>第 ${n} 枚<select name="color${n}">${options(Object.entries(gemNames).filter(([key]) => key !== "j").map(([key,name]) => [key,name+"色"]),"不取")}</select></label>`).join("")}</div><details><summary>持有超过 10 枚时选择归还</summary><div class="party-form-row">${Object.entries(gemNames).map(([key,name]) => `<label>${name}<input type="number" name="return_${key}" min="0" max="10" value="0"></label>`).join("")}</div></details><button class="primary-action">领取宝石</button></form></section>` : ""}`;
  }

  function avalonBoard() {
    const state = view.state, me = view.me, current = view.current === me?.id;
    const playerOptions = view.players.map((p) => [p.id,p.name]);
    const role = me?.role ? `<div class="secret-role">${me.roleImage ? img(me.roleImage,me.role) : ""}<div><strong>你的身份：${escape(me.role)}</strong><p>${me.known?.length ? `你认得：${me.known.map((id) => escape(view.players.find((p) => p.id === id)?.name || id)).join("、")}` : "你没有额外的身份情报。"}</p></div></div>` : "<p>认领座位后可查看自己的秘密身份。</p>";
    const stageText = {propose:"队长提名任务队伍",team_vote:"全员秘密表决队伍",quest_vote:"队员秘密提交任务牌",assassinate:"刺客决定刺杀对象"};
    return `<section class="party-panel"><h2>身份情报</h2>${role}</section>
      <section class="party-panel"><h2>任务进度</h2><div class="quest-track">${[0,1,2,3,4].map((n) => `<div class="quest ${state.results?.[n] === true ? "quest-good" : state.results?.[n] === false ? "quest-evil" : ""}"><strong>${n+1}</strong><span>${state.results?.[n] === true ? "成功" : state.results?.[n] === false ? "失败" : `${({5:[2,3,2,3,3],6:[2,3,4,3,4],7:[2,3,3,4,4],8:[3,4,4,5,5],9:[3,4,4,5,5],10:[3,4,4,5,5]})[view.players.length][n]} 人`}</span></div>`).join("")}</div><p>${escape(stageText[state.stage] || "等待结算")} · 连续否决 ${state.rejections || 0}/5</p>${state.team?.length ? `<p>本次队员：${state.team.map((id) => escape(view.players.find((p) => p.id === id)?.name || id)).join("、")}</p>` : ""}</section>
      ${me && state.stage === "propose" && current ? `<section class="party-panel party-controls"><h2>提名队伍</h2><form data-action="a-propose"><div class="team-select">${view.players.map((p) => `<label><input type="checkbox" name="team" value="${escape(p.id)}">${escape(p.name)}</label>`).join("")}</div><button class="primary-action">提交队伍</button></form></section>` : ""}
      ${me && state.stage === "team_vote" && !state.votes?.[me.id] ? `<section class="party-panel party-controls"><h2>秘密表决</h2><div class="party-actions"><button data-action="a-vote" data-vote="approve">赞成队伍</button><button data-action="a-vote" data-vote="reject">反对队伍</button></div></section>` : ""}
      ${me && state.stage === "quest_vote" && state.team?.includes(me.id) && !state.quest_votes?.[me.id] ? `<section class="party-panel party-controls"><h2>秘密提交任务牌</h2><div class="party-actions"><button data-action="a-quest" data-vote="success">任务成功</button>${["刺客","莫甘娜","莫德雷德","奥伯伦","爪牙"].includes(me.role) ? `<button data-action="a-quest" data-vote="fail">任务失败</button>` : ""}</div></section>` : ""}
      ${me?.role === "刺客" && state.stage === "assassinate" ? `<section class="party-panel party-controls"><h2>选择刺杀对象</h2><form data-action="a-assassinate"><label>目标<select name="target" required>${options(playerOptions.filter(([id]) => id !== me.id))}</select></label><button class="primary-action">确认刺杀</button></form></section>` : ""}`;
  }

  function coupBoard() {
    const state = view.state, me = view.me, pending = state.pending;
    const current = view.current === me?.id;
    const isKs = view.mode.startsWith("ks-");
    const isReformation = view.mode === "reformation";
    const targetOptions = view.players.filter((p) => p.alive && (p.id !== me?.id || isReformation))
      .map((p) => [p.id, p.id === me?.id ? `${p.name}（自己，仅用于转换阵营）` : p.name]);
    const stats = `<section class="party-panel"><h2>权力与硬币</h2><div class="party-stats">${view.players.map((p) => `<div><strong>${escape(p.name)} ${p.alive ? "" : "· 已出局"}</strong><span>${state.coins?.[p.id] ?? 0} 枚硬币 · ${p.cards} 张影响牌${state.factions?.[p.id] ? ` · ${escape(state.factions[p.id])}` : ""}</span><small>已公开：${(state.lost?.[p.id] || []).join("、") || "无"}</small></div>`).join("")}</div>${isReformation ? `<p>国库：${state.treasury} 枚。不能对其他同阵营玩家发动针对行动。</p>` : ""}</section>`;
    const ownHand = me ? `<section class="party-panel"><h2>我的影响牌</h2><div class="party-card-strip">${me.hand.map((role) => imageCard(role)).join("")}</div><p>身份只在你的浏览器显示。失去全部影响牌即出局。</p></section>` : "";
    let controls = "";
    if (pending) {
      const actor = view.players.find((p) => p.id === pending.actor)?.name || "玩家";
      const target = view.players.find((p) => p.id === pending.target)?.name || "";
      const aidRole = isKs ? (view.mode === "ks-speculator" ? "投机者" : "官僚") : "公爵";
      const stealRoles = isKs ? ["上尉","弄臣"] : isReformation ? ["上尉","判官"] : ["上尉","大使"];
      const blockRoles = pending.move === "aid" ? [aidRole] : pending.move === "steal" ? stealRoles : ["女爵"];
      let actions = "";
      if (me && pending.actor !== me.id && !pending.blocked && ["aid","steal","assassinate"].includes(pending.move)) {
        actions += `<form data-action="c-block"><select name="role">${options(blockRoles.map((role) => [role,role]))}</select><button>声明阻挡</button></form>`;
      }
      if (me?.hand?.length) {
        const handOptions = options(me.hand.map((role) => [role,role]));
        actions += `<form data-action="c-reveal"><select name="card">${handOptions}</select><button>失去影响</button></form><form data-action="c-prove"><select name="card">${handOptions}</select><button>亮牌证明</button></form>`;
      }
      if (me && pending.must_lose === me.id) {
        actions += `<form data-action="c-lose"><select name="card">${options(me.hand.map((role) => [role,role]))}</select><button class="primary-action">确认失去影响</button></form>`;
      }
      if (me && pending.exchange && pending.actor === me.id) {
        actions += `<form data-action="c-exchange"><p>勾选要洗回牌库的牌，最后保留两张。</p>${me.hand.map((role,i) => `<label><input type="checkbox" name="card" value="${escape(role)}">第 ${i+1} 张 ${escape(role)}</label>`).join("")}<button class="primary-action">完成交换</button></form>`;
      }
      if (me && pending.inspection && pending.actor === me.id) {
        actions += `<div><p>你看到了：${escape(pending.inspection)}</p><button data-action="c-inspect-keep">让对方保留</button><button data-action="c-inspect-change">要求更换</button></div>`;
      }
      if (me && pending.disorder && pending.actor === me.id) {
        actions += `<form data-action="c-disorder"><p>从手中选一张给目标，再选一张洗回牌库；最后保留两张。</p><label>给目标<select name="to_target">${options(me.hand.map((role) => [role,role]))}</select></label><label>归还牌库<select name="to_deck">${options(me.hand.map((role) => [role,role]))}</select></label><button class="primary-action">完成骚乱</button></form>`;
      }
      if (me && pending.actor === me.id && !["must_lose","exchange","inspection","disorder"].some((key) => pending[key])) {
        actions += `<button data-action="c-resolve" class="primary-action">确认执行</button><button data-action="c-cancel">取消行动</button>${pending.blocked ? '<button data-action="c-overrule">阻挡被成功质疑，继续执行</button>' : ""}`;
      }
      controls = `<section class="party-panel party-controls"><h2>待结算行动</h2><p>${escape(actor)} 宣布「${escape(pending.move)}」${target ? `，目标：${escape(target)}` : ""}。${pending.blocked ? `已被 ${escape(pending.block_role)} 阻挡。` : ""}</p><p>在 QQ 群讨论诈称、质疑和阻挡，再由相关玩家在网页确认判定。</p><div class="party-actions">${actions}</div></section>`;
    } else if (current) {
      const moves = [["income","收入 +1"],["aid","外援 +2"],["steal","上尉：偷窃 2"],["assassinate","刺客：刺杀（3 币）"],["coup","政变（7 币）"]];
      if (isKs) moves.push([view.mode === "ks-speculator" ? "invest" : "bribe",view.mode === "ks-speculator" ? "投机者：投资" : "官僚：贿赂"],["disorder","弄臣：骚乱"]);
      else moves.push(["tax","公爵：税收 +3"],["exchange",isReformation ? "判官：交换" : "大使：交换"]);
      if (isReformation) moves.push(["inspect","判官：检视"],["convert","转换阵营"],["embezzle","挪用国库"]);
      controls = `<section class="party-panel party-controls"><h2>宣布行动</h2><form data-action="c-declare"><label>行动<select name="move">${moves.map(([value,label]) => `<option value="${value}">${label}</option>`).join("")}</select></label><label>目标<select name="target">${options(targetOptions)}</select></label><button class="primary-action">宣布行动</button></form></section>`;
    }
    return stats + ownHand + controls;
  }

  function render() {
    const me = view.me, state = view.state || {};
    root.innerHTML = `<div class="party-top"><div><a href="./">← 游戏库</a><span class="party-kicker">${escape(view.name)} · ${escape(view.mode === "basic" ? "基础" : view.mode === "advanced" ? "进阶" : view.mode.startsWith("ks-") ? "KS 角色包" : "扩展")}</span><h1>${escape(view.name)}</h1><p>房间 ${escape(code)} · ${escape(view.phase === "lobby" ? "等待开局" : view.phase === "finished" ? "游戏结束" : `轮到 ${view.players.find((p) => p.id === view.current)?.name || "玩家"}`)}</p></div><button type="button" data-action="copy-link">复制游玩链接</button></div>
      <div class="party-columns"><aside class="party-sidebar"><h2>玩家 · ${view.players.length}</h2><div class="party-player-list">${view.players.map((p) => `<div class="party-player ${p.id === view.current ? "is-current" : ""}">${avatar(p)}<span><strong>${escape(p.name)}</strong><small>${p.alive ? p.claimed ? "已入座" : "等待入座" : "已出局"}</small></span></div>`).join("")}</div>${!me ? `<div class="party-panel party-claim"><h3>输入身份码认领座位</h3><p>Bot 会私聊发送身份码。请确认群设置已开启“允许群成员私聊”。</p><form data-action="claim"><label>你的身份码<input name="claim_code" autocomplete="one-time-code" maxlength="10" minlength="10" placeholder="输入 10 位身份码" required></label><button class="primary-action">认领我的座位</button></form></div>` : `<p class="party-self">你已入座：${escape(me.name)}</p>`}</aside>
      <div class="party-main">${view.phase === "lobby" ? `<section class="party-panel"><h2>等待房主开局</h2><p>在 QQ 群发送「/桌游 加入 ${escape(code)}」，Bot 会私聊身份码。所有人加入后由房主发送「/桌游 开始」；创建后 5 分钟未开始会自动取消。</p></section>` : game === "cubirds" ? cubirdsBoard() : game === "splendor" ? splendorBoard() : game === "avalon" ? avalonBoard() : coupBoard()}
      <section class="party-panel party-log"><h2>最近动态</h2><ol>${(view.log || []).slice().reverse().map((entry) => `<li>${escape(entry)}</li>`).join("")}</ol></section></div></div>`;
  }

  root.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-action]");
    if (!button || button.closest("form")) return;
    const act = button.dataset.action;
    if (act === "copy-link") {
      try { await navigator.clipboard.writeText(location.href); notify("游玩链接已复制。"); }
      catch { notify("复制失败，请从地址栏复制链接。"); }
      return;
    }
    const tier = Number(button.dataset.tier);
    const actions = {
      "bird-draw":{type:"draw_two"},"bird-end":{type:"end_turn"},
      "s-buy":{type:"buy",card:button.dataset.card,tier},
      "s-reserve":{type:"reserve",card:button.dataset.card,tier},
      "s-blind":{type:"reserve",card:"deck",tier},
      "s-noble":{type:"claim_noble",noble:button.dataset.noble},
      "a-vote":{type:"team_vote",vote:button.dataset.vote},
      "a-quest":{type:"quest_vote",vote:button.dataset.vote},
      "c-resolve":{type:"resolve",apply:true},"c-cancel":{type:"resolve",apply:false},
      "c-overrule":{type:"overrule_block"},
      "c-inspect-keep":{type:"inspect_finish",replace:false},
      "c-inspect-change":{type:"inspect_finish",replace:true},
    };
    if (actions[act]) await send(actions[act]);
  });

  root.addEventListener("submit", async (event) => {
    const form = event.target.closest("form[data-action]");
    if (!form) return;
    event.preventDefault();
    const data = new FormData(form), act = form.dataset.action;
    if (act === "claim") {
      try {
        const result = await request(`/api/rooms/${code}/claim`, "POST", {claim_code:String(data.get("claim_code") || "").trim().toUpperCase()});
        token = result.token;
        localStorage.setItem(`dicebot:${code}`, token);
        view = await request(`/api/rooms/${code}/me`);
        connect();
        render();
        notify("已进入你的座位。");
      } catch (error) { notify(error.message); }
      return;
    }
    let action;
    if (act === "bird-place") action = {type:"place",species:data.get("species"),row:Number(data.get("row")),side:data.get("side")};
    if (act === "bird-flock") action = {type:"flock",species:data.get("species")};
    if (act === "s-take") action = {type:"take",colors:[1,2,3].map((n) => data.get(`color${n}`)).filter(Boolean),returns:Object.keys(gemNames).flatMap((color) => Array(Math.min(10,Number(data.get(`return_${color}`))||0)).fill(color))};
    if (act === "a-propose") action = {type:"propose",team:data.getAll("team")};
    if (act === "a-assassinate") action = {type:"assassinate",target:data.get("target")};
    if (act === "c-declare") action = {type:"declare",move:data.get("move"),target:data.get("target") || null};
    if (act === "c-block") action = {type:"block",role:data.get("role")};
    if (act === "c-reveal") action = {type:"reveal",card:data.get("card")};
    if (act === "c-prove") action = {type:"prove",card:data.get("card")};
    if (act === "c-lose") action = {type:"lose_finish",card:data.get("card")};
    if (act === "c-exchange") action = {type:"exchange_finish",cards:data.getAll("card")};
    if (act === "c-disorder") action = {type:"disorder_finish",to_target:data.get("to_target"),to_deck:data.get("to_deck")};
    if (action) await send(action);
  });

  if (token) {
    try { view = await request(`/api/rooms/${code}/me`); connect(); }
    catch (error) { notify(error.message); view = initial; }
  }
  render();
};
