// Nala Complexity Tab — sortable table of high-complexity functions

let _complexityData = [];
let _ccSortDir = -1; // -1 = desc

function loadComplexity() {
  const threshold = document.getElementById('cc-threshold').value || 5;
  const root = new URLSearchParams(location.search).get('root') || '.';
  document.getElementById('stats').textContent = 'Loading…';
  fetch(`/complexity?project_root=${encodeURIComponent(root)}&threshold=${threshold}&limit=200`)
    .then(r => r.json())
    .then(data => {
      _complexityData = data;
      document.getElementById('stats').textContent = `${data.length} functions above CC ${threshold}`;
      _renderComplexity(data);
    })
    .catch(e => {
      document.getElementById('stats').textContent = 'Error: ' + e.message;
    });
}

function _renderComplexity(data) {
  const panel = document.getElementById('panel-complexity');
  if (!data.length) {
    panel.innerHTML = '<div class="empty">No functions above the threshold — or run /analyze first.</div>';
    return;
  }
  const rows = data.map(d =>
    `<tr>
      <td>${_ccBadge(d.cyclomatic)}</td>
      <td>${d.cognitive || 0}</td>
      <td>${_esc(d.name)}</td>
      <td style="color:#555">${_esc(d.file)}${d.line ? ':' + d.line : ''}</td>
    </tr>`
  ).join('');

  panel.innerHTML = `
    <table class="data-table">
      <thead>
        <tr>
          <th onclick="_sortCC('cyclomatic')">CC ▾</th>
          <th onclick="_sortCC('cognitive')">Cog</th>
          <th onclick="_sortCC('name')">Function</th>
          <th>File</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function _sortCC(field) {
  _ccSortDir = -_ccSortDir;
  const sorted = [..._complexityData].sort((a, b) => {
    const av = a[field] ?? '', bv = b[field] ?? '';
    return typeof av === 'number' ? _ccSortDir * (av - bv) : _ccSortDir * String(av).localeCompare(String(bv));
  });
  _renderComplexity(sorted);
}

function _ccBadge(cc) {
  const cls = cc >= 20 ? 'critical' : cc >= 10 ? 'high' : cc >= 7 ? 'medium' : 'low';
  return `<span class="sev ${cls}">${cc}</span>`;
}
function _esc(s) { return String(s || '').replace(/</g, '&lt;'); }
