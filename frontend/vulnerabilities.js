'use strict';
(() => {
  const {node,request,error,text,date,tags,table,badge} = AssetPortal;
  let client = null, environment = null, loadingScope = false, version = 0;
  const initial = new URL(location.href).searchParams;
  const SCANNERS = {qualys_vmdr:'Qualys VMDR', tenable_nessus:'Tenable Nessus',
    scc_xccdf:'DISA SCC', pingcastle:'PingCastle', purple_knight:'Purple Knight'};

  function hydrate(params) {
    node('search').value = params.get('search') || '';
    node('status').value = params.get('status') || 'active';
    node('severity').value = params.get('severity') || '';
    node('scanner').value = params.get('scanner') || '';
    node('kind').value = params.get('kind') || '';
    node('limit').value = ['25','50','100'].includes(params.get('limit')) ? params.get('limit') : '50';
  }
  hydrate(initial);

  function params(offset) {
    const values = new URLSearchParams();
    if (client) values.set('tenant_id', client.id);
    if (environment) values.set('environment_id', environment.id);
    for (const [field,key] of [['search','search'],['status','status'],['severity','severity'],['scanner','scanner'],['kind','kind']]) {
      const value = node(field).value.trim();
      if (value) values.set(key,value);
    }
    values.set('limit', node('limit').value);
    values.set('offset', String(offset));
    return values;
  }
  function chips(query) {
    node('filter-chips').replaceChildren();
    for (const [key,label] of [['search','Text'],['status','Status'],['severity','Severity'],['scanner','Scanner'],['kind','Type']]) {
      const value = query.get(key);
      if (value) {const chip = document.createElement('span');chip.className = 'badge';chip.textContent = `${label}: ${value}`;node('filter-chips').append(chip);}
    }
  }

  async function load(offset = 0, applied = null) {
    const current = ++version;
    error();node('previous').disabled = true;node('next').disabled = true;node('page-position').textContent = '';
    table('finding-rows',[],client ? 'Loading findings…' : 'Select a client to view findings.',12);
    if (!client || loadingScope) {node('list-status').textContent = loadingScope ? 'Loading environments…' : 'Select a client to load findings.';return;}
    const query = applied ? new URLSearchParams(applied) : params(offset);
    query.set('offset', String(offset));chips(query);
    history.replaceState(null,'',location.pathname + '?' + query);
    node('list-status').textContent = 'Loading findings…';
    try {
      const data = await request('/findings?' + query);
      if (current !== version) return;
      node('list-status').textContent = `${data.total} finding${data.total === 1 ? '' : 's'} matching this scope and filters.`;
      table('finding-rows', data.items.map(finding => {
        const assetLabel = [finding.asset_ip, finding.asset_fqdn, finding.asset_hostname].filter(Boolean).join(' / ') || '—';
        const cves = (finding.cves || []).join(', ');
        const link = document.createElement('a');
        const detail = new URLSearchParams(query);detail.set('finding_id', finding.id);
        link.href = '/finding.html?' + detail;link.textContent = 'View';
        link.setAttribute('aria-label', `View finding ${finding.rule_id} on ${assetLabel} port ${text(finding.port)}`);
        link.onclick = () => {try {sessionStorage.setItem('finding-list-position',JSON.stringify({url:location.pathname + location.search,y:scrollY,id:String(finding.id)}));} catch {}};
        return [finding.environment_name, assetLabel,
          finding.asset_os?.trim() ? finding.asset_os : 'Unknown',
          cves ? `${finding.rule_id} / ${cves}` : finding.rule_id,
          badge(finding.severity, true), badge(finding.status), tags(finding.asset_tags),
          SCANNERS[finding.scanner] || finding.scanner,
          finding.port == null ? '—' : `${finding.port}${finding.protocol ? '/' + finding.protocol : ''}`,
          date(finding.first_seen), date(finding.last_seen), link];
      }), 'No findings match these filters.', 12);
      node('page-position').textContent = data.items.length ? `${offset + 1}–${offset + data.items.length} of ${data.total}` : `0 shown of ${data.total}`;
      node('previous').disabled = offset === 0;
      node('next').disabled = offset + data.limit >= data.total;
      node('previous').onclick = () => load(Math.max(0, offset - data.limit), query);
      node('next').onclick = () => load(offset + data.limit, query);
      try {
        const position = JSON.parse(sessionStorage.getItem('finding-list-position'));
        if (position?.url === location.pathname + location.search) {
          const link = [...node('finding-rows').querySelectorAll('a')].find(row => new URL(row.href).searchParams.get('finding_id') === position.id);
          link?.focus({preventScroll:true});window.scrollTo(0,position.y);sessionStorage.removeItem('finding-list-position');
        }
      } catch {}
    } catch (exc) {
      if (current === version) {error(exc.message);node('list-status').textContent = 'Could not load findings. Apply filters to retry.';table('finding-rows',[],'Finding data unavailable.',12);}
    }
  }

  node('filters').onsubmit = event => {event.preventDefault();load();};
  node('clear').onclick = () => {node('filters').reset();load();};
  AssetPortal.context(scope => {
    client = scope.client;environment = scope.environment;loadingScope = scope.loading;
    const offset = scope.initial ? Math.max(0, Number(initial.get('offset')) || 0) : 0;
    return load(Number.isSafeInteger(offset) ? offset : 0);
  });
})();
