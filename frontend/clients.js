'use strict';
const element = id => document.getElementById(id);
const kinds = {production:'Production', dmz:'DMZ', active_directory:'Active Directory', staging:'Staging', cloud:'Cloud', ot:'Operational technology', other:'Other'};
const matchKeys = {ip:'IP address', fqdn:'FQDN', netbios:'NetBIOS name'};
let clients = [], environments = [], selectedClient = null, scopeVersion = 0;
let loadingClients = false, savingClient = false, savingEnvironment = false, slugEdited = false, environmentsLoaded = false;

function message(id, text = '') {
  element(id).textContent = text;
  element(id).hidden = !text;
}

async function request(path, payload) {
  const response = await fetch(`/api${path}`, payload === undefined ? {} : {
    method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload)
  });
  if (!response.ok) {
    if (response.status >= 500) throw new Error('The server could not complete the request. Refresh and try again.');
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === 'string' ? body.detail : `Request failed (${response.status}). Check the form values.`);
  }
  return response.json();
}

function renderClients() {
  element('client-list').replaceChildren();
  for (const client of clients) {
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'client-choice';
    button.setAttribute('aria-pressed', String(client.id === selectedClient?.id));
    const name = document.createElement('span'); name.textContent = client.name;
    const key = document.createElement('small'); key.textContent = `${client.slug} · ${client.status}`;
    button.append(name, key);
    button.onclick = () => selectClient(client);
    element('client-list').append(button);
  }
  element('client-list-status').textContent = clients.length ? `${clients.length} client${clients.length === 1 ? '' : 's'}` : 'No clients yet. Create your first client below.';
}

async function selectClient(client) {
  selectedClient = client; environments = []; environmentsLoaded = false;
  const version = ++scopeVersion;
  renderClients();
  element('selected-name').textContent = client?.name || 'Select a client';
  element('selected-description').textContent = client?.description || '';
  element('environment-count').textContent = '0';
  element('environment-list').replaceChildren();
  element('environment-table').hidden = true;
  element('environment-fields').disabled = true;
  element('environment-form').reset();
  message('environment-error');
  const url = new URL(location.href);
  const requestedEnvironment = url.searchParams.get('tenant_id') === client?.id ? url.searchParams.get('environment_id') : null;
  Portal.scope(client);

  element('environment-status').textContent = client ? 'Loading environments…' : 'Select a client to view or create environments.';
  if (!client) return;
  try {
    const rows = await request(`/tenants/${client.id}/environments`);
    if (version !== scopeVersion) return;
    Portal.scope(client, rows.find(env => env.id === requestedEnvironment));
    environments = rows;
    environmentsLoaded = true;
    for (const env of rows) {
      const row = document.createElement('tr');
      for (const value of [env.name, kinds[env.kind] || env.kind, matchKeys[env.match_key] || env.match_key]) {
        const cell = document.createElement('td'); cell.textContent = value; row.append(cell);
      }
      element('environment-list').append(row);
    }
    element('environment-count').textContent = String(rows.length);
    element('environment-table').hidden = !rows.length;
    element('environment-status').textContent = rows.length ? 'Environments belonging to this client.' : 'No environments yet. Create one below.';
    element('environment-fields').disabled = savingEnvironment;
  } catch (error) {
    if (version !== scopeVersion) return;
    element('environment-status').textContent = 'Could not load environments. Refresh to retry.';
    message('environment-error', error.message);
  }
}

async function loadClients(preferredId = selectedClient?.id || new URL(location.href).searchParams.get('tenant_id')) {
  if (loadingClients) return;
  loadingClients = true; element('refresh').disabled = true;
  try {
    clients = await request('/tenants');
    await selectClient(clients.find(client => client.id === preferredId) || clients[0] || null);
  } catch (error) {
    message('notice', error.message);
    element('client-list-status').textContent = 'Could not load clients. Refresh to retry.';
  } finally {
    loadingClients = false; element('refresh').disabled = false;
  }
}

element('refresh').onclick = () => { message('notice'); loadClients(); };
element('client-slug').oninput = () => { slugEdited = true; };
element('client-name').oninput = event => {
  if (!slugEdited) element('client-slug').value = event.target.value.toLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 100).replace(/-$/, '');
};

element('client-form').onsubmit = async event => {
  event.preventDefault();
  if (savingClient || loadingClients) return;
  message('client-error'); message('notice');
  const name = element('client-name').value.trim();
  const slug = element('client-slug').value.trim();
  if (!name) return message('client-error', 'Enter a client name.');
  if (clients.some(client => client.slug === slug)) return message('client-error', 'This client key is already in use. Choose another key.');
  savingClient = true;
  const submit = event.target.querySelector('button[type=submit]'); submit.disabled = true;
  try {
    const client = await request('/tenants', {name, slug, description: element('client-description').value.trim() || null});
    clients.push(client); clients.sort((a, b) => a.name.localeCompare(b.name));
    element('client-form').reset(); slugEdited = false;
    await selectClient(client);
    message('notice', `Client “${client.name}” created. You can now add environments.`);
  } catch (error) { message('client-error', error.message); }
  finally { savingClient = false; submit.disabled = false; }
};

element('environment-form').onsubmit = async event => {
  event.preventDefault();
  if (!selectedClient || savingEnvironment) return;
  message('environment-error'); message('notice');
  const client = selectedClient;
  const name = element('environment-name').value.trim();
  if (!name) return message('environment-error', 'Enter an environment name.');
  if (environments.some(env => env.name === name)) return message('environment-error', 'An environment with this name already exists for this client.');
  const payload = {name, kind: element('environment-kind').value, match_key: element('environment-match').value};
  savingEnvironment = true; element('environment-fields').disabled = true;
  try {
    await request(`/tenants/${client.id}/environments`, payload);
    if (selectedClient?.id === client.id) {
      savingEnvironment = false;
      await selectClient(client);
    }
    message('notice', `Environment “${name}” created for “${client.name}”.`);
  } catch (error) {
    if (selectedClient?.id === client.id) message('environment-error', error.message);
    else message('notice', error.message);
  } finally {
    savingEnvironment = false;
    element('environment-fields').disabled = !environmentsLoaded;
  }
};

loadClients();
