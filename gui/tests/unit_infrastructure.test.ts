import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ApiClient } from '../src/lib/api';

describe('Infrastructure Layer - ApiClient Unit Tests', () => {
  let api: ApiClient;
  const mockBaseUrl = 'http://127.0.0.1:10082';

  beforeEach(() => {
    api = new ApiClient(mockBaseUrl);
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('getStatus should fetch and parse status response correctly', async () => {
    const mockStatusData = {
      code: 200,
      message: 'success',
      data: {
        hostname: 'TestHost',
        client_port: 10081,
        server_port: 10080,
        api_port: 10082,
        speed_up: 1024,
        speed_down: 2048,
        download_dir: './downloads',
        system_proxy: { enabled: true },
      },
    };

    (fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => mockStatusData,
    });

    const status = await api.getStatus();
    expect(fetch).toHaveBeenCalledWith(`${mockBaseUrl}/api/v1/status`, expect.any(Object));
    expect(status.hostname).toBe('TestHost');
    expect(status.speed_up).toBe(1024);
    expect(status.system_proxy.enabled).toBe(true);
  });

  it('getNodes should return empty array if data is null', async () => {
    (fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ code: 200, message: 'success', data: null }),
    });

    const nodes = await api.getNodes();
    expect(nodes).toEqual([]);
  });

  it('toggleSystemProxy should send POST request with action parameter and optional proxy_addr', async () => {
    (fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        code: 200,
        message: 'success',
        data: { enabled: true, proxy_server: '127.0.0.1:9090' },
      }),
    });

    const res = await api.toggleSystemProxy('set', '127.0.0.1:9090');
    expect(fetch).toHaveBeenCalledWith(
      `${mockBaseUrl}/api/v1/system-proxy`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ action: 'set', proxy_addr: '127.0.0.1:9090' }),
      })
    );
    expect(res.enabled).toBe(true);
    expect(res.proxy_server).toBe('127.0.0.1:9090');
  });

  it('controlService should send POST request to /api/v1/service with action', async () => {
    (fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        code: 200,
        message: 'service action install executed successfully',
        data: null,
      }),
    });

    const msg = await api.controlService('install');
    expect(fetch).toHaveBeenCalledWith(
      `${mockBaseUrl}/api/v1/service`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ action: 'install' }),
      })
    );
    expect(msg).toContain('install');
  });

  it('setDownloadDir should send POST request to /api/v1/config', async () => {
    (fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        code: 200,
        message: 'config updated successfully',
        data: { download_dir: 'D:/Downloads' },
      }),
    });

    const res = await api.setDownloadDir('D:/Downloads');
    expect(fetch).toHaveBeenCalledWith(
      `${mockBaseUrl}/api/v1/config`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ download_dir: 'D:/Downloads' }),
      })
    );
    expect(res.download_dir).toBe('D:/Downloads');
  });

  it('getInterfaces should fetch and return network interfaces', async () => {
    (fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        code: 200,
        message: 'success',
        data: [{ name: 'eth0', ip: '192.168.1.100', is_virtual: false }],
      }),
    });

    const ifaces = await api.getInterfaces();
    expect(fetch).toHaveBeenCalledWith(`${mockBaseUrl}/api/v1/interfaces`, expect.any(Object));
    expect(ifaces).toHaveLength(1);
    expect(ifaces[0].ip).toBe('192.168.1.100');
  });

  it('updateAdvertise should send POST request to /api/v1/config with advertise payload', async () => {
    (fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        code: 200,
        message: 'config updated successfully',
        data: { advertise: '192.168.1.200' },
      }),
    });

    const res = await api.updateAdvertise('192.168.1.200');
    expect(fetch).toHaveBeenCalledWith(
      `${mockBaseUrl}/api/v1/config`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ advertise: '192.168.1.200' }),
      })
    );
    expect(res.advertise).toBe('192.168.1.200');
  });

  it('should throw error when HTTP response is not ok (e.g. 500)', async () => {
    (fetch as any).mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
    });

    await expect(api.getStatus()).rejects.toThrow('HTTP Error 500');
  });
});

describe('Tauri Capabilities Adapter Unit Tests', () => {
  it('minimizeWindow, closeWindow, and startDragWindow should execute gracefully without throwing in fallback environment', async () => {
    const { minimizeWindow, closeWindow, startDragWindow } = await import('../src/lib/tauri');
    await expect(minimizeWindow()).resolves.not.toThrow();
    await expect(closeWindow()).resolves.not.toThrow();
    await expect(startDragWindow()).resolves.not.toThrow();
  });
});

