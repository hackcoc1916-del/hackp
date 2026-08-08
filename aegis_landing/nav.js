/**
 * AEGIS — Shared Navigation Controller
 * Wire up sidebar links, buttons, and keyboard shortcuts across all pages.
 * Include this script at the bottom of every AEGIS page.
 */
(function () {
  // ═══ Sidebar navigation map ═══
  const NAV = {
    'Investigations':    'index.html',
    'Workspace':         'workspace.html',
    'Evidence Library':  'workspace.html',
    'Evidence':          'workspace.html',
    'Knowledge Graph':   'knowledge-graph.html',
    'Timeline':          'timeline.html',
    'Timeline Analysis': 'timeline.html',
    'Search':            'search.html',
    'Review Queue':      'review.html',
    'Review':            'review.html',
    'Reports':           'report.html',
    'Report':            'report.html',
    'Processing':        'processing.html',
    'Capability Monitor':'processing.html',
    'Capabilities':      'processing.html',
    'Workflow Demo':     'workflow.html',
    'Workflow':          'workflow.html',
    'New Investigation': 'goal.html',
  };

  // Fix all sidebar links with href="#"
  document.querySelectorAll('a[href="#"]').forEach(link => {
    const text = link.textContent.replace(/\d+/g, '').trim();
    for (const [label, url] of Object.entries(NAV)) {
      if (text.includes(label) || text === label) {
        link.href = url;
        break;
      }
    }
  });

  // ═══ Button wiring ═══

  // "New Investigation" button (any page)
  const newBtn = document.getElementById('newInvBtn');
  if (newBtn) {
    newBtn.addEventListener('click', () => { window.location.href = 'goal.html'; });
  }

  // Search trigger
  const searchTrigger = document.getElementById('searchTrigger');
  if (searchTrigger) {
    searchTrigger.style.cursor = 'pointer';
    searchTrigger.addEventListener('click', () => { window.location.href = 'search.html'; });
  }

  // Back buttons → index.html
  document.querySelectorAll('.goalbar-back, [title="Back to Investigations"]').forEach(btn => {
    btn.addEventListener('click', () => { window.location.href = 'index.html'; });
  });

  // Investigation rows → workspace.html
  document.querySelectorAll('.inv-row').forEach(row => {
    row.style.cursor = 'pointer';
    row.addEventListener('click', () => {
      row.style.background = 'var(--bg-active)';
      setTimeout(() => { window.location.href = 'workspace.html'; }, 120);
    });
  });

  // ═══ Keyboard shortcuts ═══
  document.addEventListener('keydown', e => {
    // Ctrl/Cmd + K → Search
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault();
      window.location.href = 'search.html';
    }
  });

  // ═══ Topbar navigation buttons ═══
  // "View in Graph" / "Open Knowledge Graph" etc
  document.querySelectorAll('[data-nav]').forEach(el => {
    el.style.cursor = 'pointer';
    el.addEventListener('click', () => {
      const target = el.dataset.nav;
      if (NAV[target]) window.location.href = NAV[target];
      else if (target.endsWith('.html')) window.location.href = target;
    });
  });

  console.log('[AEGIS] Navigation controller loaded');
})();
