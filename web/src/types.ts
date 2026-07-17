/**
 * MOPS Dashboard — TypeScript interfaces
 *
 * Shared type definitions for API responses and topology graph data.
 */

/** Active or completed connection tracked by the server. */
export interface ConnInfo {
  /** Unique connection identifier (auto-incremented). */
  conn_id: string
  /** Client IP address. */
  client_ip: string
  /** Client listening port (if reported). */
  client_port?: number
  /** Client hostname (if reported). */
  client_host?: string
  /** Target host the client connected to. */
  target_host: string
  /** Target port. */
  target_port: number
  /** Connection state. */
  status: 'active' | 'completed'
  /** Monotonic timestamp when connection started. */
  started_at: number
  /** Monotonic timestamp when connection ended (completed only). */
  ended_at?: number
  /** Server node key (ip:port) — filled by Dashboard aggregation. */
  server_node?: string
}

/** Server node info returned by /api/server or /api/dashboard. */
export interface NodeInfo {
  /** Node IP address. */
  ip: string
  /** Server TCP port. */
  port: number
  /** REST API port (if advertised via mDNS). */
  api_port?: number
  /** Server hostname. */
  hostname: string
  /** Consecutive connection failures (circuit breaker). */
  fails: number
  /** Node health status. */
  status: 'active' | 'offline'
  /** Total upload bytes. */
  total_up: number
  /** Total download bytes. */
  total_down: number
  /** Currently active connections through this node. */
  active_conns: number
  /** Active and recent connections. */
  connections: ConnInfo[]
  /** Upload speed in bytes/sec. */
  speed_up: number
  /** Download speed in bytes/sec. */
  speed_down: number
  /** Monotonic timestamp of last mDNS seen (offline nodes only). */
  last_seen?: number
}

/** Top-level API response from /api/server or /api/dashboard. */
export interface DashboardStatus {
  /** All known server nodes. */
  nodes: NodeInfo[]
  /** Aggregated connections across all servers. */
  connections: ConnInfo[]
  /** Total upload bytes across all nodes. */
  total_up: number
  /** Total download bytes across all nodes. */
  total_down: number
  /** Aggregate upload speed (bytes/sec). */
  speed_up: number
  /** Aggregate download speed (bytes/sec). */
  speed_down: number
  /** Total active connections across all nodes. */
  active_conns: number
  /** Seconds since the reporting process started. */
  uptime: number
  /** Run mode: 'server' | 'client' | 'both' | 'dashboard'. */
  mode: string
  /** Load balance strategy. */
  strategy: string
  /** Local client address (only in integrated both/client mode). */
  local_client?: { ip: string; port: number } | null
}

/** Topology graph node for AntV G6 rendering. */
export interface TopoNode {
  /** Unique node ID (e.g. 'cli-local', 'srv-10.0.0.1:10080'). */
  id: string
  /** Visual node type controlling color and shape. */
  type: 'app' | 'client' | 'server' | 'internet' | 'offline'
  /** Display label. */
  label: string
  /** Server hostname (server/offline only). */
  hostname?: string
  /** IP address. */
  ip?: string
  /** Port number. */
  port?: number
  /** Upload speed (bytes/sec). */
  speed_up?: number
  /** Download speed (bytes/sec). */
  speed_down?: number
  /** Health status. */
  status?: string
}

/** Topology graph edge for AntV G6 rendering. */
export interface TopoEdge {
  /** Unique edge ID. */
  id: string
  /** Source node ID. */
  source: string
  /** Target node ID. */
  target: string
  /** Whether the connection is actively flowing. */
  isActive: boolean
  /** Combined speed (bytes/sec) for edge thickness. */
  speed?: number
}

/** Complete topology data passed to updateGraph(). */
export interface TopoData {
  /** All visible nodes. */
  nodes: TopoNode[]
  /** All edges between nodes. */
  edges: TopoEdge[]
}
