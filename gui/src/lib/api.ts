export interface NodeInfo {
  id: string;
  hostname: string;
  ip: string;
  port: number;
  role: string;
  status: string;
  active_conns: number;
  bytes_up: number;
  bytes_down: number;
  last_seen: string;
  is_me: boolean;
}

export interface SystemProxyInfo {
  enabled: boolean;
  proxy_server: string;
  http_proxy: string;
  https_proxy: string;
  no_proxy: string;
}

export interface NetworkInterface {
  name: string;
  ip: string;
  is_virtual: boolean;
}

export interface StatusData {
  hostname: string;
  strategy: string;
  client_port: number;
  server_port: number;
  api_port: number;
  client_enabled: boolean;
  server_enabled: boolean;
  system_proxy: SystemProxyInfo;
  speed_up: number;
  speed_down: number;
  bytes_up: number;
  bytes_down: number;
  total_nodes: number;
  online_nodes: number;
  advertise?: string;
}

export interface ProgressData {
  file_name: string;
  transferred_bytes: number;
  total_bytes: number;
  percentage: number;
  status: string;
  direction: string;
}

export interface ApiResponse<T> {
  code: number;
  message: string;
  total?: number;
  data: T;
}

export class ApiClient {
  private baseUrl: string;

  constructor(baseUrl = 'http://127.0.0.1:10082') {
    this.baseUrl = baseUrl;
  }

  private async request<T>(path: string, options?: RequestInit): Promise<ApiResponse<T>> {
    const url = `${this.baseUrl}${path}`;
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    });

    if (!response.ok) {
      throw new Error(`HTTP Error ${response.status}: ${response.statusText}`);
    }

    return response.json();
  }

  async getStatus(): Promise<StatusData> {
    const res = await this.request<StatusData>('/api/v1/status');
    return res.data;
  }

  async getNodes(): Promise<NodeInfo[]> {
    const res = await this.request<NodeInfo[]>('/api/v1/nodes');
    return res.data || [];
  }

  async toggleSystemProxy(action: 'on' | 'clear' | 'set', proxyAddr?: string): Promise<SystemProxyInfo> {
    const body: Record<string, string> = { action };
    if (proxyAddr) {
      body.proxy_addr = proxyAddr;
    }
    const res = await this.request<SystemProxyInfo>('/api/v1/system-proxy', {
      method: 'POST',
      body: JSON.stringify(body),
    });
    return res.data;
  }

  async toggleClient(enable: boolean): Promise<{ enabled: boolean; port: number }> {
    const res = await this.request<{ enabled: boolean; port: number }>('/api/v1/client', {
      method: 'POST',
      body: JSON.stringify({ enable }),
    });
    return res.data;
  }

  async toggleServer(enable: boolean): Promise<{ enabled: boolean; port: number }> {
    const res = await this.request<{ enabled: boolean; port: number }>('/api/v1/server', {
      method: 'POST',
      body: JSON.stringify({ enable }),
    });
    return res.data;
  }

  async transferFile(targetIp: string, targetPort: number, filePath: string): Promise<any> {
    const query = new URLSearchParams({
      target_ip: targetIp,
      target_port: targetPort.toString(),
      path: filePath,
    });
    const res = await this.request<any>(`/api/v1/files/transfer?${query.toString()}`, {
      method: 'POST',
    });
    return res.data;
  }

  async getProgress(): Promise<ProgressData | null> {
    const res = await this.request<ProgressData>('/api/v1/files/progress');
    return res.data;
  }

  async getInterfaces(): Promise<NetworkInterface[]> {
    const res = await this.request<NetworkInterface[]>('/api/v1/interfaces');
    return res.data || [];
  }

  async updateAdvertise(advertise: string): Promise<{ advertise: string }> {
    const res = await this.request<{ advertise: string }>('/api/v1/config', {
      method: 'POST',
      body: JSON.stringify({ advertise }),
    });
    return res.data;
  }

  async setDownloadDir(downloadDir: string): Promise<{ download_dir: string }> {
    const res = await this.request<{ download_dir: string }>('/api/v1/config', {
      method: 'POST',
      body: JSON.stringify({ download_dir: downloadDir }),
    });
    return res.data;
  }

  async controlService(action: 'install' | 'uninstall' | 'start' | 'stop'): Promise<string> {
    const res = await this.request<string>('/api/v1/service', {
      method: 'POST',
      body: JSON.stringify({ action }),
    });
    if (res.code !== 200) {
      throw new Error(res.message);
    }
    return res.message;
  }
}

export const api = new ApiClient();
