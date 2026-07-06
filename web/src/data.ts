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
  const nodes: TopoNode[] = [
    { id: 'app', type: 'app', label: 'App' },
    { id: 'inet', type: 'internet', label: 'Internet' },
  ]
  const edges: TopoEdge[] = []

  const servers = status.nodes.filter(n => n.status !== 'offline')
  const offline = status.nodes.filter(n => n.status === 'offline')

  // Extract unique client IPs from connections
  const clientIps = new Set<string>()
  for (const conn of status.connections) {
    clientIps.add(conn.client_ip)
  }

  // If no connections yet, show single placeholder client
  if (clientIps.size === 0) {
    const clientId = 'cli-local'
    nodes.push({
      id: clientId,
      type: 'client',
      label: 'Client',
      ip: '127.0.0.1',
    })

    if (servers.length === 0 && offline.length === 0) {
      nodes.push({ id: 'srv-0', type: 'server', label: '...', status: 'offline' })
      edges.push({ id: 'e-app-cli', source: 'app', target: clientId, isActive: false })
      edges.push({ id: 'e-cli-srv0', source: clientId, target: 'srv-0', isActive: false })
      edges.push({ id: 'e-srv0-inet', source: 'srv-0', target: 'inet', isActive: false })
    } else {
      edges.push({ id: 'e-app-cli', source: 'app', target: clientId, isActive: true })
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

      // Offline nodes (dimmed)
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
        edges.push({
          id: `e-cli-${srvId}`,
          source: clientId,
          target: srvId,
          isActive: false,
        })
        edges.push({
          id: `e-${srvId}-inet`,
          source: srvId,
          target: 'inet',
          isActive: false,
        })
      }
    }
  } else {
    // Multi-client topology: extract unique clients and their server connections
    const clientServers = new Map<string, Set<string>>() // client_ip -> Set<server_node>

    for (const conn of status.connections) {
      if (conn.server_node) {
        if (!clientServers.has(conn.client_ip)) {
          clientServers.set(conn.client_ip, new Set())
        }
        clientServers.get(conn.client_ip)!.add(conn.server_node)
      }
    }

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
      edges.push({
        id: `e-${srvId}-inet`,
        source: srvId,
        target: 'inet',
        isActive: false,
      })
    }

    // Add client nodes and edges
    let clientIdx = 0
    for (const clientIp of clientIps) {
      const clientId = `cli-${clientIp}`
      const label = clientIps.size === 1 ? 'Client' : `Client ${clientIp.split('.').slice(-1)[0]}`

      nodes.push({
        id: clientId,
        type: 'client',
        label,
        ip: clientIp,
      })

      // App → Client
      edges.push({
        id: `e-app-${clientId}`,
        source: 'app',
        target: clientId,
        isActive: true,
      })

      // Client → Servers it connects to
      const connectedServers = clientServers.get(clientIp)
      if (connectedServers && connectedServers.size > 0) {
        for (const serverNode of connectedServers) {
          // serverNode format: "ip:port"
          const srvId = `srv-${serverNode}`
          const srv = servers.find(s => `${s.ip}:${s.port}` === serverNode)
          const isActive = srv ? srv.status === 'active' : false
          edges.push({
            id: `e-${clientId}-${srvId}`,
            source: clientId,
            target: srvId,
            isActive: isActive,
            speed: srv ? srv.speed_up + srv.speed_down : 0,
          })
        }
      } else {
        // No server info — connect to all servers (fallback)
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

      clientIdx++
    }
  }

  return { nodes, edges }
}
