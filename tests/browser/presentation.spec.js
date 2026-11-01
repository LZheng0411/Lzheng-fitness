const {test,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto');
const {spawnSync}=require('node:child_process');const {pathToFileURL}=require('node:url');
const {navigate,rail}=require('../../skills/lzheng-fitness-workbench-builder/scripts/workbench_browser_navigation.cjs');
const repo=path.resolve(__dirname,'../..'),skill=path.join(repo,'skills/lzheng-fitness-workbench-builder');let formal;
test.beforeAll(()=>{
  const project=path.join(fs.mkdtempSync(path.join(os.tmpdir(),'fitness-presentation-')),'project');
  const r=spawnSync(process.env.PYTHON||'python',['-B',path.join(skill,'scripts/Initialize-FitnessWorkbench.py'),'--target',project,'--brand','TEST'],{encoding:'utf8',env:{...process.env,PYTHONUTF8:'1',PYTHONDONTWRITEBYTECODE:'1'}});
  if(r.status!==0)throw Error(r.stdout+r.stderr);formal=path.join(project,'健身工作台.html');
});
test('approved background files match the recorded source and template has no personal data',()=>{
  const provenance=JSON.parse(fs.readFileSync(path.join(skill,'assets/presentation-provenance.json'),'utf8'));
  for(const [name,sha] of Object.entries(provenance.backgrounds))expect(crypto.createHash('sha256').update(fs.readFileSync(path.join(skill,'assets/backgrounds',name))).digest('hex')).toBe(sha);
  const html=fs.readFileSync(path.join(skill,'assets/workbench-template.html'),'utf8');
  expect(JSON.parse(html.match(/<script id="workbench-data" type="application\/json">(.*?)<\/script>/s)[1])).toEqual({});
  expect(JSON.parse(html.match(/<script id="knowledge-library-data" type="application\/json">(.*?)<\/script>/s)[1])).toEqual([]);
  expect(html).toContain('id="fitness-local-store"');
});
test('matching mobile and desktop shells keep every actual page reachable',async({page},info)=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.emulateMedia({reducedMotion:'reduce'});
  await page.route(/^https?:/,r=>r.abort());await page.goto(pathToFileURL(formal).href);
  for(const width of [375,390,760,761,1440]){
    await page.setViewportSize({width,height:960});
    await expect(page.locator('body')).toHaveAttribute('data-px-screen',width<=760?'mobile':'desktop');
    expect(await page.locator('.px-nav-link:visible').count()).toBe(width<=760?5:6);
    await expect(rail(page)).toBeVisible();
    for(const key of ['today','week','trend','nutrition','record','knowledge','settings']){
      await navigate(page,key);await expect(page.locator('#m-'+key)).toBeVisible();
      await expect(page.locator('main>section.on')).toHaveCount(1);
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
    }
    await navigate(page,'today');
    expect(await page.locator('.px-brand-mark').first().innerText()).toBe('TEST');
    if(width===375||width===1440)await page.screenshot({path:info.outputPath('public-'+width+'.png')});
  }
  expect(errors).toEqual([]);
});
test('motion background chooses the matching mobile asset and respects reduced motion',async({page})=>{
  await page.setViewportSize({width:390,height:960});await page.emulateMedia({reducedMotion:'reduce'});await page.goto(pathToFileURL(formal).href);
  expect(await page.locator('#workbenchVideoSource').getAttribute('src')).toBeNull();
  await page.emulateMedia({reducedMotion:'no-preference'});
  await expect(page.locator('#workbenchVideoSource')).toHaveAttribute('src',/workbench-background-mobile\.mp4$/);
  await page.emulateMedia({reducedMotion:'reduce'});
  expect(await page.locator('#workbenchBgVideo').evaluate(video=>video.paused)).toBe(true);
});
