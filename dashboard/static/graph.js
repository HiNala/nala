// Nala Code Graph — D3.js force-directed visualisation
// Handles: load, filter by type, search/highlight, zoom/pan, drag, tooltip

let simulation, svg, linkSel, nodeSel;
let allData = { nodes: [], links: [] };
let activeFilter = 'all';

function _root() {
  return new URLSearchParams(location.search).get('root') || '.';
}

function loadGraph() {
  document.getElementById('stats').textContent = 'Loading…';
  fetch('/graph?project_root=' + encodeURIComponent(_root()))
    .then(r => r.json())
    .then(data => {
      allData = data;
      if (data.error) {
        document.getElementById('stats').textContent = 'Error: ' + data.error;
        return;
      }
      const langStr = Object.entries(data.stats?.languages || {})
        .map(([k,v]) => `${k}:${v}`).join(' · ');
      document.getElementById('stats').textContent =
        `${data.nodes.length} nodes · ${data.links.length} edges · ${langStr}`;
      _renderGraph(data);
    })
    .catch(e => {
      document.getElementById('stats').textContent = 'Connect error: ' + e.message;
    });
}

function filterNodes(type) {
  activeFilter = type;
  if (!allData.nodes.length) return;
  if (type === 'all') { _renderGraph(allData); return; }
  const keep = new Set(allData.nodes.filter(n => n.type === type).map(n => n.id));
  const filtered = {
    nodes: allData.nodes.filter(n => keep.has(n.id)),
    links: allData.links.filter(l => {
      const s = typeof l.source === 'object' ? l.source.id : l.source;
      const t = typeof l.target === 'object' ? l.target.id : l.target;
      return keep.has(s) && keep.has(t);
    }),
  };
  _renderGraph(filtered);
}

function searchNodes(query) {
  if (!nodeSel) return;
  const q = query.toLowerCase().trim();
  nodeSel.classed('highlighted', d =>
    q.length > 0 && (d.id.toLowerCase().includes(q) || (d.label||'').toLowerCase().includes(q))
  );
}

function _renderGraph(data) {
  const container = document.getElementById('panel-graph');
  container.innerHTML = '';
  const W = container.clientWidth, H = container.clientHeight;

  svg = d3.select('#panel-graph').append('svg')
    .attr('id', 'graph-svg')
    .attr('width', W).attr('height', H)
    .call(d3.zoom().scaleExtent([0.05, 8]).on('zoom', e => g.attr('transform', e.transform)));

  const g = svg.append('g');

  // Deep-copy nodes/links so D3 can mutate x/y/vx/vy
  const nodes = data.nodes.map(n => ({ ...n }));
  const links = data.links.map(l => ({ ...l }));

  simulation = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(links).id(d => d.id).distance(55).strength(0.4))
    .force('charge', d3.forceManyBody().strength(-60))
    .force('center', d3.forceCenter(W / 2, H / 2))
    .force('collision', d3.forceCollide(10));

  linkSel = g.append('g').selectAll('line')
    .data(links).join('line')
    .attr('class', d => 'link ' + (d.rel || ''))
    .attr('stroke-width', 1);

  nodeSel = g.append('g').selectAll('g')
    .data(nodes).join('g')
    .attr('class', d => 'node ' + d.type)
    .call(d3.drag()
      .on('start', (e, d) => { if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on('drag',  (e, d) => { d.fx = e.x; d.fy = e.y; })
      .on('end',   (e, d) => { if (!e.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; }))
    .on('mouseover', _showTip)
    .on('mouseout',  _hideTip)
    .on('click', (e, d) => { e.stopPropagation(); _focusNode(d, nodes, links); });

  const r = d => Math.max(4, Math.min(14, 4 + Math.sqrt((d.complexity || 0) + 1)));
  nodeSel.append('circle').attr('r', r);
  nodeSel.append('text')
    .attr('x', d => r(d) + 3).attr('y', 3)
    .text(d => (d.label || d.id || '').split('/').pop().slice(0, 18));

  simulation.on('tick', () => {
    linkSel
      .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
    nodeSel.attr('transform', d => `translate(${d.x},${d.y})`);
  });
}

function _focusNode(d, nodes, links) {
  // Highlight the clicked node and its immediate neighbours
  const neighbourIds = new Set([d.id]);
  links.forEach(l => {
    const s = typeof l.source === 'object' ? l.source.id : l.source;
    const t = typeof l.target === 'object' ? l.target.id : l.target;
    if (s === d.id) neighbourIds.add(t);
    if (t === d.id) neighbourIds.add(s);
  });
  nodeSel.classed('highlighted', n => neighbourIds.has(n.id));
}

function _showTip(event, d) {
  const t = document.getElementById('tooltip');
  t.style.display = 'block';
  t.style.left = (event.clientX + 14) + 'px';
  t.style.top  = (event.clientY - 10) + 'px';
  t.innerHTML =
    `<strong>${d.label || d.id}</strong><br>` +
    `Type: ${d.type}` +
    (d.complexity ? `<br>Complexity: ${d.complexity}` : '') +
    (d.sloc ? `<br>SLOC: ${d.sloc}` : '') +
    (d.language ? `<br>Language: ${d.language}` : '');
}
function _hideTip() { document.getElementById('tooltip').style.display = 'none'; }
