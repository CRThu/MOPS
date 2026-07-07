/**
 * MOPS Dashboard — TypeScript interfaces
 */

export interface ConnInfo {
  conn_id: string
  client_ip: string
  client_port?: number
  client_host?: string
  target_host: string
  target_port: number
  status: 'active' | 'completed'
  started_at: number
  ended_at?: number
  server_node?: string
}

export interface NodeInfo {
  ip: string
  port: number
  api_port?: number
  hostname: string
  fails: number
  status: 'active' | 'circuit-open' | 'offline'
  total_up: number
  total_down: number
  active_conns: number
  connections: ConnInfo[]
  speed_up: number
  speed_down: number
  last_seen?: number
}

export interface DashboardStatus {
  nodes: NodeInfo[]
  connections: ConnInfo[]
  total_up: number
  total_down: number
  speed_up: number
  speed_down: number
  active_conns: number
  uptime: number
  mode: string
  strategy: string
  local_client?: { ip: string; port: number } | null
}

export interface TopoNode {
  id: string
  type: 'app' | 'client' | 'server' | 'internet' | 'offline'
  label: string
  hostname?: string
  ip?: string
  port?: number
  speed_up?: number
  speed_down?: number
  status?: string
}

export interface TopoEdge {
  id: string
  source: string
  target: string
  isActive: boolean
  speed?: number
}

export interface TopoData {
  nodes: TopoNode[]
  edges: TopoEdge[]
}
