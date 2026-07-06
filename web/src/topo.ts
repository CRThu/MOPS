/**
 * MOPS Topology Graph — AntV G6 5.x
 *
 * Semantic zoom: far view hides labels, near view shows IP:Port + speed
 * Flowing particles on active edges via lineDash animation
 * Canvas renderer for performance
 */

import { Graph } from '@antv/g6'
import type { TopoData } from './types'

/* ─── Color palette (low-saturation industrial) ─── */
const C = {
  bg:       '#0a0e14',
  app:      { fill: '#374151', stroke: '#6b7280' },
  client:   { fill: '#1e3a5f', stroke: '#3b6d9e' },
  server:   { fill: '#1a3c2a', stroke: '#2d6a4f' },
  offline:  { fill: '#1f2937', stroke: '#374151' },
  internet: { fill: '#2d1b4e', stroke: '#6b21a8' },
  edgeActive: '#2d6a4f',
  edgeInactive: '#374151',
  edgeCircuitOpen: '#9b2226',
}

const PAL: Record<string, { fill: string; stroke: string }> = {
  app: C.app,
  client: C.client,
  server: C.server,
  offline: C.offline,
  internet: C.internet,
}

/* ─── Graph state ─── */
let graph: Graph | null = null
let currentZoom = 1

export function createGraph(el: HTMLElement): Graph {
  graph = new Graph({
    container: el,
    autoResize: true,
    background: C.bg,
    theme: 'dark',
    layout: {
      type: 'dagre',
      rankdir: 'LR',
      nodesep: 40,
      ranksep: 160,
      marginx: 40,
      marginy: 40,
    },
    node: {
      style: {
        size: [120, 36],
        radius: 6,
        labelText: (d: any) => d.data?.label ?? d.id,
        labelFill: '#d1d5db',
        labelFontSize: 11,
        labelFontWeight: 500,
        labelPlacement: 'center',
        labelWordWrap: true,
        labelTextOverflow: 'ellipsis',
      },
    },
    edge: {
      style: {
        lineWidth: 1.5,
        endArrow: true,
        endArrowSize: 6,
        curveType: 'cubic-horizontal',
      },
    },
    animation: false,
  })

  // Track zoom for semantic zoom
  graph.on('zoom', (evt: any) => {
    currentZoom = evt.zoom ?? 1
    updateLabelVisibility()
  })

  return graph
}

function updateLabelVisibility() {
  if (!graph) return
  const nodes = graph.getNodes()
  for (const node of nodes) {
    const model = node.getModel()
    const show = currentZoom >= 0.7
    graph.updateNode(model.id!, {
      style: {
        label: show ? (model.data as any)?.label : '',
      },
    })
  }
}

export async function updateGraph(g: Graph, data: TopoData) {
  graph = g

  const nodes = data.nodes.map(n => ({
    id: n.id,
    type: 'rect',
    data: {
      label: n.label,
      nodeType: n.type,
      hostname: n.hostname,
      ip: n.ip,
      port: n.port,
      speed_up: n.speed_up,
      speed_down: n.speed_down,
      status: n.status,
    },
    style: {
      fill: PAL[n.type]?.fill ?? C.offline.fill,
      stroke: PAL[n.type]?.stroke ?? C.offline.stroke,
      lineWidth: 2,
    },
  }))

  const edges = data.edges.map(e => {
    let strokeColor = C.edgeInactive
    let lineWidth = 1
    let lineDash: number[] | undefined = [4, 3]
    let showParticles = false

    if (e.isActive) {
      strokeColor = C.edgeActive
      lineWidth = 2
      lineDash = undefined
      showParticles = true
    }

    return {
      id: e.id,
      source: e.source,
      target: e.target,
      data: { active: e.isActive, speed: e.speed },
      style: {
        stroke: strokeColor,
        lineWidth,
        lineDash,
        endArrowFill: strokeColor,
        endArrow: true,
        endArrowSize: 6,
        curveType: 'cubic-horizontal',
      },
      animation: showParticles ? {
        type: 'dash',
        duration: 1000,
        easing: 'linear',
        iterations: Infinity,
      } : undefined,
    }
  })

  g.setData({ nodes, edges })
  await g.render()
  g.fitView()
  updateLabelVisibility()
}
