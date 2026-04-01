// Nala Files Tab — file list from SQLite cache, sortable

let _filesData = [];
let _fileSort = { field: 'symbol_count', dir: -1 };

function loadFiles() {
  const root = new URLSearchParams(location.search).get('root') || '.';
  document.getElementById('stats').textContent = 'Loading…';
  fetch(`/files?project_root=${encodeURIComponent(root)}&limit=500`)
    .then(r => r.json())
    .then(data => {
      _filesData = data;
      document.getElementById('stats').textContent = `${data.length} files indexed`;
      _renderFiles(data);
    })
    .catch(e => {
      document.getElementById('stats').textContent = 'Error: ' + e.message;
    });
}

function _renderFiles(data) {
  const panel = document.getElementById('panel-files');
  if (!data.length) {
    panel.innerHTML = '<div class="empty">No files indexed. Run /scan or /index in the TUI.</div>';
    return;
  }
  const rows = data.map(f =>
    `<tr>
      <td>${_esc(f.path)}</td>
      <td style="color:#4a9eff">${_esc(f.language)}</td>
      <td style="text-align:right;color:#555">${f.symbol_count || 0}</td>
      <td style="text-align:right;color:#444">${_humanSize(f.size_bytes)}</td>
    </tr>`
  ).join('');

  panel.innerHTML = `
    <div style="overflow:auto;height:100%">
      <table class="data-table">
        <thead><tr>
          <th onclick="_sortFiles('path')">Path</th>
          <th onclick="_sortFiles('language')">Language</th>
          <th onclick="_sortFiles('symbol_count')" style="text-align:right">Symbols ▾</th>
          <th onclick="_sortFiles('size_bytes')" style="text-align:right">Size</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

function _sortFiles(field) {
  if (_fileSort.field === field) _fileSort.dir = -_fileSort.dir;
  else { _fileSort.field = field; _fileSort.dir = field === 'path' || field === 'language' ? 1 : -1; }
  const sorted = [..._filesData].sort((a, b) => {
    const av = a[field] ?? '', bv = b[field] ?? '';
    return typeof av === 'number' ? _fileSort.dir * (av - bv) : _fileSort.dir * String(av).localeCompare(String(bv));
  });
  _renderFiles(sorted);
}

function _humanSize(bytes) {
  if (!bytes) return '0 B';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1024 / 1024).toFixed(1) + ' MB';
}
function _esc(s) { return String(s || '').replace(/</g, '&lt;'); }
