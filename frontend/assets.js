'use strict';
(() => {
  const {node,request,error,date,tags,table} = AssetPortal;
  let client = null, environment = null, version = 0, loadingScope = false;
  const initial = new URL(location.href).searchParams;
  function hydrate(params) {
    node('search').value = params.get('search') || '';
    node('os-search').value = params.get('os_search') || '';
    node('os-family').value = params.get('os_family') || '';
    node('tags').value = params.getAll('tag').join('\n');
    node('sort').value = `${params.get('sort') || 'ip'}:${params.get('direction') || 'asc'}`;
    if (!node('sort').value) node('sort').value = 'ip:asc';
    node('limit').value = ['25','50','100'].includes(params.get('limit')) ? params.get('limit') : '50';
  }
  hydrate(initial);
  function params(offset) {
    const values = new URLSearchParams();
    if (client) values.set('tenant_id',client.id);
    if (environment) values.set('environment_id',environment.id);
    for (const [field,key] of [['search','search'],['os-search','os_search'],['os-family','os_family']]) {
      const value = node(field).value.trim();if (value) values.set(key,value);
    }
    for (const tag of node('tags').value.split('\n').map(s => s.trim()).filter(Boolean)) values.append('tag',tag);
    const [sort,direction] = node('sort').value.split(':');
    values.set('sort',sort);values.set('direction',direction);values.set('limit',node('limit').value);
    values.set('offset',String(offset));return values;
  }
  function chips(query) {
    node('filter-chips').replaceChildren();
    for (const [key,label] of [['search','Identity'],['os_search','OS text'],['os_family','OS family'],['tag','Asset tag']]) {
      for (const value of query.getAll(key)) {
        const chip = document.createElement('span');chip.className = 'badge';chip.textContent = `${label}: ${value}`;
        node('filter-chips').append(chip);
      }
    }
  }
  async function load(offset = 0, applied = null) {
    const current = ++version;
    error();node('previous').disabled = true;node('next').disabled = true;node('page-position').textContent = '';
    table('asset-rows',[],client ? 'Loading assets…' : 'Select a client to view the inventory.',9);
    if (!client || loadingScope) {node('list-status').textContent = loadingScope ? 'Loading environments…' : 'Select a client to load assets.';return;}
    const query = applied ? new URLSearchParams(applied) : params(offset);
    query.set('offset',String(offset));chips(query);
    history.replaceState(null,'',location.pathname + '?' + query);
    node('list-status').textContent = 'Loading assets…';
    try {
      const data = await request('/assets?' + query);
      if (current !== version) return;
      node('list-status').textContent = `${data.total} asset${data.total === 1 ? '' : 's'} matching this scope and filters.`;
      table('asset-rows',data.items.map(asset => {
        const link = document.createElement('a');const detail = new URLSearchParams(query);detail.set('asset_id',asset.id);
        link.href = '/asset.html?' + detail;link.textContent = 'View';
        link.setAttribute('aria-label',`View asset ${asset.fqdn || asset.ip || asset.hostname_netbios}`);
        link.onclick = () => {try {sessionStorage.setItem('asset-list-position',JSON.stringify({url:location.pathname + location.search,y:scrollY,id:asset.id}));} catch {}};
        return [asset.ip, [asset.fqdn,asset.hostname_netbios].filter(Boolean).join(' / '),asset.os?.trim() ? asset.os : 'Unknown',asset.environment_name,
          `${asset.criticality} / 5`,tags(asset.tags),date(asset.last_seen),`${asset.open_findings} (${asset.open_critical_high} critical/high)`,link];
      }),'No assets match these filters.',9);
      node('page-position').textContent = data.items.length ? `${offset + 1}–${offset + data.items.length} of ${data.total}` : `0 shown of ${data.total}`;
      node('previous').disabled = offset === 0;
      node('next').disabled = offset + data.limit >= data.total;
      node('previous').onclick = () => load(Math.max(0,offset - data.limit),query);
      node('next').onclick = () => load(offset + data.limit,query);
      try {
        const position = JSON.parse(sessionStorage.getItem('asset-list-position'));
        if (position?.url === location.pathname + location.search) {
          const link = [...node('asset-rows').querySelectorAll('a')].find(row => new URL(row.href).searchParams.get('asset_id') === position.id);
          link?.focus({preventScroll:true});window.scrollTo(0,position.y);sessionStorage.removeItem('asset-list-position');
        }
      } catch {}
    } catch (exc) {if (current === version) {error(exc.message);node('list-status').textContent = 'Could not load assets. Apply filters to retry.';table('asset-rows',[],'Asset data unavailable.',9);}}
  }
  node('filters').onsubmit = event => {event.preventDefault();load();};
  node('clear').onclick = () => {node('filters').reset();load();};
  AssetPortal.context(scope => {
    client = scope.client;environment = scope.environment;loadingScope = scope.loading;
    const offset = scope.initial ? Math.max(0,Number(initial.get('offset')) || 0) : 0;
    return load(Number.isSafeInteger(offset) ? offset : 0);
  });
})();
