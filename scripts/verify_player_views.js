async (page) => {
  const fixtures = await (await page.request.get("http://127.0.0.1:8098/__fixtures.json")).json();
  const browser = page.context().browser();
  const failures = [];
  let checked = 0;
  async function checkPrivate(tab, player) {
    const panel = tab.locator("[data-private-hand]:visible");
    await panel.waitFor({timeout:15000});
    await tab.waitForFunction(() => [...document.querySelectorAll("[data-private-hand] img")].filter(i=>i.getBoundingClientRect().width>0).every(i=>i.complete&&i.naturalWidth>0),null,{timeout:15000});
    const sources=await panel.locator("img").evaluateAll(images=>images.map(i=>new URL(i.src).pathname.replace(/^\//,"")));
    for(const expected of player.privateImages){
      const index=sources.indexOf(expected);
      if(index<0)throw new Error(`private card missing: ${expected}`);
      sources.splice(index,1);
    }
  }
  for (const fixture of fixtures) {
    for (const player of fixture.players) {
      const context=await browser.newContext({viewport:{width:1280,height:850}});
      await context.addInitScript(({key,token})=>localStorage.setItem(key,token),{key:`dicebot:${fixture.code}`,token:player.token});
      const tab=await context.newPage();
      const errors=[];
      tab.on("pageerror",error=>errors.push(error.message));
      try {
        await tab.goto(`http://127.0.0.1:8098/?room=${fixture.code}`);
        await checkPrivate(tab,player);
        await tab.locator("[data-public-table]:visible").first().waitFor();
        await tab.locator("img").evaluateAll(images=>images.forEach(i=>i.loading="eager"));
        await tab.waitForFunction(()=>[...document.querySelectorAll("main:not([hidden]) img")].filter(i=>i.getBoundingClientRect().width>0).every(i=>i.complete&&i.naturalWidth>0),null,{timeout:15000});
        const publicImages=await tab.locator("[data-public-table]:visible img").count();
        if(!publicImages)throw new Error("public table has no images");
        await tab.reload();
        await checkPrivate(tab,player);
        if(errors.length)throw new Error(errors.join("; "));
        checked++;
        if(fixture.game==="coup"&&fixture.mode==="reformation"&&player.id===fixture.players[0].id){
          await tab.screenshot({path:"output/playwright/coup-private-desktop.png"});
          await tab.locator("[data-private-hand] img").first().click();
          if(!await tab.locator("#card-dialog").isVisible())throw new Error("card zoom did not open");
        }
      } catch(error){ failures.push(`${fixture.game}/${fixture.mode}/${player.id}: ${error.message}`); }
      await context.close();
    }
    const spectator=await browser.newContext();
    const tab=await spectator.newPage();
    try {
      await tab.goto(`http://127.0.0.1:8098/?room=${fixture.code}`);
      await tab.locator("[data-public-table]:visible").first().waitFor();
      const privateCount=await tab.locator("[data-private-hand]:visible img").count();
      if(privateCount)throw new Error("spectator can see private hand images");
    }catch(error){failures.push(`${fixture.game}/spectator: ${error.message}`);}
    await spectator.close();
    console.log(`${fixture.game}/${fixture.mode}: player images, reload and spectator privacy checked`);
  }
  const coup=fixtures.find(f=>f.game==="coup"&&f.mode==="reformation");
  const mobile=await browser.newContext({viewport:{width:390,height:844}});
  await mobile.addInitScript(({key,token})=>localStorage.setItem(key,token),{key:`dicebot:${coup.code}`,token:coup.players[0].token});
  const tab=await mobile.newPage();
  await tab.goto(`http://127.0.0.1:8098/?room=${coup.code}`);
  await checkPrivate(tab,coup.players[0]);
  await tab.screenshot({path:"output/playwright/coup-private-mobile.png",fullPage:true});
  const overflow=await tab.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
  if(overflow)failures.push("coup/mobile: page overflows horizontally");
  await mobile.close();
  console.log(JSON.stringify({checkedPlayerViews:checked,spectatorViews:fixtures.length,failures}));
  if(failures.length)throw new Error(failures.join("\n"));
  return {checkedPlayerViews:checked,spectatorViews:fixtures.length,failures};
}
