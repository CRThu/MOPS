/**
 * MOPS Topology Graph — AntV G6 5.x
 *
 * auto-adapt-label: smart label visibility based on density
 * zoom-canvas / drag-canvas / scroll-canvas: smooth zoom/pan
 * FPS + render time overlay
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
let totalNodeCount = 0
let zoomLevelEl: HTMLElement | null = null
let autoFitToggleEl: HTMLElement | null = null
let renderedOnce = false
let lastNodeKey = ''
let lastEdgeKey = ''
let canvasContainer: HTMLElement | null = null
let autoFit = true

/* ─── Performance monitoring ─── */
let fpsEl: HTMLElement | null = null
let perfEl: HTMLElement | null = null
let frameCount = 0
let lastFpsTime = performance.now()
let currentFps = 0
let lastRenderMs = 0

function startFpsLoop() {
  const tick = () => {
    frameCount++
    const now = performance.now()
    if (now - lastFpsTime >= 1000) {
      currentFps = Math.round(frameCount * 1000 / (now - lastFpsTime))
      frameCount = 0
      lastFpsTime = now
      updatePerfUI()
    }
    requestAnimationFrame(tick)
  }
  requestAnimationFrame(tick)
}

function updatePerfUI() {
  if (fpsEl) fpsEl.textContent = `${currentFps} FPS`
  if (perfEl) perfEl.textContent = `render ${lastRenderMs.toFixed(0)}ms`
}

/* ─── Node size ─── */
const NODE_W = 120
const NODE_H = 36

export function createGraph(el: HTMLElement): Graph {
  canvasContainer = el
  startFpsLoop()

  graph = new Graph({
    container: el,
    autoResize: true,
    background: C.bg,
    theme: 'dark',
    layout: {
      type: 'dagre',
      rankdir: 'LR',
      nodesep: 40,
      ranksep: 140,
      marginx: 60,
      marginy: 60,
    },
    node: {
      style: {
        size: [NODE_W, NODE_H],
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
    behaviors: [
      { type: 'zoom-canvas', sensitivity: 1.5, enableOptimize: true },
      { type: 'drag-canvas', enableOptimize: true },
      { type: 'scroll-canvas', direction: 'y' },
      { type: 'auto-adapt-label', padding: 8, throttle: 32 },
    ],
    animation: false,
    zoomRange: [0.05, 5],
  })

  // Track zoom for UI display
  graph.on('aftertransform', () => {
    if (!graph) return
    currentZoom = graph.getZoom()
    updateZoomUI()
  })

  return graph
}

/* ─── Get mouse position relative to canvas (for zoom center) ─── */
function getCanvasCenter(): [number, number] | undefined {
  if (!canvasContainer) return undefined
  const rect = canvasContainer.getBoundingClientRect()
  return [rect.width / 2, rect.height / 2]
}

/* ─── Zoom controls ─── */
export function setupZoomControls(g: Graph) {
  graph = g
  zoomLevelEl = document.getElementById('zoom-level')
  autoFitToggleEl = document.getElementById('zoom-autofit')
  fpsEl = document.getElementById('perf-fps')
  perfEl = document.getElementById('perf-render')
  autoFitToggleEl?.classList.toggle('active', autoFit)
  autoFitToggleEl?.addEventListener('click', () => setAutoFit(!autoFit))

  document.getElementById('zoom-in')?.addEventListener('click', () => zoomBy(1.3))
  document.getElementById('zoom-out')?.addEventListener('click', () => zoomBy(1 / 1.3))
  document.getElementById('zoom-fit')?.addEventListener('click', fitView)

  document.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.target !== document.body) return
    if (e.key === '=' || e.key === '+') { e.preventDefault(); zoomBy(1.3) }
    if (e.key === '-') { e.preventDefault(); zoomBy(1 / 1.3) }
    if (e.key === '0') { e.preventDefault(); fitView() }
  })
}

function zoomBy(factor: number) {
  if (!graph) return
  const origin = getCanvasCenter()
  graph.zoomTo(currentZoom * factor, { duration: 200 }, origin)
}

function fitView() {
  if (!graph) return
  graph.fitView({ padding: 100, duration: 300 })
}

function setAutoFit(on: boolean) {
  autoFit = on
  autoFitToggleEl?.classList.toggle('active', on)
  if (on && graph) {
    graph.fitView({ padding: 100, duration: 300 })
  }
}

function updateZoomUI() {
  if (zoomLevelEl) {
    zoomLevelEl.textContent = `${Math.round(currentZoom * 100)}%`
  }
}

function computeLabel(nodeType: string, data: any): string {
  const fullLabel = data?.label ?? ''
  if (nodeType === 'server' || nodeType === 'offline') {
    const ip = data?.ip ?? ''
    const port = data?.port
    if (ip && port) return `${ip}:${port}`
    if (data?.hostname) return data.hostname
    return fullLabel
  }
  return fullLabel
}

function getEdgeStyle(e: { isActive: boolean; curveOffset?: number }) {
  const base = {
    endArrow: true,
    curveType: 'cubic-horizontal' as const,
    curveOffset: e.curveOffset ?? 0,
  }
  if (e.isActive) {
    return {
      ...base,
      stroke: C.edgeActive,
      lineWidth: 2,
      endArrowFill: C.edgeActive,
      endArrowSize: 6,
    }
  }
  return {
    ...base,
    stroke: C.edgeInactive,
    lineWidth: 1,
    lineDash: [6, 4],
    endArrowFill: C.edgeInactive,
    endArrowSize: 5,
  }
}

export async function updateGraph(g: Graph, data: TopoData) {
  graph = g
  totalNodeCount = data.nodes.length
  const t0 = performance.now()

  const nodeKey = data.nodes.map(n => n.id).sort().join(',')
  const edgeKey = data.edges.map(e => `${e.source}->${e.target}`).sort().join(',')
  const topologyChanged = nodeKey !== lastNodeKey || edgeKey !== lastEdgeKey
  lastNodeKey = nodeKey
  lastEdgeKey = edgeKey

  const nodes = data.nodes.map(n => ({
    id: n.id,
    type: 'rect',
    data: {
      label: computeLabel(n.type, n),
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

  const edges = data.edges.map(e => ({
    id: e.id,
    source: e.source,
    target: e.target,
    data: { active: e.isActive, speed: e.speed },
    style: getEdgeStyle(e),
    animation: e.isActive ? {
      type: 'dash',
      duration: 1200,
      easing: 'linear',
      iterations: Infinity,
    } : undefined,
  }))

  if (topologyChanged || !renderedOnce) {
    g.setData({ nodes, edges })
    await g.render()
    g.fitView({ padding: 100 })
    renderedOnce = true
  } else {
    g.setData({ nodes, edges })
    await g.render()
  }

  // Sync zoom state
  currentZoom = g.getZoom()
  updateZoomUI()

  // Performance tracking
  lastRenderMs = performance.now() - t0
  updatePerfUI()
}
