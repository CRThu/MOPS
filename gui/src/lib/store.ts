import { writable } from 'svelte/store';
import { api, type StatusData, type NodeInfo, type ProgressData, type NetworkInterface } from './api';

export interface AppState {
  status: StatusData | null;
  nodes: NodeInfo[];
  interfaces: NetworkInterface[];
  progress: ProgressData | null;
  error: string | null;
  isOnline: boolean;
  isTransferring: boolean;
  lastUpdated: number;
}

const initialState: AppState = {
  status: null,
  nodes: [],
  interfaces: [],
  progress: null,
  error: null,
  isOnline: true,
  isTransferring: false,
  lastUpdated: 0,
};

function createMopsStore() {
  const { subscribe, set, update } = writable<AppState>(initialState);
  let timer: any = null;

  async function fetchState() {
    try {
      const [status, nodes, interfaces, progress] = await Promise.all([
        api.getStatus(),
        api.getNodes(),
        api.getInterfaces().catch(() => []),
        api.getProgress().catch(() => null),
      ]);

      const transferring = progress ? progress.status === 'TRANSFERRING' : false;

      update((state) => ({
        ...state,
        status,
        nodes,
        interfaces,
        progress,
        error: null,
        isOnline: true,
        isTransferring: transferring,
        lastUpdated: Date.now(),
      }));
    } catch (err: any) {
      update((state) => ({
        ...state,
        isOnline: false,
      }));
    }
  }

  function startPolling(intervalMs = 1000) {
    fetchState();
    if (!timer) {
      timer = setInterval(fetchState, intervalMs);
    }
  }

  function stopPolling() {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
  }

  async function toggleSystemProxy(customAddr?: string) {
    try {
      update((s) => ({ ...s, error: null }));
      const current = (await api.getStatus()).system_proxy?.enabled;
      const action = current ? 'clear' : 'on';
      await api.toggleSystemProxy(action, customAddr);
      await fetchState();
    } catch (err: any) {
      update((s) => ({ ...s, error: `切换系统代理失败: ${err.message}` }));
    }
  }

  async function saveSystemProxy(proxyAddr: string) {
    try {
      update((s) => ({ ...s, error: null }));
      await api.toggleSystemProxy('set', proxyAddr);
      await fetchState();
    } catch (err: any) {
      update((s) => ({ ...s, error: `保存系统代理失败: ${err.message}` }));
    }
  }

  async function toggleClient() {
    try {
      update((s) => ({ ...s, error: null }));
      const current = (await api.getStatus()).client_enabled;
      await api.toggleClient(!current);
      await fetchState();
    } catch (err: any) {
      update((s) => ({ ...s, error: `切换 SOCKS5 代理失败: ${err.message}` }));
    }
  }

  async function toggleServer() {
    try {
      update((s) => ({ ...s, error: null }));
      const current = (await api.getStatus()).server_enabled;
      await api.toggleServer(!current);
      await fetchState();
    } catch (err: any) {
      update((s) => ({ ...s, error: `切换 Server 中继失败: ${err.message}` }));
    }
  }

  async function startFileTransfer(targetIp: string, targetPort: number, filePath: string) {
    try {
      update((s) => ({ ...s, error: null, isTransferring: true }));
      await api.transferFile(targetIp, targetPort, filePath);
      await fetchState();
    } catch (err: any) {
      update((s) => ({ ...s, isTransferring: false, error: `文件传输失败: ${err.message}` }));
    }
  }

  async function updateDownloadDir(newDir: string) {
    try {
      update((s) => {
        if (s.status) {
          return {
            ...s,
            status: { ...s.status, download_dir: newDir },
            error: null,
          };
        }
        return { ...s, error: null };
      });
      await api.setDownloadDir(newDir);
      await fetchState();
    } catch (err: any) {
      update((s) => ({ ...s, error: `保存路径更新失败: ${err.message}` }));
    }
  }

  async function updateAdvertise(advertise: string) {
    try {
      update((s) => ({ ...s, error: null }));
      await api.updateAdvertise(advertise);
      await fetchState();
    } catch (err: any) {
      update((s) => ({ ...s, error: `广播网卡更新失败: ${err.message}` }));
    }
  }

  async function launchChrome(): Promise<{ success: boolean; message: string }> {
    try {
      update((s) => ({ ...s, error: null }));
      const res = await api.launchChrome();
      return { success: true, message: res.message || '已成功启动多通道加速版 Chrome' };
    } catch (err: any) {
      const errMsg = err.message || '启动 Chrome 失败';
      update((s) => ({ ...s, error: errMsg }));
      return { success: false, message: errMsg };
    }
  }

  async function openDownloadDir(): Promise<{ success: boolean; message?: string }> {
    try {
      update((s) => ({ ...s, error: null }));
      await api.openDownloadDir();
      return { success: true };
    } catch (err: any) {
      const errMsg = err.message || '打开下载目录失败';
      update((s) => ({ ...s, error: errMsg }));
      return { success: false, message: errMsg };
    }
  }

  function setError(msg: string | null) {
    update((s) => ({ ...s, error: msg }));
  }

  function clearError() {
    update((s) => ({ ...s, error: null }));
  }

  return {
    subscribe,
    fetchState,
    startPolling,
    stopPolling,
    toggleSystemProxy,
    saveSystemProxy,
    toggleClient,
    toggleServer,
    startFileTransfer,
    updateDownloadDir,
    updateAdvertise,
    openDownloadDir,
    launchChrome,
    setError,
    clearError,
    reset: () => set(initialState),
  };
}

export const mopsStore = createMopsStore();
