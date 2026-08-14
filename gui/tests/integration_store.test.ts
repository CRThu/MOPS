import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { mopsStore, type AppState } from '../src/lib/store';
import { api } from '../src/lib/api';

describe('State Layer - mopsStore Integration Tests', () => {
  beforeEach(() => {
    mopsStore.reset();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    mopsStore.stopPolling();
  });

  it('fetchState should update store with fetched API status and nodes', async () => {
    const mockStatus: any = {
      hostname: 'MockPC',
      client_port: 10081,
      speed_up: 500,
      download_dir: './downloads',
      system_proxy: { enabled: false },
    };
    const mockNodes: any[] = [
      { id: '1', hostname: 'Node1', ip: '192.168.1.10', port: 10080, is_me: false },
    ];

    vi.spyOn(api, 'getStatus').mockResolvedValue(mockStatus);
    vi.spyOn(api, 'getNodes').mockResolvedValue(mockNodes);
    vi.spyOn(api, 'getProgress').mockResolvedValue(null);

    await mopsStore.fetchState();

    let state!: AppState;
    mopsStore.subscribe((s) => (state = s))();

    expect(state.isOnline).toBe(true);
    expect(state.status?.hostname).toBe('MockPC');
    expect(state.nodes).toHaveLength(1);
    expect(state.nodes[0].hostname).toBe('Node1');
  });

  it('fetchState should set isOnline to false without setting continuous error toast when API call fails', async () => {
    vi.spyOn(api, 'getStatus').mockRejectedValue(new Error('Connection refused'));

    await mopsStore.fetchState();

    let state!: AppState;
    mopsStore.subscribe((s) => (state = s))();

    expect(state.isOnline).toBe(false);
    expect(state.error).toBeNull();
  });

  it('toggleSystemProxy should call API and update error on failure', async () => {
    vi.spyOn(api, 'getStatus').mockResolvedValue({ system_proxy: { enabled: false } } as any);
    vi.spyOn(api, 'toggleSystemProxy').mockRejectedValue(new Error('Permission Denied'));

    await mopsStore.toggleSystemProxy('127.0.0.1:10081');

    let state!: AppState;
    mopsStore.subscribe((s) => (state = s))();

    expect(state.error).toContain('切换系统代理失败');
  });

  it('saveSystemProxy should call API with set action and update state', async () => {
    vi.spyOn(api, 'toggleSystemProxy').mockResolvedValue({ enabled: true, proxy_server: '127.0.0.1:9090' } as any);
    vi.spyOn(api, 'getStatus').mockResolvedValue({ system_proxy: { enabled: true, proxy_server: '127.0.0.1:9090' } } as any);
    vi.spyOn(api, 'getNodes').mockResolvedValue([]);
    vi.spyOn(api, 'getProgress').mockResolvedValue(null);

    await mopsStore.saveSystemProxy('127.0.0.1:9090');

    expect(api.toggleSystemProxy).toHaveBeenCalledWith('set', '127.0.0.1:9090');

    let state!: AppState;
    mopsStore.subscribe((s) => (state = s))();
    expect(state.status?.system_proxy?.proxy_server).toBe('127.0.0.1:9090');
  });

  it('saveSystemProxy with custom port 127.0.0.1:7897 should pass exact custom port to API', async () => {
    vi.spyOn(api, 'toggleSystemProxy').mockResolvedValue({ enabled: true, proxy_server: '127.0.0.1:7897' } as any);
    vi.spyOn(api, 'getStatus').mockResolvedValue({ system_proxy: { enabled: true, proxy_server: '127.0.0.1:7897' } } as any);
    vi.spyOn(api, 'getNodes').mockResolvedValue([]);
    vi.spyOn(api, 'getProgress').mockResolvedValue(null);

    await mopsStore.saveSystemProxy('127.0.0.1:7897');

    expect(api.toggleSystemProxy).toHaveBeenCalledWith('set', '127.0.0.1:7897');

    let state!: AppState;
    mopsStore.subscribe((s) => (state = s))();
    expect(state.status?.system_proxy?.proxy_server).toBe('127.0.0.1:7897');
  });

  it('updateDownloadDir should call API and update download_dir state', async () => {
    vi.spyOn(api, 'getStatus').mockResolvedValue({ download_dir: './downloads' } as any);
    vi.spyOn(api, 'setDownloadDir').mockResolvedValue({ download_dir: 'E:/Downloads' });
    vi.spyOn(api, 'getNodes').mockResolvedValue([]);
    vi.spyOn(api, 'getProgress').mockResolvedValue(null);

    await mopsStore.updateDownloadDir('E:/Downloads');

    let state!: AppState;
    mopsStore.subscribe((s) => (state = s))();

    expect(api.setDownloadDir).toHaveBeenCalledWith('E:/Downloads');
  });

  it('startFileTransfer should trigger transferFile API call', async () => {
    vi.spyOn(api, 'transferFile').mockResolvedValue({ status: 'started' });

    await mopsStore.startFileTransfer('192.168.1.55', 10080, 'test.txt');

    expect(api.transferFile).toHaveBeenCalledWith('192.168.1.55', 10080, 'test.txt');
  });

  it('updateAdvertise should call updateAdvertise API and trigger state refresh', async () => {
    vi.spyOn(api, 'getStatus').mockResolvedValue({ advertise: '192.168.1.88' } as any);
    vi.spyOn(api, 'getNodes').mockResolvedValue([]);
    vi.spyOn(api, 'getInterfaces').mockResolvedValue([{ name: 'Ethernet', ip: '192.168.1.88', is_virtual: false }]);
    vi.spyOn(api, 'getProgress').mockResolvedValue(null);
    vi.spyOn(api, 'updateAdvertise').mockResolvedValue({ advertise: '192.168.1.88' });

    await mopsStore.updateAdvertise('192.168.1.88');

    expect(api.updateAdvertise).toHaveBeenCalledWith('192.168.1.88');

    let state!: AppState;
    mopsStore.subscribe((s) => (state = s))();
    expect(state.status?.advertise).toBe('192.168.1.88');
    expect(state.interfaces).toHaveLength(1);
  });

  it('launchChrome should call api.launchChrome and return success', async () => {
    vi.spyOn(api, 'launchChrome').mockResolvedValue({ browser: 'chrome', message: '启动成功' });

    const res = await mopsStore.launchChrome();

    expect(api.launchChrome).toHaveBeenCalled();
    expect(res.success).toBe(true);

    let state!: AppState;
    mopsStore.subscribe((s) => (state = s))();
    expect(state.error).toBeNull();
  });

  it('launchChrome should set error in store on API failure', async () => {
    vi.spyOn(api, 'launchChrome').mockRejectedValue(new Error('未检测到 Chrome 浏览器'));

    const res = await mopsStore.launchChrome();

    expect(api.launchChrome).toHaveBeenCalled();
    expect(res.success).toBe(false);

    let state!: AppState;
    mopsStore.subscribe((s) => (state = s))();
    expect(state.error).toBe('未检测到 Chrome 浏览器');
  });
});
