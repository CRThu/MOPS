/**
 * MOPS Dashboard — API data fetching and transformation
 */

import type { DashboardStatus, TopoData, TopoNode, TopoEdge, NodeInfo } from './types'

const API_URL = '/api/dashboard'

export async function fetchStatus(): Promise<DashboardStatus | null> {
  try {
    const resp = await fetch(API_URL)
    if (!resp.ok) return null
    return await resp.json()
  } catch {
    return null
  }
}

export function toTopo(status: DashboardStatus): TopoData {
  const nodes: TopoNode[] = []
  const edges: TopoEdge[] = []

  const servers = status.nodes.filter(n => n.status !== 'offline')
  const offline = status.nodes.filter(n => n.status === 'offline')
  const hasLocalClient = status.local_client != null

  // Always add Internet node
  nodes.push({ id: 'inet', type: 'internet', label: 'Internet' })

  if (hasLocalClient) {
    // Integrated mode: App → local Client → Servers
    const localClient = status.local_client!
    const clientId = 'cli-local'
    nodes.push({ id: 'app', type: 'app', label: 'App' })
    nodes.push({
      id: clientId,
      type: 'client',
      label: `${localClient.ip}:${localClient.port}`,
      ip: localClient.ip,
      port: localClient.port,
    })
    edges.push({ id: 'e-app-cli', source: 'app', target: clientId, isActive: true })

    // Client → Servers
    for (const srv of servers) {
      const srvId = `srv-${srv.ip}:${srv.port}`
      const isActive = srv.status === 'active' && (srv.total_up + srv.total_down > 0)
      nodes.push({
        id: srvId,
        type: 'server',
        label: srv.hostname,
        hostname: srv.hostname,
        ip: srv.ip,
        port: srv.port,
        speed_up: srv.speed_up,
        speed_down: srv.speed_down,
        status: srv.status,
      })
      edges.push({
        id: `e-cli-${srvId}`,
        source: clientId,
        target: srvId,
        isActive: srv.status === 'active',
        speed: srv.speed_up + srv.speed_down,
      })
      edges.push({
        id: `e-${srvId}-inet`,
        source: srvId,
        target: 'inet',
        isActive: isActive,
      })
    }

    // Offline nodes
    for (const srv of offline) {
      const srvId = `srv-${srv.ip}:${srv.port}`
      nodes.push({
        id: srvId,
        type: 'offline',
        label: srv.hostname,
        hostname: srv.hostname,
        ip: srv.ip,
        port: srv.port,
        status: 'offline',
      })
      edges.push({ id: `e-cli-${srvId}`, source: clientId, target: srvId, isActive: false })
      edges.push({ id: `e-${srvId}-inet`, source: srvId, target: 'inet', isActive: false })
    }
  } else {
    // Standalone mode: no App node
    // Collect client info: hostname + connected servers
    const clientInfo = new Map<string, { hostname: string; servers: Set<string> }>()
    for (const conn of status.connections) {
      if (conn.server_node) {
        const clientKey = `${conn.client_ip}:${conn.client_port || 0}`
        if (!clientInfo.has(clientKey)) {
          clientInfo.set(clientKey, { hostname: conn.client_host || '', servers: new Set() })
        }
        clientInfo.get(clientKey)!.servers.add(conn.server_node)
        if (conn.client_host && !clientInfo.get(clientKey)!.hostname) {
          clientInfo.get(clientKey)!.hostname = conn.client_host
        }
      }
    }

    if (clientInfo.size === 0 && servers.length === 0 && offline.length === 0) {
      // Empty dashboard: just Internet
    } else if (clientInfo.size === 0) {
      // Servers only, no clients — show Servers → Internet
      for (const srv of servers) {
        const srvId = `srv-${srv.ip}:${srv.port}`
        const isActive = srv.status === 'active' && (srv.total_up + srv.total_down > 0)
        nodes.push({
          id: srvId,
          type: 'server',
          label: srv.hostname,
          hostname: srv.hostname,
          ip: srv.ip,
          port: srv.port,
          speed_up: srv.speed_up,
          speed_down: srv.speed_down,
          status: srv.status,
        })
        edges.push({
          id: `e-${srvId}-inet`,
          source: srvId,
          target: 'inet',
          isActive: isActive,
        })
      }
      for (const srv of offline) {
        const srvId = `srv-${srv.ip}:${srv.port}`
        nodes.push({
          id: srvId,
          type: 'offline',
          label: srv.hostname,
          hostname: srv.hostname,
          ip: srv.ip,
          port: srv.port,
          status: 'offline',
        })
        edges.push({ id: `e-${srvId}-inet`, source: srvId, target: 'inet', isActive: false })
      }
    } else {
      // Has connections — infer clients, no App node

      // Add server nodes
      for (const srv of servers) {
        const srvId = `srv-${srv.ip}:${srv.port}`
        const isActive = srv.status === 'active' && (srv.total_up + srv.total_down > 0)
        nodes.push({
          id: srvId,
          type: 'server',
          label: srv.hostname,
          hostname: srv.hostname,
          ip: srv.ip,
          port: srv.port,
          speed_up: srv.speed_up,
          speed_down: srv.speed_down,
          status: srv.status,
        })
        edges.push({
          id: `e-${srvId}-inet`,
          source: srvId,
          target: 'inet',
          isActive: isActive,
        })
      }

      // Add offline server nodes
      for (const srv of offline) {
        const srvId = `srv-${srv.ip}:${srv.port}`
        nodes.push({
          id: srvId,
          type: 'offline',
          label: srv.hostname,
          hostname: srv.hostname,
          ip: srv.ip,
          port: srv.port,
          status: 'offline',
        })
        edges.push({ id: `e-${srvId}-inet`, source: srvId, target: 'inet', isActive: false })
      }

      // Add client nodes — no App connection in standalone mode
      for (const [clientKey, info] of clientInfo) {
        const [clientIp, clientPort] = clientKey.split(':')
        const clientId = `cli-${clientKey}`
        const portNum = parseInt(clientPort, 10)
        const label = info.hostname
          ? `${info.hostname}:${clientPort}`
          : (portNum ? `Client :${clientPort}` : 'Client')

        nodes.push({
          id: clientId,
          type: 'client',
          label,
          ip: clientIp,
          port: portNum || undefined,
        })

        // Client → Servers it connects to (no App edge)
        if (info.servers && info.servers.size > 0) {
          for (const serverNode of info.servers) {
            const srvId = `srv-${serverNode}`
            const srv = servers.find(s => `${s.ip}:${s.port}` === serverNode)
            const isActive = srv ? srv.status === 'active' : false
            edges.push({
              id: `e-${clientId}-${srvId}`,
              source: clientId,
              target: srvId,
              isActive,
              speed: srv ? srv.speed_up + srv.speed_down : 0,
            })
          }
        } else {
          for (const srv of servers) {
            const srvId = `srv-${srv.ip}:${srv.port}`
            edges.push({
              id: `e-${clientId}-${srvId}`,
              source: clientId,
              target: srvId,
              isActive: srv.status === 'active',
              speed: srv.speed_up + srv.speed_down,
            })
          }
        }
      }
    }
  }

  return { nodes, edges }
}
