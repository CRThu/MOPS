/**
 * MOPS Dashboard — main entry
 *
 * Polls /api/server every 15s, transforms data, drives G6 topology.
 */
import { createGraph, updateGraph, type TopoData } from './graph'
import './style.css'

/* ─── format helpers ─── */
export const fmtB = (b: number) => {
  if (!b) return '0 B'
  const u = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(b) / Math.log(1024))
  return (b / 1024 ** i).toFixed(1) + ' ' + u[i]
}

export const fmtDur = (sec: number) => {
  if (sec < 60) return `${Math.floor(sec)}s`
  return `${Math.floor(sec / 60)}m ${Math.floor(sec % 60)}s`
}

export const fmtUp = (s: number) => {
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  const m = Math.floor((s % 3600) / 60)
  return (d ? d + 'd ' : '') + (h ? h + 'h ' : '') + m + 'm'
}

/* ─── API types ─── */
export interface ConnInfo {
  conn_id: string
  client_ip: string
  target_host: string
  target_port: number
  status: 'active' | 'completed'
  started_at: number
  ended_at?: number
}

export interface ServerStatus {
  nodes: { ip: string; port: number; fails: number; up: number; down: number }[]
  total_up: number
  total_down: number
  active_conns: number
  connections: ConnInfo[]
  uptime: number
}

/* ─── transform API → TopoData ─── */
export function toTopo(s: ServerStatus): TopoData {
  const nodes: TopoData['nodes'] = [
    { id: 'app', type: 'app', label: 'App' },
    { id: 'inet', type: 'internet', label: 'Internet' },
  ]
  const edges: TopoData['edges'] = []

  /* server nodes (skip self-referencing "server:port" stats key) */
  const servers = s.nodes
    .filter((n) => n.ip !== 'server')
    .map((n) => {
      const id = `srv-${n.ip}:${n.port}`
      nodes.push({ id, type: 'server', label: `${n.ip}:${n.port}` })
      return { id, ip: n.ip, port: n.port, active: n.up + n.down > 0 }
    })

  if (!servers.length) {
    nodes.push({ id: 'srv-0', type: 'server', label: '…' })
    servers.push({ id: 'srv-0', ip: '', port: 0, active: false })
  }

  /* build client nodes from connections — each unique client_ip = one Client */
  const clientMap = new Map<string, { hosts: Set<string>; isActive: boolean }>()
  for (const c of s.connections) {
    let e = clientMap.get(c.client_ip)
    if (!e) { e = { hosts: new Set(), isActive: false }; clientMap.set(c.client_ip, e) }
    e.hosts.add(c.target_host)
    if (c.status === 'active') e.isActive = true
  }

  const clientIds: string[] = []
  for (const [ip, { hosts, isActive }] of clientMap) {
    const cid = `cli-${ip}`
    clientIds.push(cid)
    nodes.push({
      id: cid,
      type: isActive ? 'client' : 'client-offline',
      label: ip,
    })
    /* client → servers it talked to */
    for (const srv of servers) {
      if (hosts.has(srv.ip)) {
        edges.push({ id: `e-${cid}-${srv.id}`, source: cid, target: srv.id, isActive: isActive && srv.active })
      }
    }
  }

  if (!clientIds.length) {
    /* no connections yet: App → Servers directly */
    for (const srv of servers) {
      edges.push({ id: `e-app-${srv.id}`, source: 'app', target: srv.id, isActive: false })
    }
  } else {
    /* App → each Client */
    for (const cid of clientIds) {
      edges.push({ id: `e-app-${cid}`, source: 'app', target: cid, isActive: true })
    }
  }

  /* Servers → Internet */
  for (const srv of servers) {
    edges.push({ id: `e-${srv.id}-inet`, source: srv.id, target: 'inet', isActive: srv.active })
  }

  return { nodes, edges }
}

/* ─── DOM helpers ─── */
const $ = (id: string) => document.getElementById(id)!

/* ─── connection sidebar ─── */
function renderConns(conns: ConnInfo[]) {
  const el = $('conn-list')
  $('conn-count').textContent = String(conns.length)
  if (!conns.length) {
    el.innerHTML = '<div class="empty-hint">Waiting for connections…</div>'
    return
  }
  const sorted = [...conns].sort((a, b) => {
    if (a.status === 'active' && b.status !== 'active') return -1
    if (a.status !== 'active' && b.status === 'active') return 1
    return (b.started_at ?? 0) - (a.started_at ?? 0)
  })
  el.innerHTML = sorted.map((c) => {
    const sec = Math.floor((c.ended_at ?? Date.now() / 1000) - c.started_at)
    return `<div class="conn-card">
      <div class="conn-row">
        <span class="conn-ip">${c.client_ip}</span>
        <span class="conn-status ${c.status}">${c.status}</span>
      </div>
      <div class="conn-target">→ ${c.target_host}:${c.target_port}</div>
      <div class="conn-duration">${fmtDur(sec)}</div>
    </div>`
  }).join('')
}

/* ─── traffic table ─── */
function renderTraffic(nodes: ServerStatus['nodes'], up: number, down: number) {
  const el = $('traffic-table')
  const valid = nodes.filter((n) => n.ip !== 'server')
  if (!valid.length) { el.innerHTML = '<div class="empty-hint">No traffic yet</div>'; return }
  el.innerHTML = `<table>
    <thead><tr><th>Server</th><th style="text-align:right">Up</th><th style="text-align:right">Down</th></tr></thead>
    <tbody>${valid.map((n) =>
      `<tr><td class="tr-addr">${n.ip}:${n.port}</td><td class="tr-up">${fmtB(n.up)}</td><td class="tr-down">${fmtB(n.down)}</td></tr>`
    ).join('')}</tbody>
    <tfoot><tr><td></td><td class="tr-total" colspan="2">Total ${fmtB(up)} ↑ ${fmtB(down)} ↓</td></tr></tfoot>
  </table>`
}

/* ─── poll cycle ─── */
let graph: ReturnType<typeof createGraph>
const POLL = 15_000

async function refresh() {
  try {
    const r = await fetch('/api/server')
    if (!r.ok) return
    const d: ServerStatus = await r.json()

    $('hdr-uptime').textContent = fmtUp(d.uptime)
    $('s-up').textContent = fmtB(d.total_up)
    $('s-down').textContent = fmtB(d.total_down)
    $('s-active').textContent = String(d.active_conns)
    $('s-total').textContent = String(d.connections?.length ?? 0)
    $('s-uptime').textContent = fmtUp(d.uptime)

    await updateGraph(graph, toTopo(d))
    renderConns(d.connections ?? [])
    renderTraffic(d.nodes, d.total_up, d.total_down)
  } catch { /* server offline — keep last state */ }
}

/* ─── boot ─── */
function init() {
  graph = createGraph($('topo-container'))
  refresh()
  setInterval(refresh, POLL)
}

document.readyState === 'loading'
  ? document.addEventListener('DOMContentLoaded', init)
  : init()
