import { describe, it, expect } from 'vitest'
import { toTopo } from './data'
import type { DashboardStatus } from './types'

function makeStatus(overrides: Partial<DashboardStatus> = {}): DashboardStatus {
  return {
    nodes: [],
    connections: [],
    total_up: 0,
    total_down: 0,
    speed_up: 0,
    speed_down: 0,
    active_conns: 0,
    uptime: 0,
    mode: 'dashboard',
    strategy: 'mDNS',
    ...overrides,
  }
}

describe('toTopo', () => {
  it('always has App and Internet nodes', () => {
    const topo = toTopo(makeStatus())
    expect(topo.nodes.find((n) => n.id === 'app')).toBeDefined()
    expect(topo.nodes.find((n) => n.id === 'inet')).toBeDefined()
  })

  it('creates placeholder server when no nodes', () => {
    const topo = toTopo(makeStatus())
    const serverNodes = topo.nodes.filter((n) => n.type === 'server')
    expect(serverNodes).toHaveLength(1)
    expect(serverNodes[0].id).toBe('srv-0')
  })

  it('creates server nodes with correct IDs', () => {
    const topo = toTopo(makeStatus({
      nodes: [
        { ip: '10.0.0.1', port: 10080, hostname: 'server-a', fails: 0, status: 'active', total_up: 100, total_down: 200, active_conns: 1, connections: [], speed_up: 0, speed_down: 0 },
        { ip: '10.0.0.2', port: 10080, hostname: 'server-b', fails: 0, status: 'active', total_up: 50, total_down: 50, active_conns: 0, connections: [], speed_up: 0, speed_down: 0 },
      ],
    }))
    const serverNodes = topo.nodes.filter((n) => n.type === 'server')
    expect(serverNodes).toHaveLength(2)
    expect(serverNodes[0].id).toBe('srv-10.0.0.1:10080')
    expect(serverNodes[1].id).toBe('srv-10.0.0.2:10080')
  })

  it('creates single Client node when no connections', () => {
    const topo = toTopo(makeStatus({
      nodes: [
        { ip: '10.0.0.1', port: 10080, hostname: 'server-a', fails: 0, status: 'active', total_up: 100, total_down: 200, active_conns: 1, connections: [], speed_up: 0, speed_down: 0 },
      ],
    }))
    const clientNodes = topo.nodes.filter((n) => n.type === 'client')
    expect(clientNodes).toHaveLength(1)
    expect(clientNodes[0].id).toBe('cli-local')
  })

  it('creates multiple Client nodes from connections', () => {
    const topo = toTopo(makeStatus({
      nodes: [
        { ip: '10.0.0.1', port: 10080, hostname: 'server-a', fails: 0, status: 'active', total_up: 100, total_down: 200, active_conns: 2, connections: [], speed_up: 0, speed_down: 0 },
      ],
      connections: [
        { conn_id: 'c1', client_ip: '192.168.1.10', target_host: 'example.com', target_port: 443, status: 'active', started_at: 100, server_node: '10.0.0.1:10080' },
        { conn_id: 'c2', client_ip: '192.168.1.20', target_host: 'github.com', target_port: 443, status: 'active', started_at: 100, server_node: '10.0.0.1:10080' },
      ],
    }))
    const clientNodes = topo.nodes.filter((n) => n.type === 'client')
    expect(clientNodes).toHaveLength(2)
    expect(clientNodes.map(n => n.id).sort()).toEqual(['cli-192.168.1.10', 'cli-192.168.1.20'])
  })

  it('creates edges from each client to its connected servers', () => {
    const topo = toTopo(makeStatus({
      nodes: [
        { ip: '10.0.0.1', port: 10080, hostname: 'server-a', fails: 0, status: 'active', total_up: 100, total_down: 200, active_conns: 3, connections: [], speed_up: 0, speed_down: 0 },
        { ip: '10.0.0.2', port: 10080, hostname: 'server-b', fails: 0, status: 'active', total_up: 50, total_down: 50, active_conns: 1, connections: [], speed_up: 0, speed_down: 0 },
      ],
      connections: [
        // Client A connects to server-a
        { conn_id: 'c1', client_ip: '192.168.1.10', target_host: 'example.com', target_port: 443, status: 'active', started_at: 100, server_node: '10.0.0.1:10080' },
        // Client B connects to both servers
        { conn_id: 'c2', client_ip: '192.168.1.20', target_host: 'github.com', target_port: 443, status: 'active', started_at: 100, server_node: '10.0.0.1:10080' },
        { conn_id: 'c3', client_ip: '192.168.1.20', target_host: 'api.openai.com', target_port: 443, status: 'active', started_at: 100, server_node: '10.0.0.2:10080' },
      ],
    }))

    // App → 2 Clients
    const appEdges = topo.edges.filter(e => e.source === 'app' && e.target.startsWith('cli-'))
    expect(appEdges).toHaveLength(2)

    // Client A → server-a only
    const cliAEdges = topo.edges.filter(e => e.source === 'cli-192.168.1.10' && e.target.startsWith('srv-'))
    expect(cliAEdges).toHaveLength(1)
    expect(cliAEdges[0].target).toBe('srv-10.0.0.1:10080')

    // Client B → both servers
    const cliBEdges = topo.edges.filter(e => e.source === 'cli-192.168.1.20' && e.target.startsWith('srv-'))
    expect(cliBEdges).toHaveLength(2)
  })

  it('creates edges App → Client → Server → Internet', () => {
    const topo = toTopo(makeStatus({
      nodes: [
        { ip: '10.0.0.1', port: 10080, hostname: 'server-a', fails: 0, status: 'active', total_up: 100, total_down: 200, active_conns: 1, connections: [], speed_up: 0, speed_down: 0 },
      ],
    }))
    // App → Client
    const appToCli = topo.edges.filter(e => e.source === 'app' && e.target === 'cli-local')
    expect(appToCli).toHaveLength(1)
    // Client → Server
    const cliToSrv = topo.edges.filter(e => e.source === 'cli-local' && e.target.startsWith('srv-'))
    expect(cliToSrv).toHaveLength(1)
    // Server → Internet
    const srvToInet = topo.edges.filter(e => e.source.startsWith('srv-') && e.target === 'inet')
    expect(srvToInet).toHaveLength(1)
  })

  it('creates placeholder edges when no servers', () => {
    const topo = toTopo(makeStatus())
    const edges = topo.edges
    // App → Client → srv-0 → Internet
    expect(edges.length).toBe(3)
  })

  it('includes offline nodes', () => {
    const topo = toTopo(makeStatus({
      nodes: [
        { ip: '10.0.0.1', port: 10080, hostname: 'server-a', fails: 0, status: 'active', total_up: 100, total_down: 200, active_conns: 1, connections: [], speed_up: 0, speed_down: 0 },
        { ip: '10.0.0.2', port: 10080, hostname: 'server-b', fails: 0, status: 'offline', total_up: 0, total_down: 0, active_conns: 0, connections: [], speed_up: 0, speed_down: 0, last_seen: 1000 },
      ],
    }))
    const offlineNodes = topo.nodes.filter(n => n.type === 'offline')
    expect(offlineNodes).toHaveLength(1)
    expect(offlineNodes[0].hostname).toBe('server-b')
  })
})
