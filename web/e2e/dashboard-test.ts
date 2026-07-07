/**
 * MOPS Dashboard DevTools Test
 * Tests topology rendering with multiple servers and clients
 */

import type { DashboardStatus } from '../../src/types'

// Test data: 3 servers + 3 clients with mixed states
const testStatus: DashboardStatus = {
  nodes: [
    { ip: '10.0.0.1', port: 10080, api_port: 10082, hostname: 'server-us', fails: 0, status: 'active', total_up: 5242880, total_down: 10485760, active_conns: 3, connections: [], speed_up: 4096, speed_down: 8192 },
    { ip: '10.0.0.2', port: 10080, api_port: 10083, hostname: 'server-eu', fails: 0, status: 'active', total_up: 2097152, total_down: 4194304, active_conns: 2, connections: [], speed_up: 2048, speed_down: 4096 },
    { ip: '10.0.0.3', port: 10080, api_port: 10084, hostname: 'server-ap', fails: 0, status: 'active', total_up: 1048576, total_down: 2097152, active_conns: 1, connections: [], speed_up: 1024, speed_down: 2048 },
  ],
  connections: [
    // Client A: Carrot-PC connecting to US and EU servers
    { conn_id: 'c1', client_ip: '192.168.1.10', client_port: 10090, client_host: 'Carrot-PC', target_host: 'amazon.com', target_port: 443, status: 'active', started_at: Date.now() / 1000 - 200, server_node: '10.0.0.1:10080' },
    { conn_id: 'c2', client_ip: '192.168.1.10', client_port: 10090, client_host: 'Carrot-PC', target_host: 'google.com', target_port: 443, status: 'active', started_at: Date.now() / 1000 - 150, server_node: '10.0.0.2:10080' },
    { conn_id: 'c3', client_ip: '192.168.1.10', client_port: 10090, client_host: 'Carrot-PC', target_host: 'youtube.com', target_port: 443, status: 'active', started_at: Date.now() / 1000 - 100, server_node: '10.0.0.1:10080' },
    // Client B: Workstation connecting to US and AP servers
    { conn_id: 'c4', client_ip: '192.168.1.20', client_port: 10091, client_host: 'Workstation', target_host: 'twitter.com', target_port: 443, status: 'active', started_at: Date.now() / 1000 - 80, server_node: '10.0.0.1:10080' },
    { conn_id: 'c5', client_ip: '192.168.1.20', client_port: 10091, client_host: 'Workstation', target_host: 'Line.me', target_port: 443, status: 'active', started_at: Date.now() / 1000 - 50, server_node: '10.0.0.3:10080' },
    // Client C: Laptop connecting to EU server
    { conn_id: 'c6', client_ip: '192.168.1.30', client_port: 10092, client_host: 'Laptop', target_host: 'spotify.com', target_port: 443, status: 'active', started_at: Date.now() / 1000 - 30, server_node: '10.0.0.2:10080' },
    // Completed connections
    { conn_id: 'c7', client_ip: '192.168.1.10', client_port: 10090, client_host: 'Carrot-PC', target_host: 'github.com', target_port: 443, status: 'completed', started_at: Date.now() / 1000 - 500, ended_at: Date.now() / 1000 - 200, server_node: '10.0.0.1:10080' },
    { conn_id: 'c8', client_ip: '192.168.1.30', client_port: 10092, client_host: 'Laptop', target_host: 'stackoverflow.com', target_port: 443, status: 'completed', started_at: Date.now() / 1000 - 400, ended_at: Date.now() / 1000 - 100, server_node: '10.0.0.2:10080' },
  ],
  total_up: 8388608,
  total_down: 16777216,
  speed_up: 7168,
  speed_down: 14336,
  active_conns: 6,
  uptime: 345600,
  mode: 'dashboard',
  strategy: 'mDNS',
  local_client: null,
}

export default testStatus
