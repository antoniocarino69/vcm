/* Run with NODE_PATH pointing to a Playwright installation and the stack on :8080. */
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const base = process.env.VCM_PORTAL_URL || 'http://127.0.0.1:8080';

(async () => {
  const browser = await chromium.launch({headless:true, args:['--no-sandbox']});
  try {
    const page = await browser.newPage();
    const clients = [], environments = new Map();
    let failEnvironment = false;
    await page.route('**/api/**', async route => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      let body;
      if (path === '/api/tenants') {
        if (request.method() === 'POST') {
          body = {...request.postDataJSON(), id:`client-${clients.length}`, status:'active'};
          clients.push(body); environments.set(body.id, []);
        } else body = clients;
      } else {
        const id = path.split('/')[3];
        if (request.method() === 'POST') {
          if (failEnvironment) return route.fulfill({status:503, body:'unavailable'});
          body = {...request.postDataJSON(), id:`env-${environments.get(id).length}`, tenant_id:id};
          environments.get(id).push(body);
        } else body = environments.get(id);
      }
      await route.fulfill({status:200, contentType:'application/json', body:JSON.stringify(body)});
    });
    await page.goto(`${base}/clients.html`);
    await page.getByText('No clients yet. Create your first client below.').waitFor();
    assert(await page.locator('#environment-name').isDisabled());

    const name = 'Example <b>Client</b>';
    await page.getByLabel('Client name', {exact:true}).fill(name);
    assert.equal(await page.locator('#client-slug').inputValue(), 'example-b-client-b');
    await page.getByRole('button', {name:'Create client', exact:true}).click();
    await page.getByText('No environments yet. Create one below.').waitFor();
    assert.equal(await page.locator('#selected-name').textContent(), name);
    assert.equal(await page.locator('#selected-name b').count(), 0);
    await page.getByLabel('Environment name').fill('AD <img src=x>');
    await page.getByLabel('Type', {exact:true}).selectOption('active_directory');
    await page.getByLabel('Match assets by').selectOption('fqdn');
    await page.getByRole('button', {name:'Create environment', exact:true}).click();
    await page.locator('#environment-list td', {hasText:'AD <img src=x>'}).waitFor();
    assert.equal(await page.locator('#environment-list img').count(), 0);
    assert.equal(environments.get('client-0')[0].match_key, 'fqdn');
    await page.reload();
    await page.locator('#environment-list td', {hasText:'AD <img src=x>'}).waitFor();

    await page.getByLabel('Environment name').fill('AD <img src=x>');
    await page.getByRole('button', {name:'Create environment', exact:true}).click();
    await page.locator('#environment-error').waitFor();
    assert.equal(environments.get('client-0').length, 1);

    failEnvironment = true;
    await page.getByLabel('Environment name').fill('Unreachable');
    await page.getByRole('button', {name:'Create environment', exact:true}).click();
    await page.getByText('The server could not complete the request. Refresh and try again.').waitFor();
    assert.equal(await page.locator('#environment-name').inputValue(), 'Unreachable');
    assert(!(await page.locator('#environment-name').isDisabled()));
    failEnvironment = false;

    await page.getByLabel('Client name', {exact:true}).fill('Second client');
    await page.getByRole('button', {name:'Create client', exact:true}).click();
    await page.getByText('No environments yet. Create one below.').waitFor();
    assert.equal(await page.locator('#environment-list tr').count(), 0);
    await page.getByRole('button', {name:/Example <b>Client/}).click();
    await page.locator('#environment-list td', {hasText:'AD <img src=x>'}).waitFor();

    // A stale response from the previous client must not replace the current table.
    let release;
    const delay = new Promise(resolve => { release = resolve; });
    await page.route('**/api/tenants/client-0/environments', async route => {
      await delay;
      await route.fulfill({contentType:'application/json',body:JSON.stringify(environments.get('client-0'))});
    });
    await page.getByRole('button', {name:/Second client/}).click();
    await page.getByText('No environments yet. Create one below.').waitFor();
    await page.getByRole('button', {name:/Example <b>Client/}).click();
    await page.getByText('Loading environments…').waitFor();
    await page.getByRole('button', {name:/Second client/}).click();
    await page.getByText('No environments yet. Create one below.').waitFor();
    release();
    await page.waitForLoadState('networkidle');
    assert.equal(await page.locator('#selected-name').textContent(), 'Second client');
    assert.equal(await page.locator('#environment-list tr').count(), 0);
    await page.setViewportSize({width:390,height:844});
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    console.log('PASS: empty state, client/environment creation, persistence, safe text, duplicate check, server error, client switching, stale response, mobile layout');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
