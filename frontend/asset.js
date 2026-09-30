'use strict';
(() => {
  const {node,request,error,text,date,tags,table,badge} = AssetPortal;
  const initial = new URL(location.href).searchParams;
  const assetId = initial.get('asset_id');
  let version = 0;
  function backLink() {
    const query = new URL(location.href).searchParams;query.delete('asset_id');
    node('back-to-assets').href = '/assets.html?' + query;
  }
  backLink();
  const sections = {
    findings:{span:9,empty:'No findings associated with this asset.',row:f => [`${f.rule_id} — ${f.rule_title}`,f.kind,badge(f.severity,true),badge(f.status),f.scanner,f.port == null ? '—' : `${f.port} / ${f.protocol || '—'}`,f.environment_name,date(f.first_seen),date(f.last_seen)]},
    moves:{span:4,empty:'No recorded environment moves.',row:m => [date(m.moved_at),m.from_environment_name || 'Unavailable',m.to_environment_name,m.reason]},
    imports:{span:5,empty:'No proven import references available.',row:i => [date(i.created_at),i.filename,i.scanner,i.environment_name,badge(i.status)]}
  };
  async function loadSection(key, tenantId, epoch, offset = 0) {
    const section = sections[key], sequence = (section.sequence || 0) + 1;section.sequence = sequence;
    const previous = node(key+'-previous'), next = node(key+'-next');
    previous.disabled = true;next.disabled = true;
    node(key+'-status').textContent = 'Loading…';node(key+'-position').textContent = '';
    table(key+'-rows',[],'Loading…',section.span);
    try {
      const data = await request(`/assets/${encodeURIComponent(assetId)}/${key}?tenant_id=${encodeURIComponent(tenantId)}&limit=25&offset=${offset}`);
      if (epoch !== version || sequence !== section.sequence) return;
      node(key+'-status').textContent = `${data.total} ${key} available.`;
      table(key+'-rows',data.items.map(section.row),section.empty,section.span);
      node(key+'-position').textContent = data.items.length ? `${offset+1}–${offset+data.items.length} of ${data.total}` : '0 shown';
      previous.disabled = offset === 0;next.disabled = offset + data.limit >= data.total;
      previous.onclick = () => loadSection(key,tenantId,epoch,Math.max(0,offset-data.limit));
      next.onclick = () => loadSection(key,tenantId,epoch,offset+data.limit);
    } catch (exc) {
      if (epoch !== version || sequence !== section.sequence) return;
      node(key+'-status').textContent = exc.message;
      table(key+'-rows',[],'History data unavailable.',section.span);
    }
  }
  AssetPortal.context(async scope => {
    const epoch = ++version;error();node('asset-detail').hidden = true;
    node('asset-title').textContent = 'Asset details';
    if (scope.loading) {node('detail-status').textContent = 'Loading context…';return;}
    backLink();
    if (!scope.initial) {
      const query = new URLSearchParams();
      if (scope.client) query.set('tenant_id',scope.client.id);
      if (scope.environment) query.set('environment_id',scope.environment.id);
      location.assign('/assets.html?' + query);return;
    }
    if (!scope.client || !assetId) {node('detail-status').textContent = 'Select a client and open an asset from the inventory.';return;}
    node('detail-status').textContent = 'Loading asset…';
    try {
      const asset = await request(`/assets/${encodeURIComponent(assetId)}?tenant_id=${encodeURIComponent(scope.client.id)}`);
      if (epoch !== version) return;
      node('asset-title').textContent = asset.fqdn || asset.ip || asset.hostname_netbios;
      node('asset-fields').replaceChildren();
      for (const [label,value] of [
        ['IP address',asset.ip],['FQDN',asset.fqdn],['NetBIOS',asset.hostname_netbios],
        ['Current operating system',asset.os?.trim() ? asset.os : 'Unknown'],
        ['Current environment',asset.environment_name],['Environment type',asset.environment_kind],
        ['Criticality',`${asset.criticality} / 5`],['Asset tags',tags(asset.tags)],
        ['First observed (UTC)',date(asset.first_seen)],['Last observed (UTC)',date(asset.last_seen)],
        ['Open findings (all snapshots)',`${asset.open_findings} (${asset.open_critical_high} critical/high)`]
      ]) {
        const term = document.createElement('dt'), definition = document.createElement('dd');
        term.textContent = label;definition.textContent = text(value);node('asset-fields').append(term,definition);
      }
      node('asset-detail').hidden = false;node('detail-status').textContent = '';
      await Promise.all(Object.keys(sections).map(key => loadSection(key,scope.client.id,epoch)));
    } catch (exc) {if (epoch === version) {error(exc.message);node('detail-status').textContent = 'Asset unavailable. Return to the inventory or choose another client.';}}
  });
})();
