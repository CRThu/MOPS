/**
 * MOPS Topology Graph — AntV G6 5.x
 *
 * App → Client → Server阵列 → Internet
 * dagre LR layout, Canvas renderer.
 */
import { Graph } from '@antv/g6'

/* ─── palette ─── */
const C = {
  bg:       '#0d1117',
  app:      { fill: '#64748b', stroke: '#94a3b8' },
  client:   { fill: '#2563eb', stroke: '#60a5fa' },
  server:   { fill: '#16a34a', stroke: '#4ade80' },
  internet: { fill: '#7c3aed', stroke: '#a78bfa' },
  inactive: { fill: '#334155', stroke: '#64748b' },
  'client-offline': { fill: '#1e40af', stroke: '#3b82f6' },
  lineOff:  '#475569',
  lineOn:   '#f59e0b',
}

const PAL: Record<string, { fill: string; stroke: string }> = {
  app: C.app,
  client: C.client,
  'client-offline': C['client-offline'],
  server: C.server,
  internet: C.internet,
}

/* ─── types ─── */
export interface TopoNode { id: string; type: string; label: string }
export interface TopoEdge { id: string; source: string; target: string; isActive: boolean }
export interface TopoData  { nodes: TopoNode[]; edges: TopoEdge[] }

/* ─── create graph ─── */
export function createGraph(el: HTMLElement): Graph {
  return new Graph({
    container: el,
    autoResize: true,
    background: C.bg,
    theme: 'dark',
    layout: {
      type: 'dagre',
      rankdir: 'LR',
      nodesep: 16,
      ranksep: 100,
      marginx: 24,
      marginy: 16,
    },
    node: {
      style: {
        size: [110, 32],
        radius: 6,
        labelText: (d: any) => d.data?.label ?? d.id,
        labelFill: '#e5e7eb',
        labelFontSize: 11,
        labelFontWeight: 500,
        labelPlacement: 'center',
        labelWordWrap: true,
        labelTextOverflow: 'ellipsis',
      },
    },
    edge: {
      style: {
        lineWidth: 1,
        endArrow: true,
        endArrowSize: 5,
        curveType: 'cubic-horizontal',
      },
    },
    animation: false,
  })
}

/* ─── incremental update (no flicker) ─── */
export async function updateGraph(graph: Graph, data: TopoData) {
  const nodes = data.nodes.map((n) => ({
    id: n.id,
    type: 'rect',
    data: { label: n.label, nodeType: n.type },
    style: {
      fill: PAL[n.type]?.fill ?? C.inactive.fill,
      stroke: PAL[n.type]?.stroke ?? C.inactive.stroke,
      lineWidth: 2,
    },
  }))

  const edges = data.edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    data: { active: e.isActive },
    style: {
      stroke: e.isActive ? C.lineOn : C.lineOff,
      lineWidth: e.isActive ? 2.5 : 1,
      lineDash: e.isActive ? [] : [4, 3],
      endArrowFill: e.isActive ? C.lineOn : C.lineOff,
      endArrow: true,
      endArrowSize: 5,
      curveType: 'cubic-horizontal',
    },
  }))

  graph.setData({ nodes, edges })
  await graph.render()
  graph.fitView()
}
