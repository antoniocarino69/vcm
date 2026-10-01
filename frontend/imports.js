'use strict';
(() => {
  const $ = id => document.getElementById(id);
  let clients = [], environments = [], generation = 0, timer, busy = false;
  const initial = new URL(location.href).searchParams;
  const initialClient = initial.get('tenant_id'), initialEnvironment = initial.get('environment_id');
  async function request(path, options) {
    const response = await fetch('/api' + path, options);
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Request failed (${response.status})`);
    return data;
  }
  function options(select, rows, prompt) {
    select.replaceChildren(new Option(prompt, ''));
    for (const row of rows) select.add(new Option(row.name, row.id));
  }
  function context() {
    clearTimeout(timer); generation++; busy = false;
    $('upload').disabled = false;
    $('progress').textContent = ''; $('error').textContent = ''; $('results').hidden = true;
    $('history').replaceChildren();
    $('upload-fields').disabled = !$('environment').value;
    Portal.scope(clients.find(row => row.id === $('tenant').value), environments.find(row => row.id === $('environment').value));
    return generation;
  }
  async function history(token = generation) {
    const tenant = $('tenant').value, env = $('environment').value;
    if (!tenant || !env) { $('history-status').textContent = 'Select a client and environment.'; return; }
    $('history-status').textContent = 'Loading imports…';
    try {
      const rows = await request(`/environments/${encodeURIComponent(env)}/imports?tenant_id=${encodeURIComponent(tenant)}`);
      if (token !== generation) return;
      $('history').replaceChildren();
      for (const row of rows) {
        const tr = document.createElement('tr');
        for (const value of [row.created_at, row.filename, row.scanner, row.status, row.error || JSON.stringify(row.stats || {})]) {
          const td = document.createElement('td'); td.textContent = value || '—'; tr.append(td);
        }
        $('history').append(tr);
      }
      $('history-status').textContent = rows.length ? `${rows.length} imports` : 'No imports yet.';
    } catch (error) { if (token === generation) $('history-status').textContent = error.message; }
  }
  async function selectClient(envId = '') {
    environments = []; options($('environment'), [], 'Select an environment'); $('environment').disabled = true;
    const token = context(), tenant = $('tenant').value;
    if (!tenant) { history(token); return; }
    try {
      const rows = await request(`/tenants/${encodeURIComponent(tenant)}/environments`);
      if (token !== generation) return;
      environments = rows; options($('environment'), rows, 'Select an environment'); $('environment').disabled = false;
      if (rows.some(row => row.id === envId)) $('environment').value = envId;
      context(); history();
    } catch (error) { if (token === generation) $('error').textContent = error.message; }
  }
  async function poll(id, tenant, token) {
    try {
      const row = await request(`/imports/${encodeURIComponent(id)}?tenant_id=${encodeURIComponent(tenant)}`);
      if (token !== generation) return;
      $('progress').textContent = `Import ${row.status}: ${JSON.stringify(row.stats || {})}`;
      if (['completed', 'failed'].includes(row.status)) {
        busy = false; $('upload').disabled = false;
        if (row.status === 'completed') {
          const query = new URLSearchParams({tenant_id: tenant, environment_id: $('environment').value});
          $('result-assets').href = `/assets.html?${query}`;
          $('result-findings').href = `/vulnerabilities.html?${query}`;
          $('results').hidden = false;
        }
        if (row.status === 'failed') $('error').textContent = row.error || 'Import failed.';
        history(token);
      } else timer = setTimeout(() => poll(id, tenant, token), 2000);
    } catch (error) {
      if (token !== generation) return;
      busy = false; $('upload').disabled = false;
      $('error').textContent = `Unable to monitor import: ${error.message}. Use Refresh to check its status.`;
    }
  }
  $('tenant').onchange = () => selectClient();
  $('environment').onchange = () => { context(); history(); };
  $('refresh').onclick = () => history();
  $('upload-form').onsubmit = async event => {
    event.preventDefault();
    if (busy || !$('environment').value || !$('file').files.length) return;
    const token = generation, tenant = $('tenant').value, env = $('environment').value;
    busy = true; $('results').hidden = true; $('upload').disabled = true; $('error').textContent = ''; $('progress').textContent = 'Uploading report…';
    const body = new FormData();
    body.append('tenant_id', tenant); body.append('file', $('file').files[0]);
    body.append('scanner', $('scanner').value); body.append('auto_close', String($('auto-close').checked));
    try {
      const result = await request(`/environments/${encodeURIComponent(env)}/imports`, {method: 'POST', body});
      if (token !== generation) return;
      $('file').value = ''; history(token); poll(result.import_id, tenant, token);
    } catch (error) {
      if (token !== generation) return;
      busy = false; $('upload').disabled = false; $('progress').textContent = ''; $('error').textContent = error.message;
    }
  };
  request('/tenants').then(rows => {
    clients = rows; options($('tenant'), rows, 'Select a client');
    if (rows.some(row => row.id === initialClient)) $('tenant').value = initialClient;
    selectClient(initialEnvironment);
  }).catch(error => { $('error').textContent = error.message; });
})();
