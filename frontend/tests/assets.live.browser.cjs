/* Read-only browser verification against an existing fixture client. */
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const base = process.env.VCM_PORTAL_URL || 'http://127.0.0.1:8080';
const tenantId = process.env.VCM_TEST_TENANT_ID;
(async () => {
 assert(tenantId,'Set VCM_TEST_TENANT_ID to a populated fixture client');
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try {
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/assets.html?tenant_id='+encodeURIComponent(tenantId));
  await page.locator('#asset-rows a').first().waitFor();
  const data=await (await page.request.get(base+'/api/assets?tenant_id='+tenantId)).json();
  assert(data.total>0);assert.equal(await page.locator('#asset-rows tr').count(),data.items.length);
  await page.locator('#os-family').selectOption('windows');
  await page.getByRole('button',{name:'Apply filters',exact:true}).click();
  await page.locator('#asset-rows a').first().waitFor();
  assert(!(await page.locator('#asset-rows').textContent()).includes('Ubuntu'));
  const detailQuery=new URL((await page.locator('#asset-rows a').first().getAttribute('href')),base).searchParams;
  const assetId=detailQuery.get('asset_id');
  await page.locator('#asset-rows a').first().click();
  await page.locator('#asset-detail').waitFor();
  await page.waitForFunction(()=>!document.getElementById('findings-status').textContent.includes('Loading'));
  const detail=await (await page.request.get(`${base}/api/assets/${assetId}?tenant_id=${tenantId}`)).json();
  assert((await page.locator('#asset-fields').textContent()).includes(detail.os));
  assert.equal(await page.locator('#findings-rows tr').count(),detail.open_findings);
  await page.waitForFunction(()=>!document.getElementById('imports-status').textContent.includes('Loading'));
  assert((await page.locator('#imports-rows').textContent()).includes('.nessus'));
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.locator('#back-to-assets').click();
  await page.locator('#asset-rows a').first().waitFor();
  assert.equal(await page.locator('#os-family').inputValue(),'windows');
  assert.deepEqual(errors,[]);
  console.log('PASS live assets: ingest results, Windows filter, asset/finding/import details, list return state and mobile');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
