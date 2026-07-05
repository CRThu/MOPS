import { describe, it, expect } from 'vitest'
import { toTopo, type ServerStatus } from './main'

function makeStatus(overrides: Partial<ServerStatus> = {}): ServerStatus {
  return {
    nodes: [],
    total_up: 0,
    total_down: 0,
    active_conns: 0,
    connections: [],
    uptime: 0,
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

  it('filters out server self-referencing stats', () => {
    const topo = toTopo(makeStatus({
      nodes: [
        { ip: '10.0.0.1', port: 10080, fails: 0, up: 100, down: 200 },
        { ip: 'server', port: 10080, fails: 0, up: 50, down: 50 },
      ],
    }))
    const serverNodes = topo.nodes.filter((n) => n.type === 'server')
    expect(serverNodes).toHaveLength(1)
    expect(serverNodes[0].id).toContain('10.0.0.1')
  })

  it('creates server nodes with correct IDs', () => {
    const topo = toTopo(makeStatus({
      nodes: [
        { ip: '10.0.0.1', port: 10080, fails: 0, up: 100, down: 200 },
        { ip: '10.0.0.2', port: 10080, fails: 0, up: 50, down: 50 },
      ],
    }))
    const serverNodes = topo.nodes.filter((n) => n.type === 'server')
    expect(serverNodes).toHaveLength(2)
    expect(serverNodes[0].id).toBe('srv-10.0.0.1:10080')
    expect(serverNodes[1].id).toBe('srv-10.0.0.2:10080')
  })

  it('creates one client node per unique client_ip', () => {
    const topo = toTopo(makeStatus({
      nodes: [
        { ip: '10.0.0.1', port: 10080, fails: 0, up: 100, down: 200 },
      ],
      connections: [
        { conn_id: '1', client_ip: '192.168.1.10', target_host: 'example.com', target_port: 443, status: 'active', started_at: 1000 },
        { conn_id: '2', client_ip: '192.168.1.10', target_host: 'api.github.com', target_port: 443, status: 'active', started_at: 1000 },
        { conn_id: '3', client_ip: '192.168.1.20', target_host: 'example.com', target_port: 443, status: 'completed', started_at: 1000 },
      ],
    }))
    const clientNodes = topo.nodes.filter((n) => n.type === 'client' || n.type === 'client-offline')
    expect(clientNodes).toHaveLength(2)
    expect(clientNodes.find((n) => n.id === 'cli-192.168.1.10')).toBeDefined()
    expect(clientNodes.find((n) => n.id === 'cli-192.168.1.20')).toBeDefined()
  })

  it('marks active client with client type', () => {
    const topo = toTopo(makeStatus({
      nodes: [{ ip: '10.0.0.1', port: 10080, fails: 0, up: 100, down: 200 }],
      connections: [
        { conn_id: '1', client_ip: '192.168.1.10', target_host: '10.0.0.1', target_port: 443, status: 'active', started_at: 1000 },
      ],
    }))
    const cli = topo.nodes.find((n) => n.id === 'cli-192.168.1.10')
    expect(cli?.type).toBe('client')
  })

  it('marks offline client with client-offline type', () => {
    const topo = toTopo(makeStatus({
      nodes: [{ ip: '10.0.0.1', port: 10080, fails: 0, up: 100, down: 200 }],
      connections: [
        { conn_id: '1', client_ip: '192.168.1.10', target_host: '10.0.0.1', target_port: 443, status: 'completed', started_at: 1000, ended_at: 2000 },
      ],
    }))
    const cli = topo.nodes.find((n) => n.id === 'cli-192.168.1.10')
    expect(cli?.type).toBe('client-offline')
  })

  it('creates edges App → each Client', () => {
    const topo = toTopo(makeStatus({
      nodes: [{ ip: '10.0.0.1', port: 10080, fails: 0, up: 100, down: 200 }],
      connections: [
        { conn_id: '1', client_ip: '192.168.1.10', target_host: 'example.com', target_port: 443, status: 'active', started_at: 1000 },
        { conn_id: '2', client_ip: '192.168.1.20', target_host: 'example.com', target_port: 443, status: 'active', started_at: 1000 },
      ],
    }))
    const appToCli = topo.edges.filter(
      (e) => e.source === 'app' && e.target.startsWith('cli-')
    )
    expect(appToCli).toHaveLength(2)
  })

  it('creates edges Client → Server it talked to', () => {
    const topo = toTopo(makeStatus({
      nodes: [
        { ip: '10.0.0.1', port: 10080, fails: 0, up: 100, down: 200 },
        { ip: '10.0.0.2', port: 10080, fails: 0, up: 50, down: 50 },
      ],
      connections: [
        { conn_id: '1', client_ip: '192.168.1.10', target_host: '10.0.0.1', target_port: 443, status: 'active', started_at: 1000 },
      ],
    }))
    const cliToSrv = topo.edges.filter(
      (e) => e.source === 'cli-192.168.1.10' && e.target.startsWith('srv-')
    )
    expect(cliToSrv).toHaveLength(1)
    expect(cliToSrv[0].target).toBe('srv-10.0.0.1:10080')
  })

  it('creates App → Servers directly when no connections', () => {
    const topo = toTopo(makeStatus({
      nodes: [{ ip: '10.0.0.1', port: 10080, fails: 0, up: 100, down: 200 }],
    }))
    const appToSrv = topo.edges.filter(
      (e) => e.source === 'app' && e.target.startsWith('srv-')
    )
    expect(appToSrv).toHaveLength(1)
  })

  it('creates Server → Internet edges', () => {
    const topo = toTopo(makeStatus({
      nodes: [{ ip: '10.0.0.1', port: 10080, fails: 0, up: 100, down: 200 }],
    }))
    const srvToInet = topo.edges.filter(
      (e) => e.source.startsWith('srv-') && e.target === 'inet'
    )
    expect(srvToInet).toHaveLength(1)
  })
})
