'use strict';
(() => {
  const {node,request,error,text,date,tags,table,badge} = AssetPortal;
  const SCANNERS = {qualys_vmdr:'Qualys VMDR', tenable_nessus:'Tenable Nessus',
    scc_xccdf:'DISA SCC', pingcastle:'PingCastle', purple_knight:'Purple Knight'};
  const query = new URL(location.href).searchParams;
  const tenantId = query.get('tenant_id');
  const findingId = query.get('finding_id');
  let version = 0, finding = null;

  // Return to the exact list URL (filters, page and scroll position included).
  try {
    const position = JSON.parse(sessionStorage.getItem('finding-list-position'));
    node('back-link').href = position?.url || (tenantId ? `/vulnerabilities.html?tenant_id=${tenantId}` : '/vulnerabilities.html');
  } catch {}

  function rows(id, pairs) {
    table(id, pairs.map(([label, value]) => {
      const strong = document.createElement('strong');strong.textContent = label;
      return [strong, value];
    }), 'No data.', 2);
  }

  function setDecisionState() {
    const accepted = node('decision-status').value === 'risk_accepted';
    node('reason-requirement').textContent = accepted ? '(required)' : '(optional)';
    node('decision-expiry').disabled = !accepted;
    if (!accepted) node('decision-expiry').value = '';
  }

  function render(detail) {
    finding = detail.finding;
    node('finding-title').textContent = finding.rule_title;
    node('finding-subtitle').textContent = `${finding.rule_id} · ${finding.kind === 'compliance' ? 'Compliance' : 'Vulnerability'} · ${SCANNERS[finding.scanner] || finding.scanner}`;
    node('status-badge').replaceChildren(badge(finding.status), badge(finding.severity, true));
    node('detail-status').textContent = `Finding #${finding.id} · first seen ${date(finding.first_seen)} · last seen ${date(finding.last_seen)}`;

    const assetLink = document.createElement('a');
    assetLink.href = `/asset.html?tenant_id=${tenantId}&asset_id=${detail.asset.id}`;
    assetLink.textContent = [detail.asset.ip, detail.asset.fqdn, detail.asset.hostname_netbios].filter(Boolean).join(' / ') || 'Unknown identity';
    rows('context-rows', [
      ['Client', scopeClient?.name || '—'],
      ['Environment (snapshot)', detail.environment.name],
      ['Asset', assetLink],
      ['Operating system', detail.asset.os?.trim() ? detail.asset.os : 'Unknown'],
      ['Asset tags', tags(detail.asset.tags)],
      ['Severity', `${finding.severity}${finding.severity_raw ? ` (scanner: ${finding.severity_raw})` : ''}`],
      ['CVSS', finding.cvss_score != null ? `${finding.cvss_score}${finding.cvss_vector ? ' · ' + finding.cvss_vector : ''}` : '—'],
      ['CVEs', (finding.cves || []).join(', ') || '—'],
      ['Port / protocol', finding.port == null ? '—' : `${finding.port}${finding.protocol ? ' / ' + finding.protocol : ''}`],
      ['Scanner', SCANNERS[finding.scanner] || finding.scanner],
      ['Observations', `${finding.occurrence_count ?? 1}`],
    ]);

    const evidence = [
      ['Rule ID', finding.rule_id],
      ['Rule title', finding.rule_title],
    ];
    if (finding.kind === 'compliance') {
      evidence.push(['Benchmark', text(finding.benchmark)], ['Profile', text(finding.profile)], ['Result', text(finding.result)]);
    }
    evidence.push(['Description', finding.description || '—'], ['Solution', finding.solution || '—']);
    if ((finding.affected_objects || []).length) {
      evidence.push(['Affected objects', finding.affected_objects.map(obj => typeof obj === 'object' ? JSON.stringify(obj) : String(obj)).join(' · ')]);
    }
    evidence.push(
      ['First observed (UTC)', date(finding.first_seen)],
      ['Last observed (UTC)', date(finding.last_seen)],
      ['Latest import', detail.provenance.last_import
        ? `${detail.provenance.last_import.filename} · ${SCANNERS[detail.provenance.last_import.scanner] || detail.provenance.last_import.scanner} · ${date(detail.provenance.last_import.created_at)}`
        : '—'],
      ['Closure import', detail.provenance.closed_by_import
        ? `${detail.provenance.closed_by_import.filename} · ${date(detail.provenance.closed_by_import.created_at)}`
        : '—'],
    );
    rows('evidence-rows', evidence);
    node('scanner-output').textContent = finding.scanner_output || 'No scanner output retained for this finding.';

    node('decision-status').value = finding.status;
    node('decision-expiry').value = finding.risk_accepted_until || '';
    if (finding.status_reason) node('decision-reason').value = finding.status_reason;
    setDecisionState();

    const comments = node('comment-list');comments.replaceChildren();
    if (!detail.comments.length) {
      const empty = document.createElement('p');empty.className = 'muted';empty.textContent = 'No comments yet.';comments.append(empty);
    }
    for (const comment of detail.comments) {
      const block = document.createElement('article');
      const head = document.createElement('p');
      head.innerHTML = ''; // never render scanner/user text as HTML
      const author = document.createElement('strong');author.textContent = comment.author;
      head.append(author, document.createTextNode(` · ${date(comment.created_at)}`));
      const body = document.createElement('p');body.textContent = comment.body;
      block.append(head, body);comments.append(block);
    }
    table('history-rows', detail.history.map(item => [
      date(item.changed_at),
      `${item.from_status ? text(item.from_status) : '—'} → ${text(item.to_status)}`,
      item.reason || '—', item.changed_by || '—']), 'No status changes recorded.', 4);
  }

  async function load() {
    const current = ++version;
    error();node('detail-status').textContent = 'Loading finding…';
    try {
      const detail = await request(`/findings/${findingId}?tenant_id=${tenantId}`);
      if (current !== version) return;
      render(detail);
    } catch (exc) {
      if (current === version) {error(exc.message);node('detail-status').textContent = 'Could not load this finding.';}
    }
  }

  node('decision-status').onchange = setDecisionState;
  node('decision-form').onsubmit = async event => {
    event.preventDefault();
    error();node('decision-error').hidden = true;
    const status = node('decision-status').value;
    const reason = node('decision-reason').value.trim();
    const payload = {status, reason: reason || null, changed_by: node('decision-author').value.trim() || null};
    if (status === 'risk_accepted') {
      if (!reason) {node('decision-error').textContent = 'Risk acceptance requires a reason.';node('decision-error').hidden = false;return;}
      if (node('decision-expiry').value) payload.risk_accepted_until = node('decision-expiry').value;
    }
    try {
      await request(`/findings/${findingId}/status?tenant_id=${tenantId}`, payload, 'POST');
      await load();
      node('detail-status').textContent = 'Decision saved for this finding only.';
    } catch (exc) {
      node('decision-error').textContent = exc.message;node('decision-error').hidden = false;
    }
  };
  node('comment-form').onsubmit = async event => {
    event.preventDefault();
    node('comment-error').hidden = true;
    const body = node('comment-body').value.trim();
    if (!body) return;
    try {
      await request(`/findings/${findingId}/comments?tenant_id=${tenantId}`,
        {author: node('comment-author').value.trim() || 'analyst', body}, 'POST');
      node('comment-body').value = '';
      await load();
      node('detail-status').textContent = 'Comment added.';
    } catch (exc) {
      node('comment-error').textContent = exc.message;node('comment-error').hidden = false;
    }
  };

  let scopeClient = null;
  if (!tenantId || !findingId) {
    error('This page needs a client scope and a finding ID. Open a finding from the list.');
    node('detail-status').textContent = '';
  } else {
    // Resolve the client name for the scope summary without blocking the detail.
    request(`/tenants/${tenantId}`).then(client => {
      scopeClient = client;
      Portal.scope(client, null);
    }).catch(() => {});
    load();
  }
})();
