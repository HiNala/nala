// Nala Findings Tab — sortable, filterable findings table with CSV export

let _findingsData = [];
let _findSort = { field: 'severity', dir: 1 };
let _activeSevs = new Set(['critical','high','medium','low','info']);

function loadFindings() {
  const root = new URLSearchParams(location.search).get('root') || '.';
  const sid  = (document.getElementById('session-id')?.value || '').trim() || 'latest';
  document.getElementById('stats').textContent = 'Loading…';
  fetch(`/findings?project_root=${encodeURIComponent(root)}&session_id=${encodeURIComponent(sid)}`)
    .then(r => r.json())
    .then(data => {
      _findingsData = data;
      document.getElementById('stats').textContent = `${data.length} findings`;
      _renderFindings();
    })
    .catch(e => {
      document.getElementById('stats').textContent = 'Error: ' + e.message;
    });
}

function _renderFindings() {
  const panel = document.getElementById('panel-findings');
  const visible = _findingsData.filter(f => _activeSevs.has(f.severity));

  if (!_findingsData.length) {
    panel.innerHTML = '<div class="empty">No findings. Run /analyze in the TUI first.</div>';
    return;
  }

  // Severity filter checkboxes
  const sevCounts = {};
  _findingsData.forEach(f => { sevCounts[f.severity] = (sevCounts[f.severity]||0)+1; });
  const filterHtml = ['critical','high','medium','low','info'].map(s =>
    `<label style="font-size:0.72rem;cursor:pointer;margin-right:10px">
       <input type="checkbox" ${_activeSevs.has(s)?'checked':''} onchange="_toggleSev('${s}',this.checked)" />
       <span class="sev ${s}">${s}</span> ${sevCounts[s]||0}
     </label>`
  ).join('');

  const rows = visible.map(f =>
    `<tr title="${_esc(f.recommendation)}">
      <td><span class="sev ${f.severity}">${f.severity}</span></td>
      <td style="color:#555">${_esc(f.perspective)}</td>
      <td>${_esc(f.title)}</td>
      <td style="color:#555">${_esc(f.file)}${f.line ? ':'+f.line : ''}</td>
      <td style="color:#444;font-size:0.7rem">${_esc(f.message).slice(0,80)}</td>
    </tr>`
  ).join('');

  panel.innerHTML = `
    <div style="padding:6px 12px;background:#0f0f1a;border-bottom:1px solid #1a1a28;display:flex;align-items:center;gap:4px;flex-wrap:wrap">
      ${filterHtml}
      <button onclick="_exportCSV()" style="margin-left:auto">Export CSV</button>
    </div>
    <div style="overflow:auto;height:calc(100% - 36px)">
      <table class="data-table">
        <thead><tr>
          <th onclick="_sortFindings('severity')">Severity</th>
          <th onclick="_sortFindings('perspective')">Category</th>
          <th onclick="_sortFindings('title')">Title</th>
          <th onclick="_sortFindings('file')">File</th>
          <th>Description</th>
        </tr></thead>
        <tbody>${rows || '<tr><td colspan="5" class="empty">No findings match the current filter.</td></tr>'}</tbody>
      </table>
    </div>`;
}

function _toggleSev(sev, checked) {
  if (checked) _activeSevs.add(sev); else _activeSevs.delete(sev);
  _renderFindings();
}

function _sortFindings(field) {
  if (_findSort.field === field) _findSort.dir = -_findSort.dir;
  else { _findSort.field = field; _findSort.dir = 1; }
  const sevRank = s => ({critical:0,high:1,medium:2,low:3,info:4}[s]??9);
  _findingsData.sort((a,b) => {
    const av = field === 'severity' ? sevRank(a[field]) : a[field]??'';
    const bv = field === 'severity' ? sevRank(b[field]) : b[field]??'';
    return typeof av === 'number' ? _findSort.dir*(av-bv) : _findSort.dir*String(av).localeCompare(String(bv));
  });
  _renderFindings();
}

function _exportCSV() {
  const header = 'severity,perspective,title,file,line,message,recommendation\n';
  const rows = _findingsData.map(f =>
    [f.severity,f.perspective,f.title,f.file,f.line,f.message,f.recommendation]
      .map(v => '"' + String(v||'').replace(/"/g,'""') + '"').join(',')
  ).join('\n');
  const blob = new Blob([header+rows], {type:'text/csv'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'nala-findings.csv';
  a.click();
}

function _esc(s) { return String(s||'').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
