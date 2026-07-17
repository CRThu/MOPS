/**
 * MOPS Dashboard — main entry
 *
 * 1s polling /api/dashboard, drives topology + cards.
 */

import { createGraph, updateGraph, setupZoomControls } from './topo'
import { renderCards } from './cards'
import { toTopo, fetchStatus } from './data'
import { fmtBytes, fmtSpeed, fmtUptime } from './format'
import type { DashboardStatus } from './types'
import './style.css'

const POLL_INTERVAL = 1000

/* ─── DOM refs ─── */
const $ = (id: string) => document.getElementById(id)!

let graph: ReturnType<typeof createGraph>

/* ─── Mock data for ?mock=SC or ?mock=N ─── */
// ?mock=30     → 30 servers + 1 local client
// ?mock=5s10c  → 5 servers + 10 remote clients
// ?mock=20s20c → 20 servers + 20 remote clients
function parseMockParam(): { servers: number; clients: number } | null {
  const m = location.search.match(/mock=([^&]+)/)
  if (!m) return null
  const v = m[1].toLowerCase()
  const sc = v.match(/^(\d+)s(\d+)c$/)
  if (sc) return { servers: parseInt(sc[1], 10), clients: parseInt(sc[2], 10) }
  const n = parseInt(v, 10)
  return isNaN(n) ? null : { servers: n, clients: 0 }
}

function generateMockStatus(servers: number, clients: number): DashboardStatus {
  const serverNodes = Array.from({ length: servers }, (_, i) => ({
    ip: `10.0.${Math.floor(i / 100)}.${(i % 100) + 1}`,
    port: 10080 + i,
    api_port: 10082 + i,
    hostname: `srv-${String(i + 1).padStart(2, '0')}`,
    fails: Math.random() < 0.1 ? 2 : 0,
    status: 'active' as 'active',
    total_up: Math.floor(Math.random() * 1e9),
    total_down: Math.floor(Math.random() * 1e9),
    active_conns: Math.floor(Math.random() * 20),
    connections: [] as any[],
    speed_up: Math.random() * 1e6,
    speed_down: Math.random() * 1e6,
  }))

  // Generate remote client connections
  const connections: any[] = []
  for (let c = 0; c < clients; c++) {
    const cIp = `192.168.${10 + Math.floor(c / 50)}.${(c % 50) + 1}`
    const cPort = 20000 + c
    const cHost = `pc-${String(c + 1).padStart(2, '0')}`
    // Each client connects to 1-3 random servers
    const nConns = 1 + Math.floor(Math.random() * 3)
    for (let k = 0; k < nConns; k++) {
      const srvIdx = Math.floor(Math.random() * servers)
      const srv = serverNodes[srvIdx]
      connections.push({
        conn_id: `conn-${c}-${k}`,
        client_ip: cIp,
        client_port: cPort,
        client_host: cHost,
        target_host: `${srv.ip}:${srv.port}`,
        target_port: srv.port,
        status: 'active',
        started_at: Date.now() / 1000 - Math.random() * 3600,
        server_node: `${srv.ip}:${srv.port}`,
      })
    }
  }

  return {
    nodes: serverNodes,
    connections,
    total_up: serverNodes.reduce((s, n) => s + n.total_up, 0),
    total_down: serverNodes.reduce((s, n) => s + n.total_down, 0),
    speed_up: serverNodes.reduce((s, n) => s + n.speed_up, 0),
    speed_down: serverNodes.reduce((s, n) => s + n.speed_down, 0),
    active_conns: serverNodes.reduce((s, n) => s + n.active_conns, 0) + clients * 2,
    uptime: 3600,
    mode: 'both',
    strategy: 'random',
    local_client: { ip: '127.0.0.1', port: 10090 },
  }
}

/* ─── refresh cycle ─── */
let lastData: DashboardStatus | null = null

async function refresh() {
  const mock = parseMockParam()
  const d = mock ? generateMockStatus(mock.servers, mock.clients) : await fetchStatus()
  if (!d) return
  lastData = d

  // Header
  $('hdr-uptime').textContent = fmtUptime(d.uptime)

  // Stats bar
  $('stat-traffic').textContent = `${fmtBytes(d.total_up)} ↑ ${fmtBytes(d.total_down)} ↓`
  $('stat-speed').textContent = `${fmtSpeed(d.speed_up)} ↑ ${fmtSpeed(d.speed_down)} ↓`
  $('stat-conns').textContent = String(d.active_conns)

  // Server cards (pure DOM, no async — render first)
  renderCards(
    $('cards-list'),
    $('cards-count'),
    d.nodes,
  )

  // Topology (async, may fail in headless)
  try {
    await updateGraph(graph, toTopo(d))
  } catch { /* G6 may fail in test env */ }
}

/* ─── boot ─── */
function init() {
  graph = createGraph($('topo-container'))
  setupZoomControls(graph)
  refresh()
  setInterval(refresh, POLL_INTERVAL)
}

document.readyState === 'loading'
  ? document.addEventListener('DOMContentLoaded', init)
  : init()
