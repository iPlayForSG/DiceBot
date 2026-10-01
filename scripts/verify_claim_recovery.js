async (page) => {
  const fixtures=await (await page.request.get("http://127.0.0.1:8098/__fixtures.json")).json();
  const fixture=fixtures.find(f=>f.game==="coup"&&f.mode==="reformation");
  const player=fixture.players[0];
  const browser=page.context().browser();
  const context=await browser.newContext();
  const fresh=await (await page.request.post(`http://127.0.0.1:8776/api/rooms/${fixture.code}/claim`,{data:{claim_code:player.claim}})).json();
  await context.addInitScript(({key,token})=>{if(!localStorage.getItem(key))localStorage.setItem(key,token);},{key:`dicebot:${fixture.code}`,token:fresh.token});
  const tab=await context.newPage();
  await tab.goto(`http://127.0.0.1:8098/?room=${fixture.code}`);
  await tab.locator("[data-private-hand] img").first().waitFor();
  for(let attempt=0;attempt<2;attempt++){
    await tab.request.post(`http://127.0.0.1:8776/api/rooms/${fixture.code}/claim`,{data:{claim_code:player.claim}});
    const form=tab.locator('form[data-action="claim"]');
    await form.waitFor();
    if(await tab.locator("[data-private-hand] img").count())throw new Error("revoked seat still displays hand");
    await form.locator("input").fill(player.claim);
    await form.locator("button").click();
    await tab.locator("[data-private-hand] img").first().waitFor();
    if(await tab.locator("[data-private-hand] img").count()!==player.privateImages.length)throw new Error("reclaimed hand incomplete");
    await tab.reload();
    await tab.locator("[data-private-hand] img").first().waitFor();
  }
  await context.close();
  return {seatTransfers:2,reclaims:2,reloads:2,handRestored:true};
}
