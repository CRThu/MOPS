/**
 * MOPS Dashboard — main entry
 *
 * 1s polling /api/dashboard, drives topology + cards.
 */

import { createGraph, updateGraph } from './topo'
import { renderCards } from './cards'
import { toTopo, fetchStatus } from './data'
import { fmtBytes, fmtSpeed, fmtUptime } from './format'
import type { DashboardStatus } from './types'
import './style.css'

const POLL_INTERVAL = 1000

/* ─── DOM refs ─── */
const $ = (id: string) => document.getElementById(id)!

let graph: ReturnType<typeof createGraph>

/* ─── refresh cycle ─── */
let lastData: DashboardStatus | null = null

async function refresh() {
  const d = await fetchStatus()
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
  refresh()
  setInterval(refresh, POLL_INTERVAL)
}

document.readyState === 'loading'
  ? document.addEventListener('DOMContentLoaded', init)
  : init()
