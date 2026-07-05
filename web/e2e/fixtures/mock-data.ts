import type { ServerStatus } from '../../src/main'

export const mockStatusEmpty: ServerStatus = {
  nodes: [],
  total_up: 0,
  total_down: 0,
  active_conns: 0,
  connections: [],
  uptime: 0,
}

export const mockStatusWithServers: ServerStatus = {
  nodes: [
    { ip: '10.0.0.1', port: 10080, fails: 0, up: 1048576, down: 2097152 },
    { ip: '10.0.0.2', port: 10080, fails: 0, up: 524288, down: 1048576 },
  ],
  total_up: 1572864,
  total_down: 3145728,
  active_conns: 2,
  connections: [
    {
      conn_id: '1',
      client_ip: '192.168.1.10',
      target_host: 'example.com',
      target_port: 443,
      status: 'active',
      started_at: Date.now() / 1000 - 60,
    },
    {
      conn_id: '2',
      client_ip: '192.168.1.20',
      target_host: 'api.github.com',
      target_port: 443,
      status: 'completed',
      started_at: Date.now() / 1000 - 300,
      ended_at: Date.now() / 1000 - 120,
    },
  ],
  uptime: 86400,
}
