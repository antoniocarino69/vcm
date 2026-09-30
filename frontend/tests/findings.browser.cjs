/* Run with NODE_PATH pointing to a Playwright installation and the stack on :8080.
   Vulnerability list, individual finding detail and per-finding decisions. */
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const base = process.env.VCM_PORTAL_URL || 'http://127.0.0.1:8080';

(async () => {
  const browser = await chromium.launch({headless:true, args:['--no-sandbox']});
  try {
    const page = await browser.newPage();
    const tenants = [{id:'t1', name:'Acme', slug:'acme', status:'active'}];
    const envs = [{id:'e1', tenant_id:'t1', name:'Production', kind:'production', match_key:'ip'}];
    const rows = [
      {id:11, environment_id:'e1', environment_name:'Production', asset_id:'a1',
       asset_ip:'192.0.2.10', asset_fqdn:'web.acme.test', asset_hostname:null,
       asset_os:'Windows Server 2022', asset_tags:{tier:'critical'},
       kind:'vulnerability', scanner:'tenable_nessus', rule_id:'10042',
       rule_title:'TLS weakness', cves:['CVE-2026-0001'], severity:'high',
       severity_raw:'High', status:'active', port:443, protocol:'tcp',
       first_seen:'2026-09-01T00:00:00Z', last_seen:'2026-09-30T00:00:00Z'},
      {id:12, environment_id:'e1', environment_name:'Production', asset_id:'a2',
       asset_ip:'192.0.2.11', asset_fqdn:'db.acme.test', asset_hostname:null,
       asset_os:'Windows Server 2022', asset_tags:{},
       kind:'vulnerability', scanner:'tenable_nessus', rule_id:'10042',
       rule_title:'TLS weakness', cves:['CVE-2026-0001'], severity:'high',
       severity_raw:'High', status:'active', port:8443, protocol:'tcp',
       first_seen:'2026-09-01T00:00:00Z', last_seen:'2026-09-30T00:00:00Z'},
    ];
    const details = new Map();
    for (const row of rows) details.set(String(row.id), {
      finding: {...row, severity_raw:'High', description:'Weak TLS suites accepted.',
        solution:'Disable TLS 1.0.', scanner_output:'Plugin output line', cvss_score:7.5,
        cvss_vector:'CVSS:3.1/AV:N', occurrence_count:3, status_reason:null,
        risk_accepted_until:null, affected_objects:[]},
      asset: {id:row.asset_id, environment_id:'e1', ip:row.asset_ip,
        fqdn:row.asset_fqdn, hostname_netbios:null, os:row.asset_os,
        criticality:3, tags:row.asset_tags},
      environment: {id:'e1', name:'Production', kind:'production'},
      provenance: {last_import:{id:'i1', filename:'scan.nessus', scanner:'tenable_nessus',
        status:'completed', created_at:'2026-09-30T00:00:00Z', environment_id:'e1'},
        closed_by_import:null},
      history: [], comments: [],
    });
    const mutations = [];
    let failStatus = false;

    await page.route('**/api/**', async route => {
      const request = route.request();
      const url = new URL(request.url());
      const path = url.pathname, method = request.method();
      let status = 200, body;
      if (path === '/api/tenants') body = tenants;
      else if (path === '/api/tenants/t1/environments') body = envs;
      else if (path === '/api/tenants/t1') body = tenants[0];
      else if (path === '/api/findings' && method === 'GET') {
        const wanted = url.searchParams.get('status') || 'active';
        const matches = wanted === 'all' ? rows : rows.filter(row => row.status === wanted);
        body = {items:matches, total:matches.length, limit:Number(url.searchParams.get('limit')), offset:0};
      } else if (/^\/api\/findings\/\d+\/status$/.test(path)) {
        mutations.push({path, payload:request.postDataJSON(), tenant:url.searchParams.get('tenant_id')});
        if (failStatus) return route.fulfill({status:422, contentType:'application/json',
          body:JSON.stringify({detail:'Risk Accepted richiede una nota motivazionale'})});
        const id = path.split('/')[3];
        const detail = details.get(id);
        Object.assign(detail.finding, request.postDataJSON());
        detail.history.unshift({changed_at:'2026-10-01T00:00:00Z',
          from_status:'active', to_status:request.postDataJSON().status,
          reason:request.postDataJSON().reason, changed_by:'analyst'});
        body = detail.finding;
      } else if (/^\/api\/findings\/\d+\/comments$/.test(path)) {
        mutations.push({path, payload:request.postDataJSON(), tenant:url.searchParams.get('tenant_id')});
        const id = path.split('/')[3];
        const comment = {id:1, author:request.postDataJSON().author, body:request.postDataJSON().body,
          created_at:'2026-10-01T00:00:00Z'};
        details.get(id).comments.unshift(comment);
        body = comment;
      } else if (/^\/api\/findings\/\d+$/.test(path)) {
        body = details.get(path.split('/')[3]) || {};
      } else body = {};
      await route.fulfill({status, contentType:'application/json', body:JSON.stringify(body)});
    });

    await page.goto(`${base}/vulnerabilities.html?tenant_id=t1&status=active`);
    await page.getByText('2 findings matching this scope and filters.').waitFor();
    assert.equal(await page.locator('#finding-rows tr').count(), 2);
    assert.equal(await page.locator('#finding-rows').getByText('10042 / CVE-2026-0001').count(), 2);
    assert(await page.locator('#filter-chips').getByText('Status: active').count());
    await page.getByLabel('Severity').selectOption('high');
    await page.getByRole('button', {name:'Apply filters'}).click();
    await page.waitForLoadState('networkidle');
    assert(page.url().includes('severity=high'));

    // Open the first row and verify the individual finding page.
    await page.locator('#finding-rows tr').first().getByRole('link', {name:/View finding/}).click();
    await page.getByText('Finding #11').waitFor();
    assert.equal(await page.locator('#finding-title').textContent(), 'TLS weakness');
    assert(await page.locator('#context-rows').getByText('web.acme.test').count());
    assert(await page.locator('#evidence-rows').getByText('Weak TLS suites accepted.').count());
    assert.equal(await page.locator('#scanner-output').textContent(), 'Plugin output line');
    assert(await page.locator('#evidence-rows').getByText(/scan\.nessus · Tenable Nessus/).count());

    // Risk acceptance without a reason is refused before any request.
    await page.locator('#decision-status').selectOption('risk_accepted');
    assert.equal(await page.getByText('(required)').count(), 1);
    await page.getByRole('button', {name:'Save decision'}).click();
    await page.getByText('Risk acceptance requires a reason.').waitFor();
    assert.equal(mutations.length, 0);

    // A valid acceptance travels to this finding only, with reason and expiry.
    await page.locator('#decision-reason').fill('Compensating control in place');
    await page.locator('#decision-expiry').fill('2027-06-30');
    await page.locator('#decision-author').fill('analyst');
    await page.getByRole('button', {name:'Save decision'}).click();
    await page.getByText('Decision saved for this finding only.').waitFor();
    assert.deepEqual(mutations[0], {path:'/api/findings/11/status', tenant:'t1',
      payload:{status:'risk_accepted', reason:'Compensating control in place',
        changed_by:'analyst', risk_accepted_until:'2027-06-30'}});
    assert.equal(await page.locator('#status-badge').getByText('risk accepted').count(), 1);

    // The other row (same rule, other port) is never part of the mutation.
    assert(mutations.every(m => m.path === '/api/findings/11/status'));

    // Comments hit the same finding.
    await page.locator('#comment-body').fill('Verified with ops');
    await page.getByRole('button', {name:'Add comment'}).click();
    await page.getByText('Verified with ops').waitFor();
    assert.equal(mutations.at(-1).path, '/api/findings/11/comments');

    // Back returns to the exact list URL with filters preserved.
    await page.getByRole('link', {name:/Back to findings/}).click();
    await page.waitForLoadState('networkidle');
    assert(page.url().includes('severity=high'), page.url());
    assert.equal(await page.getByLabel('Severity').inputValue(), 'high');

    await page.setViewportSize({width:390, height:844});
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    console.log('PASS: finding list filters, individual detail/evidence/provenance, guarded decisions and comments, per-finding mutations only, back-navigation state, mobile layout');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
