/* Run against the portal with an existing Playwright/Chromium installation. */
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const base = process.env.VCM_PORTAL_URL || 'http://127.0.0.1:8080';
(async () => {
  const browser = await chromium.launch({headless:true,args:['--no-sandbox']});
  try {
    const page = await browser.newPage();
    await page.route('https://cdn.jsdelivr.net/**', route => route.fulfill({contentType:'application/javascript',body:'window.Chart = class {destroy(){}}'}));
    await page.route('**/api/**', route => {
      const path = new URL(route.request().url()).pathname;
      let data;
      if (path === '/api/tenants') data = [{id:'a',name:'Client <img src=x>'},{id:'b',name:'Client B'}];
      else if (path.includes('/tenants/')) {
        const id = path.split('/')[3]; data = [{id:'env-'+id,name:'Environment '+id,kind:'production'}];
      } else if (path.includes('/imports')) {
        const id = path.split('/')[3];
        data = [{scanner:'tenable_nessus',filename:id+' <img src=x>.xml',status:'completed',stats:{created:1},created_at:'2026-09-30T12:00:00Z'}];
      } else data = {posture_score:80,totals:{active:1,vulnerabilities:1,compliance:0,false_positive:0,risk_accepted:0},ad_health:[],severity_distribution:{critical:0,high:1,medium:0,low:0,info:0},stig_distribution:{CAT_I:0,CAT_II:0,CAT_III:0,untagged:0},trend:[],top_rules:[{rule_id:'R1',title:'Rule <img src=x>',severity:'high',affected_assets:1}],top_hosts:[{fqdn:'host <img src=x>',open_findings:1,open_crit_high:1}]};
      return route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
    });
    await page.goto(base);
    await page.locator('#top-rules td').first().waitFor();
    assert.equal(await page.locator('img').count(),0,'External fields must be rendered as text');
    assert.equal(await page.locator('#rep-exec').getAttribute('aria-disabled'),'true');
    await page.locator('#tenant').selectOption('a');
    await page.locator('#imports td', {hasText:'env-a <img src=x>.xml'}).waitFor();
    assert.equal(await page.locator('#envs tr').count(),2);
    assert((await page.locator('#rep-exec').getAttribute('href')).endsWith('tenant_id=a'));
    await page.locator('#tenant').selectOption('b');
    await page.locator('#imports td', {hasText:'env-b <img src=x>.xml'}).waitFor();
    assert.equal(await page.locator('#imports tr').count(),2);
    assert(!(await page.locator('#envs').textContent()).includes('Environment a'));
    assert(!(await page.locator('#imports').textContent()).includes('env-a'));
    assert.equal(await page.locator('img').count(),0);
    await page.locator('#tenant').selectOption('');
    await page.getByText('Select a client to view imports.').waitFor();
    assert.equal(await page.locator('#rep-exec').getAttribute('aria-disabled'),'true');
    assert.equal(await page.locator('#rep-exec').getAttribute('href'),null);
    let release;
    const delay = new Promise(resolve => { release = resolve; });
    await page.route('**/api/environments/env-a/imports', async route => {
      await delay;
      await route.fulfill({contentType:'application/json',body:JSON.stringify([
        {filename:'late-a.xml',scanner:'tenable_nessus',status:'completed',stats:{},created_at:'2026-09-30'}
      ])});
    });
    const pending = page.waitForRequest('**/api/environments/env-a/imports');
    await page.locator('#tenant').selectOption('a');
    await pending;
    await page.locator('#tenant').selectOption('b');
    await page.locator('#imports td', {hasText:'env-b <img src=x>.xml'}).waitFor();
    release();
    await page.waitForLoadState('networkidle');
    assert(!(await page.locator('#imports').textContent()).includes('late-a.xml'));
    console.log('PASS: safe external fields, coherent client/environment/import scope, disabled unscoped reports');
  } finally { await browser.close(); }
})().catch(error => { console.error(error);process.exitCode=1; });
