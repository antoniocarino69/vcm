'use strict';
window.AssetPortal = (() => {
  const node = id => document.getElementById(id);
  async function request(path, payload, method = 'POST') {
    const response = await fetch('/api' + path, payload === undefined ? {} : {
      method, headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload)});
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(response.status >= 500 ? 'The server could not load this view. Please retry.' :
        typeof body.detail === 'string' ? body.detail : `Request failed (${response.status}). Check the input values.`);
    }
    return response.json();
  }
  function error(message = '') {node('page-error').textContent = message; node('page-error').hidden = !message;}
  function text(value) {return value == null || value === '' ? '—' : String(value);}
  function date(value) {return value ? new Date(value).toLocaleString('en-GB', {timeZone:'UTC'}) + ' UTC' : '—';}
  function tags(value) {return Object.entries(value || {}).map(([key,val]) => `${key}: ${typeof val === 'object' ? JSON.stringify(val) : val}`).join(' · ') || '—';}
  function table(id, rows, empty, span) {
    const body = node(id); body.replaceChildren();
    for (const values of rows) {
      const row = document.createElement('tr');
      for (const value of values) {
        const cell = document.createElement('td');
        if (value instanceof Node) cell.append(value); else cell.textContent = text(value);
        row.append(cell);
      }
      body.append(row);
    }
    if (!rows.length) {const cell = body.insertRow().insertCell();cell.colSpan = span;cell.textContent = empty;cell.className = 'muted';}
  }
  function badge(value, severity = false) {
    const span = document.createElement('span');
    span.className = severity && ['critical','high','medium','low','info'].includes(value) ? `sev ${value}` : 'badge';
    span.textContent = value === 'active' ? 'Open' : text(value).replaceAll('_',' ');
    return span;
  }
  async function context(onChange) {
    let version = 0, clients = [], client = null, envs = [];
    const params = new URL(location.href).searchParams;
    const tenant = node('tenant'), environment = node('environment');
    async function select(id, requestedEnvironment = '', initial = false) {
      const current = ++version;
      client = clients.find(row => row.id === id) || null;
      environment.disabled = true; environment.replaceChildren(new Option('Loading…',''));
      Portal.scope(client);
      // Invalidate pending asset requests before the new environment list arrives.
      onChange({client,environment:null,loading:true,initial});
      try {
        envs = client ? await request(`/tenants/${client.id}/environments`) : [];
        if (current !== version) return;
        const env = envs.find(row => row.id === requestedEnvironment) || null;
        environment.replaceChildren(new Option('All environments',''));
        for (const row of envs) environment.add(new Option(row.name,row.id));
        environment.value = env?.id || '';environment.disabled = !client;
        Portal.scope(client,env);
        if (!client) node('scope-summary').textContent = 'Select a client';
        await onChange({client,environment:env,loading:false,initial});
      } catch (exc) {if (current === version) error(exc.message);}
    }
    tenant.onchange = () => select(tenant.value);
    environment.onchange = () => {
      const env = envs.find(row => row.id === environment.value) || null;
      Portal.scope(client,env);onChange({client,environment:env,loading:false,initial:false});
    };
    try {
      clients = await request('/tenants');
      tenant.replaceChildren(new Option('Select a client',''));
      for (const row of clients) tenant.add(new Option(row.name,row.id));
      tenant.disabled = false;
      tenant.value = clients.some(row => row.id === params.get('tenant_id')) ? params.get('tenant_id') : '';
      await select(tenant.value,params.get('environment_id'),true);
    } catch (exc) {error(exc.message);}
  }
  return {node,request,error,text,date,tags,table,badge,context};
})();
