/**
 * MOPS Dashboard — Server Status Cards
 */

import type { NodeInfo } from './types'
import { fmtBytes, fmtSpeed, fmtDuration } from './format'

export function renderCards(
  container: HTMLElement,
  countEl: HTMLElement,
  nodes: NodeInfo[],
): void {
  countEl.textContent = String(nodes.length)

  if (nodes.length === 0) {
    container.innerHTML = '<div class="empty-hint">Discovering servers...</div>'
    return
  }

  // Sort: active first, then by hostname
  const sorted = [...nodes].sort((a, b) => {
    if (a.status === 'active' && b.status !== 'active') return -1
    if (a.status !== 'active' && b.status === 'active') return 1
    return a.hostname.localeCompare(b.hostname)
  })

  container.innerHTML = sorted.map(n => {
    const statusClass = n.status
    const statusLabel = n.status.toUpperCase()

    if (n.status === 'offline') {
      return `
        <div class="server-card offline">
          <div class="card-header">
            <span class="card-hostname">${esc(n.hostname)}</span>
            <span class="card-status offline">OFFLINE</span>
          </div>
          <div class="card-ip">${esc(n.ip)}:${n.port}</div>
          <div class="card-metrics">
            <div class="card-metric">
              <span class="card-metric-label">Last Seen</span>
              <span class="card-metric-value">${n.last_seen ? fmtDuration(Date.now() / 1000 - n.last_seen) + ' ago' : '--'}</span>
            </div>
          </div>
        </div>`
    }

    return `
      <div class="server-card ${statusClass}">
        <div class="card-header">
          <span class="card-hostname">${esc(n.hostname)}</span>
          <span class="card-status ${statusClass}">${statusLabel}</span>
        </div>
        <div class="card-ip">${esc(n.ip)}:${n.port}</div>
        <div class="card-metrics">
          <div class="card-metric">
            <span class="card-metric-label">Speed ↑</span>
            <span class="card-metric-value up">${fmtSpeed(n.speed_up)}</span>
          </div>
          <div class="card-metric">
            <span class="card-metric-label">Speed ↓</span>
            <span class="card-metric-value down">${fmtSpeed(n.speed_down)}</span>
          </div>
          <div class="card-metric">
            <span class="card-metric-label">Total ↑</span>
            <span class="card-metric-value up">${fmtBytes(n.total_up)}</span>
          </div>
          <div class="card-metric">
            <span class="card-metric-label">Total ↓</span>
            <span class="card-metric-value down">${fmtBytes(n.total_down)}</span>
          </div>
          <div class="card-metric">
            <span class="card-metric-label">Conns</span>
            <span class="card-metric-value">${n.active_conns}</span>
          </div>
        </div>
      </div>`
  }).join('')
}

function esc(s: string): string {
  const div = document.createElement('div')
  div.textContent = s
  return div.innerHTML
}
