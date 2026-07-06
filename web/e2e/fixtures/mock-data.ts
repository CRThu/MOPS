import type { DashboardStatus } from '../../src/types'

export const mockStatusEmpty: DashboardStatus = {
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
}

export const mockStatusWithServers: DashboardStatus = {
  nodes: [
    { ip: '10.0.0.1', port: 10080, hostname: 'server-a', fails: 0, status: 'active', total_up: 1048576, total_down: 2097152, active_conns: 1, connections: [], speed_up: 1024, speed_down: 2048 },
    { ip: '10.0.0.2', port: 10080, hostname: 'server-b', fails: 0, status: 'active', total_up: 524288, total_down: 1048576, active_conns: 1, connections: [], speed_up: 512, speed_down: 1024 },
  ],
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
  total_up: 1572864,
  total_down: 3145728,
  speed_up: 1536,
  speed_down: 3072,
  active_conns: 2,
  uptime: 86400,
  mode: 'dashboard',
  strategy: 'mDNS',
}

// 3 servers with mixed states: active, circuit-open, offline
export const mockStatusThreeServersMixed: DashboardStatus = {
  nodes: [
    { ip: '10.0.0.1', port: 10080, api_port: 10082, hostname: 'server-alpha', fails: 0, status: 'active', total_up: 5242880, total_down: 10485760, active_conns: 3, connections: [], speed_up: 4096, speed_down: 8192 },
    { ip: '10.0.0.2', port: 10080, api_port: 10082, hostname: 'server-beta', fails: 3, status: 'circuit-open', total_up: 1048576, total_down: 2097152, active_conns: 0, connections: [], speed_up: 0, speed_down: 0 },
    { ip: '10.0.0.3', port: 10080, api_port: 10082, hostname: 'server-gamma', fails: 0, status: 'active', total_up: 2097152, total_down: 4194304, active_conns: 2, connections: [], speed_up: 2048, speed_down: 4096 },
  ],
  connections: [
    { conn_id: 'c1', client_ip: '192.168.1.10', target_host: 'example.com', target_port: 443, status: 'active', started_at: Date.now() / 1000 - 120, server_node: '10.0.0.1:10080' },
    { conn_id: 'c2', client_ip: '192.168.1.10', target_host: 'github.com', target_port: 443, status: 'active', started_at: Date.now() / 1000 - 60, server_node: '10.0.0.1:10080' },
    { conn_id: 'c3', client_ip: '192.168.1.20', target_host: 'api.openai.com', target_port: 443, status: 'active', started_at: Date.now() / 1000 - 30, server_node: '10.0.0.1:10080' },
    { conn_id: 'c4', client_ip: '192.168.1.15', target_host: 'cdn.example.com', target_port: 443, status: 'active', started_at: Date.now() / 1000 - 90, server_node: '10.0.0.3:10080' },
    { conn_id: 'c5', client_ip: '192.168.1.15', target_host: 'static.example.com', target_port: 80, status: 'active', started_at: Date.now() / 1000 - 45, server_node: '10.0.0.3:10080' },
    { conn_id: 'c6', client_ip: '192.168.1.30', target_host: 'old-api.com', target_port: 443, status: 'completed', started_at: Date.now() / 1000 - 600, ended_at: Date.now() / 1000 - 300, server_node: '10.0.0.2:10080' },
  ],
  total_up: 8388608,
  total_down: 16777216,
  speed_up: 6144,
  speed_down: 12288,
  active_conns: 5,
  uptime: 172800,
  mode: 'dashboard',
  strategy: 'mDNS',
}

// 5 servers — stress test for topology rendering
export const mockStatusFiveServers: DashboardStatus = {
  nodes: [
    { ip: '10.0.0.1', port: 10080, hostname: 'srv-1', fails: 0, status: 'active', total_up: 10485760, total_down: 20971520, active_conns: 4, connections: [], speed_up: 8192, speed_down: 16384 },
    { ip: '10.0.0.2', port: 10080, hostname: 'srv-2', fails: 0, status: 'active', total_up: 5242880, total_down: 10485760, active_conns: 2, connections: [], speed_up: 4096, speed_down: 8192 },
    { ip: '10.0.0.3', port: 10080, hostname: 'srv-3', fails: 2, status: 'circuit-open', total_up: 1048576, total_down: 2097152, active_conns: 0, connections: [], speed_up: 0, speed_down: 0 },
    { ip: '10.0.0.4', port: 10080, hostname: 'srv-4', fails: 0, status: 'active', total_up: 2097152, total_down: 4194304, active_conns: 1, connections: [], speed_up: 1024, speed_down: 2048 },
    { ip: '10.0.0.5', port: 10080, hostname: 'srv-5', fails: 5, status: 'offline', total_up: 524288, total_down: 1048576, active_conns: 0, connections: [], speed_up: 0, speed_down: 0 },
  ],
  connections: [
    { conn_id: 'c1', client_ip: '192.168.1.10', target_host: 'example.com', target_port: 443, status: 'active', started_at: Date.now() / 1000 - 120, server_node: '10.0.0.1:10080' },
    { conn_id: 'c2', client_ip: '192.168.1.10', target_host: 'github.com', target_port: 443, status: 'active', started_at: Date.now() / 1000 - 60, server_node: '10.0.0.1:10080' },
    { conn_id: 'c3', client_ip: '192.168.1.20', target_host: 'api.openai.com', target_port: 443, status: 'active', started_at: Date.now() / 1000 - 30, server_node: '10.0.0.2:10080' },
    { conn_id: 'c4', client_ip: '192.168.1.30', target_host: 'cdn.cloudflare.com', target_port: 443, status: 'active', started_at: Date.now() / 1000 - 15, server_node: '10.0.0.4:10080' },
  ],
  total_up: 19398656,
  total_down: 38797312,
  speed_up: 13312,
  speed_down: 26624,
  active_conns: 4,
  uptime: 259200,
  mode: 'dashboard',
  strategy: 'mDNS',
}

