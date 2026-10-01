'use strict';
window.Portal = (() => {
  const sidebar = document.createElement('aside');
  sidebar.id = 'app-sidebar';
  sidebar.innerHTML = `<a class="brand" data-scope-link href="/">VCM<span>Vulnerability & Compliance</span></a>
    <p class="nav-section">Operations</p><nav aria-label="Main navigation">
    <a data-scope-link href="/">Overview</a><a data-scope-link href="/clients.html">Clients & environments</a><a data-scope-link href="/assets.html">Assets</a><a data-scope-link href="/vulnerabilities.html">Vulnerabilities</a><a data-scope-link href="/imports.html">Scan imports</a></nav>
    <p class="sidebar-footer">Operational portal</p>`;
  document.body.prepend(sidebar);
  const skip = document.createElement('a');
  skip.className = 'skip-link'; skip.href = '#main-content'; skip.textContent = 'Skip to content';
  document.body.prepend(skip);
  const header = document.createElement('header');
  header.className = 'app-topbar';
  header.innerHTML = `<button id="menu-toggle" class="secondary" type="button" aria-controls="app-sidebar" aria-expanded="false">Menu</button>
    <div><span class="scope-label">Active scope</span><p id="scope-summary" role="status">Loading scope…</p></div>`;
  sidebar.after(header);
  const main = document.querySelector('main'); main.id = 'main-content'; main.tabIndex = -1;
  const toggle = document.getElementById('menu-toggle');
  const close = () => {document.body.classList.remove('nav-open');toggle.setAttribute('aria-expanded','false');};
  toggle.onclick = () => {
    const open = document.body.classList.toggle('nav-open');
    toggle.setAttribute('aria-expanded',String(open));
  };
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && document.body.classList.contains('nav-open')) {close();toggle.focus();}
  });
  matchMedia('(min-width: 751px)').addEventListener('change',close);
  document.addEventListener('click', event => {
    if (!sidebar.contains(event.target) && !toggle.contains(event.target)) close();
  });
  for (const link of sidebar.querySelectorAll('nav a')) {
    const page = location.pathname === '/asset.html' ? '/assets.html'
      : location.pathname === '/finding.html' ? '/vulnerabilities.html' : location.pathname;
    if (new URL(link.href).pathname === page) link.setAttribute('aria-current','page');
  }
  function scope(client, environment = null) {
    const url = new URL(location.href);
    if (client) url.searchParams.set('tenant_id',client.id); else url.searchParams.delete('tenant_id');
    if (client && environment) url.searchParams.set('environment_id',environment.id); else url.searchParams.delete('environment_id');
    history.replaceState(null,'',url);
    document.getElementById('scope-summary').textContent = client ? `${client.name} / ${environment?.name || 'All environments'}` : 'All clients / Summary';
    for (const link of document.querySelectorAll('[data-scope-link]')) {
      const target = new URL(link.href);
      for (const key of ['tenant_id','environment_id']) {
        if (url.searchParams.has(key)) target.searchParams.set(key,url.searchParams.get(key)); else target.searchParams.delete(key);
      }
      link.href = target.pathname + target.search;
    }
  }
  return {scope};
})();
