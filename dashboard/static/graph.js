// Nala Code Graph — D3.js force-directed visualisation
// Fetches from /graph API and renders nodes (Files, Functions, Classes)
// and edges (CONTAINS, IMPORTS, CALLS) as an interactive force graph.

let simulation, svg, link, node, allData = { nodes: [], links: [] };
let activeFilter = 'all';

function loadGraph() {
  document.getElementById('stats').textContent = 'Loading...';
  fetch('/graph')
    .then(r => r.json())
    .then(data => {
      allData = data;
      if (data.error) {
        document.getElementById('stats').textContent = 'Error: ' + data.error;
        return;
      }
      renderGraph(data);
      document.getElementById('stats').textContent =
        `${data.nodes.length} nodes · ${data.links.length} edges`;
    })
    .catch(e => {
      document.getElementById('stats').textContent = 'Cannot connect to server: ' + e.message;
    });
}

function filterType(type) {
  activeFilter = type;
  if (!allData.nodes.length) return;

  const filtered = type === 'all' ? allData : {
    nodes: allData.nodes.filter(n => n.type === type),
    links: allData.links.filter(l => {
      const srcExists = allData.nodes.some(n => n.id === l.source && n.type === type);
      const tgtExists = allData.nodes.some(n => n.id === l.target && n.type === type);
      return srcExists || tgtExists;
    }),
  };
  renderGraph(filtered);
}

function renderGraph(data) {
  const container = document.getElementById('graph');
  container.innerHTML = '';

  const width = container.clientWidth;
  const height = container.clientHeight;

  svg = d3.select('#graph').append('svg')
    .attr('width', width)
    .attr('height', height)
    .call(d3.zoom().scaleExtent([0.1, 4]).on('zoom', e => g.attr('transform', e.transform)));

  const g = svg.append('g');

  // Build a map for link source/target resolution
  const nodeMap = new Map(data.nodes.map(n => [n.id, n]));

  simulation = d3.forceSimulation(data.nodes)
    .force('link', d3.forceLink(data.links)
      .id(d => d.id)
      .distance(60)
      .strength(0.5))
    .force('charge', d3.forceManyBody().strength(-80))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide(12));

  link = g.append('g').selectAll('line')
    .data(data.links)
    .join('line')
    .attr('class', d => 'link ' + (d.rel || ''))
    .attr('stroke-width', 1);

  node = g.append('g').selectAll('g')
    .data(data.nodes)
    .join('g')
    .attr('class', d => 'node ' + d.type)
    .call(d3.drag()
      .on('start', dragStart)
      .on('drag', dragged)
      .on('end', dragEnd))
    .on('mouseover', showTooltip)
    .on('mouseout', hideTooltip);

  const radius = d => d.type === 'File' ? 6 : d.type === 'Class' ? 5 : 4;
  node.append('circle').attr('r', radius);
  node.append('text')
    .attr('x', d => radius(d) + 3)
    .attr('y', 3)
    .text(d => (d.label || d.id || '').split('/').pop().slice(0, 20));

  simulation.on('tick', () => {
    link
      .attr('x1', d => d.source.x)
      .attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x)
      .attr('y2', d => d.target.y);
    node.attr('transform', d => `translate(${d.x},${d.y})`);
  });
}

function dragStart(event, d) {
  if (!event.active) simulation.alphaTarget(0.3).restart();
  d.fx = d.x; d.fy = d.y;
}
function dragged(event, d) { d.fx = event.x; d.fy = event.y; }
function dragEnd(event, d) {
  if (!event.active) simulation.alphaTarget(0);
  d.fx = null; d.fy = null;
}

function showTooltip(event, d) {
  const t = document.getElementById('tooltip');
  t.style.display = 'block';
  t.style.left = (event.clientX + 12) + 'px';
  t.style.top = (event.clientY - 8) + 'px';
  t.innerHTML = `<strong>${d.label || d.id}</strong><br>Type: ${d.type}${d.complexity != null ? '<br>Complexity: ' + d.complexity : ''}`;
}
function hideTooltip() {
  document.getElementById('tooltip').style.display = 'none';
}

// Auto-load on page open
window.addEventListener('load', loadGraph);