// Multiple clients connecting to different servers
export const mockStatusMultipleClients: DashboardStatus = {
  nodes: [
    { ip: '10.0.0.1', port: 10080, hostname: 'server-us', fails: 0, status: 'active', total_up: 4194304, total_down: 8388608, active_conns: 3, connections: [], speed_up: 3072, speed_down: 6144 },
    { ip: '10.0.0.2', port: 10080, hostname: 'server-eu', fails: 0, status: 'active', total_up: 2097152, total_down: 4194304, active_conns: 2, connections: [], speed_up: 1536, speed_down: 3072 },
    { ip: '10.0.0.3', port: 10080, hostname: 'server-ap', fails: 0, status: 'active', total_up: 1048576, total_down: 2097152, active_conns: 1, connections: [], speed_up: 768, speed_down: 1536 },
  ],
  connections: [
    // Client A connects to US and EU servers
    { conn_id: 'c1', client_ip: '192.168.1.10', target_host: 'amazon.com', target_port: 443, status: 'active', started_at: Date.now() / 1000 - 200, server_node: '10.0.0.1:10080' },
    { conn_id: 'c2', client_ip: '192.168.1.10', target_host: 'google.com', target_port: 443, status: 'active', started_at: Date.now() / 1000 - 150, server_node: '10.0.0.2:10080' },
    { conn_id: 'c3', client_ip: '192.168.1.10', target_host: 'youtube.com', target_port: 443, status: 'active', started_at: Date.now() / 1000 - 100, server_node: '10.0.0.1:10080' },
    // Client B connects to US and AP servers
    { conn_id: 'c4', client_ip: '192.168.1.20', target_host: 'twitter.com', target_port: 443, status: 'active', started_at: Date.now() / 1000 - 80, server_node: '10.0.0.1:10080' },
    { conn_id: 'c5', client_ip: '192.168.1.20', target_host: 'Line.me', target_port: 443, status: 'active', started_at: Date.now() / 1000 - 50, server_node: '10.0.0.3:10080' },
    // Client C connects to EU server
    { conn_id: 'c6', client_ip: '192.168.1.30', target_host: 'spotify.com', target_port: 443, status: 'active', started_at: Date.now() / 1000 - 30, server_node: '10.0.0.2:10080' },
    // Completed connections
    { conn_id: 'c7', client_ip: '192.168.1.10', target_host: 'github.com', target_port: 443, status: 'completed', started_at: Date.now() / 1000 - 500, ended_at: Date.now() / 1000 - 200, server_node: '10.0.0.1:10080' },
    { conn_id: 'c8', client_ip: '192.168.1.30', target_host: 'stackoverflow.com', target_port: 443, status: 'completed', started_at: Date.now() / 1000 - 400, ended_at: Date.now() / 1000 - 100, server_node: '10.0.0.2:10080' },
  ],
  total_up: 7340032,
  total_down: 14680064,
  speed_up: 5376,
  speed_down: 10752,
  active_conns: 6,
  uptime: 345600,
  mode: 'dashboard',
  strategy: 'mDNS',
}

// All servers offline — edge case
export const mockStatusAllOffline: DashboardStatus = {
  nodes: [
    { ip: '10.0.0.1', port: 10080, hostname: 'dead-1', fails: 10, status: 'offline', total_up: 0, total_down: 0, active_conns: 0, connections: [], speed_up: 0, speed_down: 0 },
    { ip: '10.0.0.2', port: 10080, hostname: 'dead-2', fails: 10, status: 'offline', total_up: 0, total_down: 0, active_conns: 0, connections: [], speed_up: 0, speed_down: 0 },
  ],
  connections: [],
  total_up: 0,
  total_down: 0,
  speed_up: 0,
  speed_down: 0,
  active_conns: 0,
  uptime: 86400,
  mode: 'dashboard',
  strategy: 'mDNS',
}
