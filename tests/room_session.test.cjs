const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

function environment(savedToken = "old-token") {
  const storage = new Map(savedToken ? [["dicebot:TESTROOM",savedToken]] : []);
  const sockets = [], timers = new Map(), views = [];
  let timerId = 0;
  class Socket {
    constructor() { sockets.push(this); }
    send(token) { this.sent = token; }
    close() { this.closed = true; }
  }
  const state = {expired:false, hand:"old-hand"};
  const context = {window:{}, WebSocket:Socket,
    localStorage:{getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)},
    setTimeout:callback=>{timers.set(++timerId,callback);return timerId;},clearTimeout:id=>timers.delete(id),
    fetch:async (url,options) => {
      if(url.endsWith("/claim")) return {ok:true,json:async()=>({token:"new-token"})};
      if(url.endsWith("/me") && state.expired) return {ok:false,status:401,json:async()=>({detail:"expired"})};
      const hand = options.headers.Authorization === "Bearer new-token" ? "new-hand" : state.hand;
      return {ok:true,json:async()=>({revision:1,me:url.endsWith("/me")?{id:"1",hand:[hand]}:null})};
    }};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,"../web/room-session.js"),"utf8"),context);
  const session=context.window.createRoomSession({api:"http://fixture",code:"TESTROOM",initial:{me:null},onView:view=>views.push(view)});
  return {session,state,storage,sockets,timers,views};
}

test("a queued close/message from the previous socket cannot erase a newly claimed hand",async()=>{
  const env=environment();
  await env.session.start();
  const old=env.sockets[0], close=old.onclose, message=old.onmessage;
  await env.session.claim("CLAIM00001");
  close({code:1008});
  message({data:JSON.stringify({me:null})});
  assert.equal(env.storage.get("dicebot:TESTROOM"),"new-token");
  assert.equal(env.views.at(-1).me.hand[0],"new-hand");
  assert.equal(env.sockets.length,2);
  assert.equal(old.closed,true);
});

test("an expired saved seat falls back to a public view and shows no previous hand",async()=>{
  const env=environment();
  env.state.expired=true;
  await env.session.start();
  assert.equal(env.storage.has("dicebot:TESTROOM"),false);
  assert.equal(env.views.at(-1).me,null);
  assert.equal(env.sockets.length,0);
});

test("transport loss restores the same private seat before reconnecting",async()=>{
  const env=environment();
  await env.session.start();
  env.sockets[0].onclose({code:1006});
  env.state.hand="updated-hand";
  const callback=[...env.timers.values()][0];
  callback();
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(env.views.at(-1).me.hand[0],"updated-hand");
  assert.equal(env.storage.get("dicebot:TESTROOM"),"old-token");
  assert.equal(env.sockets.length,2);
});
