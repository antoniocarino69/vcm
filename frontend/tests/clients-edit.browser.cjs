/* Run with NODE_PATH pointing to a Playwright installation and the stack on :8080.
   Client/environment editing (PATCH) flows and pending-request scope guards. */
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const base = process.env.VCM_PORTAL_URL || 'http://127.0.0.1:8080';

(async () => {
  const browser = await chromium.launch({headless:true, args:['--no-sandbox']});
  try {
    const page = await browser.newPage();
    const clients = [
      {id:'client-a', name:'Alpha client', slug:'alpha-client', description:'First', status:'active'},
      {id:'client-b', name:'Beta client', slug:'beta-client', description:null, status:'active'},
    ];
    const environments = new Map([
      ['client-a', [{id:'env-a1', tenant_id:'client-a', name:'Production', kind:'production', match_key:'ip'}]],
      ['client-b', []],
    ]);
    const patches = [];
    let patchPlan = [];  // one entry consumed per PATCH: {delay?, status?, body?}

    await page.route('**/api/**', async route => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      const method = request.method();
      let status = 200, body;
      if (path === '/api/tenants' && method === 'GET') body = clients;
      else if (path === '/api/tenants' && method === 'POST') {
        status = 201;
        body = {...request.postDataJSON(), id:`client-${clients.length}`, status:'active'};
        clients.push(body); environments.set(body.id, []);
      } else if (method === 'PATCH') {
        const payload = request.postDataJSON();
        patches.push({path, payload});
        const plan = patchPlan.shift() || {};
        if (plan.delay) await plan.delay;
        status = plan.status || 200;
        if (status !== 200) return route.fulfill({status, contentType:'application/json', body:JSON.stringify(plan.body)});
        const segments = path.split('/');  // /api/tenants/{id} or /api/environments/{id}
        const id = segments[3];
        const collection = segments[2] === 'tenants' ? clients : [...environments.values()].flat();
        const record = collection.find(item => item.id === id);
        if (segments[2] === 'tenants' && payload.slug
            && clients.some(item => item.slug === payload.slug && item.id !== id)) {
          status = 409;
          return route.fulfill({status, contentType:'application/json',
            body:JSON.stringify({detail:'A client with this slug already exists'})});
        }
        Object.assign(record, payload);
        body = record;
      } else if (/^\/api\/tenants\/[^/]+\/environments$/.test(path)) {
        const id = path.split('/')[3];
        if (method === 'POST') {
          body = {...request.postDataJSON(), id:`env-${environments.get(id).length}`, tenant_id:id};
          environments.get(id).push(body);
        } else body = environments.get(id);
      } else body = [];
      await route.fulfill({status, contentType:'application/json', body:JSON.stringify(body)});
    });

    await page.goto(`${base}/clients.html`);
    await page.getByText('Alpha client').first().waitFor();

    // --- edit client: only the changed field travels in the PATCH body
    await page.getByRole('button', {name:/Alpha client/}).click();
    await page.getByLabel('Client name', {exact:true}).nth(1).fill('Alpha client renamed');
    await page.getByRole('button', {name:'Save client changes', exact:true}).click();
    await page.getByText('Client updated.').waitFor();
    assert.deepEqual(patches[0], {path:'/api/tenants/client-a', payload:{name:'Alpha client renamed'}});
    assert.equal(await page.getByLabel('Client key', {exact:true}).nth(1).inputValue(), 'alpha-client');
    await page.getByRole('button', {name:/Alpha client renamed/}).waitFor();

    // --- no changes: no PATCH at all
    await page.getByRole('button', {name:'Save client changes', exact:true}).click();
    await page.getByText('No changes to save.').waitFor();
    assert.equal(patches.length, 1);

    // --- duplicate key rejected with the server message
    await page.getByLabel('Client key', {exact:true}).nth(1).fill('beta-client');
    await page.getByRole('button', {name:'Save client changes', exact:true}).click();
    await page.getByText('A client with this slug already exists').waitFor();
    assert.equal(patches.length, 1);
    await page.getByLabel('Client key', {exact:true}).nth(1).fill('alpha-client');

    // --- server 422 shows the error and keeps the form usable
    patchPlan.push({status:422, body:{detail:[{msg:'value_error.slug'}]}});
    await page.getByLabel('Client description', {exact:true}).fill('Updated notes');
    await page.getByRole('button', {name:'Save client changes', exact:true}).click();
    await page.locator('#client-edit-error').waitFor();
    assert(!(await page.getByRole('button', {name:'Save client changes', exact:true}).isDisabled()));
    assert.equal(await page.getByLabel('Client description', {exact:true}).inputValue(), 'Updated notes');

    // --- edit environment: only the changed fields travel
    await page.locator('#environment-list tr', {hasText:'Production'}).getByRole('button', {name:'Edit'}).click();
    await page.getByLabel('Match assets by').nth(1).selectOption('fqdn');
    await page.getByRole('button', {name:'Save environment changes', exact:true}).click();
    await page.getByText('Environment updated.').waitFor();
    assert.deepEqual(patches[patches.length - 1],
      {path:'/api/environments/env-a1', payload:{match_key:'fqdn'}});
    assert.equal(environments.get('client-a')[0].kind, 'production');
    await page.locator('#environment-list tr', {hasText:'Production'}).waitFor();

    // --- a late edit response must not touch the newly selected client
    let releasePatch;
    const hold = new Promise(resolve => { releasePatch = resolve; });
    patchPlan.push({delay: hold});
    await page.getByLabel('Client description', {exact:true}).fill('Late update');
    await page.getByRole('button', {name:'Save client changes', exact:true}).click();
    await page.getByRole('button', {name:/Beta client/}).click();
    await page.getByText('No environments yet. Create one below.').waitFor();
    releasePatch();
    await page.waitForLoadState('networkidle');
    assert.equal(await page.locator('#selected-name').textContent(), 'Beta client');
    const editName = await page.getByLabel('Client name', {exact:true}).nth(1).inputValue();
    assert.equal(editName, 'Beta client');
    assert.equal(clients.find(client => client.id === 'client-a').description, 'Late update');

    // --- a late environment creation must not repopulate the new client's table
    let releaseCreate;
    const holdCreate = new Promise(resolve => { releaseCreate = resolve; });
    await page.route('**/api/tenants/client-a/environments', async route => {
      if (route.request().method() === 'POST') {
        await holdCreate;
        const body = {id:'env-late', tenant_id:'client-a', name:'Late env', kind:'other', match_key:'ip'};
        environments.get('client-a').push(body);
        return route.fulfill({contentType:'application/json', body:JSON.stringify(body)});
      }
      return route.fallback();
    });
    await page.getByRole('button', {name:/Alpha client renamed/}).click();
    await page.getByLabel('Environment name').fill('Late env');
    await page.getByRole('button', {name:'Create environment', exact:true}).click();
    await page.getByRole('button', {name:/Beta client/}).click();
    await page.getByText('No environments yet. Create one below.').waitFor();
    releaseCreate();
    await page.waitForLoadState('networkidle');
    assert.equal(await page.locator('#selected-name').textContent(), 'Beta client');
    assert.equal(await page.locator('#environment-list tr').count(), 0);

    await page.setViewportSize({width:390,height:844});
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    console.log('PASS: client/environment partial PATCH editing, 409/422 errors, no-change save, stale edit and late action scope guards, mobile layout');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
