
<script lang="ts">
  import { mopsStore } from '../lib/store';
  import type { StatusData } from '../lib/api';
  import { minimizeWindow, closeWindow, startDragWindow } from '../lib/tauri';
  import { Shield, ArrowUpRight, ArrowDownLeft, Minus, X, Zap } from 'lucide-svelte';

  export let status: StatusData | null = null;

  let proxyAddrInput = '';
  let isEditing = false;
  let lastBackendServer = '';

  $: if (status) {
    const backendServer = status.system_proxy?.proxy_server || '';
    if (!isEditing && backendServer !== lastBackendServer) {
      lastBackendServer = backendServer;
      proxyAddrInput = backendServer || `127.0.0.1:${status.client_port || 10081}`;
    }
  }

  function cleanProxyInput(input: string): string {
    let addr = input.trim();
    if (!addr) return `127.0.0.1:${status?.client_port || 10081}`;
    if (addr.includes('://')) {
      addr = addr.split('://')[1];
    }
    addr = addr.replace(/\/$/, '');
    if (/^\d+$/.test(addr)) {
      return `127.0.0.1:${addr}`;
    }
    return addr;
  }

  async function handleSaveProxy() {
    const cleaned = cleanProxyInput(proxyAddrInput);
    proxyAddrInput = cleaned;
    await mopsStore.saveSystemProxy(cleaned);
    lastBackendServer = cleaned;
    isEditing = false;
  }

  async function handleSetMopsProxy() {
    const mopsAddr = `127.0.0.1:${status?.client_port || 10081}`;
    proxyAddrInput = mopsAddr;
    await mopsStore.saveSystemProxy(mopsAddr);
    lastBackendServer = mopsAddr;
    isEditing = false;
  }

  function formatSpeed(bytesPerSec: number | undefined): string {
    if (!bytesPerSec || bytesPerSec <= 0) return '0.0 B/s';
    const units = ['B/s', 'KB/s', 'MB/s', 'GB/s'];
    let i = 0;
    let val = bytesPerSec;
    while (val >= 1024 && i < units.length - 1) {
      val /= 1024;
      i++;
    }
    return `${val.toFixed(1)} ${units[i]}`;
  }
</script>

<header class="relative glass-panel p-3 border-b border-white/10 shadow-md select-none">
  <!-- Ambient Gradient Light -->
  <div class="absolute -top-10 left-1/2 -translate-x-1/2 w-40 h-10 bg-blue-500/15 blur-2xl rounded-full pointer-events-none"></div>

  <!-- Top Bar (Title Only Draggable Region) -->
  <div class="flex items-center justify-between mb-2.5 relative z-10 cursor-move" data-tauri-drag-region on:mousedown={startDragWindow}>

    <div class="flex items-center space-x-2" data-tauri-drag-region>
      <div class="relative flex items-center justify-center">
        {#if status && $mopsStore.isOnline}
          <div class="w-2 h-2 rounded-full bg-emerald-400"></div>
          <div class="absolute w-3.5 h-3.5 rounded-full bg-emerald-400/40 animate-ping"></div>
        {:else}
          <div class="w-2 h-2 rounded-full bg-rose-500"></div>
          <div class="absolute w-3.5 h-3.5 rounded-full bg-rose-500/40 animate-ping"></div>
        {/if}
      </div>

      <div class="flex items-center space-x-1.5" data-tauri-drag-region>
        <h1 class="text-xs font-black tracking-wider bg-gradient-to-r from-blue-400 via-indigo-200 to-emerald-300 bg-clip-text text-transparent uppercase">
          MOPS Proxy
        </h1>
        {#if status && $mopsStore.isOnline}
          <span class="text-[9px] font-mono bg-slate-800/90 text-blue-300 border border-blue-500/30 px-1.5 py-0.2 rounded shadow-sm">
            :{status.client_port} SOCKS5
          </span>
        {:else}
          <span class="text-[9px] font-mono bg-rose-950/80 text-rose-300 border border-rose-500/40 px-1.5 py-0.2 rounded shadow-sm animate-pulse">
            未连接后台 (重连中...)
          </span>
        {/if}
      </div>
    </div>

    <!-- Window Control Buttons (Minimize to Tray & Close) -->
    <div class="flex items-center space-x-1" on:mousedown|stopPropagation>
      <button
        on:click={minimizeWindow}
        aria-label="最小化到托盘"
        title="最小化到托盘"
        class="p-1 text-slate-400 hover:text-slate-100 hover:bg-slate-800/80 rounded-md transition-all duration-150 active:scale-95 border border-transparent hover:border-slate-700 cursor-pointer"
      >
        <Minus class="w-3.5 h-3.5" />
      </button>

      <button
        on:click={closeWindow}
        aria-label="关闭应用"
        title="关闭应用"
        class="p-1 text-slate-400 hover:text-rose-400 hover:bg-rose-950/40 rounded-md transition-all duration-150 active:scale-95 border border-transparent hover:border-rose-900/50 cursor-pointer"
      >
        <X class="w-3.5 h-3.5" />
      </button>
    </div>
  </div>

  <!-- Realtime Speed & Proxy Control Card -->
  <div class="glass-card rounded-xl p-2.5 border border-white/5 shadow-inner space-y-2 relative z-10 cursor-default">
    <!-- Speed Board -->
    <div class="grid grid-cols-2 gap-2 pb-2 border-b border-slate-800/80">
      <!-- Upload Speed -->
      <div class="flex items-center space-x-2 bg-slate-900/70 p-2 rounded-lg border border-slate-800/80 shadow-sm">
        <div class="p-1 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 shrink-0">
          <ArrowUpRight class="w-3 h-3" />
        </div>
        <div class="min-w-0">
          <div class="text-[8px] text-slate-400 uppercase tracking-widest font-semibold">上行 UPLOAD</div>
          <div class="text-[11px] font-bold font-mono text-slate-100 truncate tracking-tight">
            {formatSpeed(status?.speed_up)}
          </div>
        </div>
      </div>

      <!-- Download Speed -->
      <div class="flex items-center space-x-2 bg-slate-900/70 p-2 rounded-lg border border-slate-800/80 shadow-sm">
        <div class="p-1 rounded bg-blue-500/10 border border-blue-500/20 text-blue-400 shrink-0">
          <ArrowDownLeft class="w-3 h-3" />
        </div>
        <div class="min-w-0">
          <div class="text-[8px] text-slate-400 uppercase tracking-widest font-semibold">下行 DOWNLOAD</div>
          <div class="text-[11px] font-bold font-mono text-slate-100 truncate tracking-tight">
            {formatSpeed(status?.speed_down)}
          </div>
        </div>
      </div>
    </div>

    <!-- System Proxy Control Panel -->
    <div class="pt-0.5 px-0.5 space-y-1.5">
      <div class="flex items-center justify-between">
        <div class="flex items-center space-x-2">
          <div class="p-0.5 rounded {status?.system_proxy?.enabled ? 'bg-emerald-500/20 text-emerald-400' : 'bg-slate-800 text-slate-500'} transition-colors">
            <Shield class="w-3 h-3" />
          </div>
          <span class="text-[11px] font-medium text-slate-200">系统代理 System Proxy</span>
        </div>

        <button
          on:click={() => mopsStore.toggleSystemProxy(proxyAddrInput.trim())}
          aria-label="切换系统代理"
          title={status?.system_proxy?.enabled ? '关闭系统代理' : '开启系统代理'}
          class="relative inline-flex h-4.5 w-8 shrink-0 cursor-pointer rounded-full border border-transparent transition-colors duration-300 ease-in-out focus:outline-none {status?.system_proxy?.enabled ? 'bg-gradient-to-r from-emerald-500 to-teal-400 shadow-md shadow-emerald-500/25' : 'bg-slate-700/80'}"
        >
          <span
            class="pointer-events-none inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow ring-0 transition duration-300 ease-in-out {status?.system_proxy?.enabled ? 'translate-x-3.5' : 'translate-x-0'}"
          ></span>
        </button>
      </div>

      <div class="flex items-center space-x-1.5">
        <input
          type="text"
          bind:value={proxyAddrInput}
          on:input={() => (isEditing = true)}
          placeholder="127.0.0.1:10081"
          aria-label="系统代理地址"
          class="flex-1 bg-slate-900/90 border border-slate-700/80 text-[10px] rounded-md px-2 py-1 text-slate-200 font-mono focus:outline-none focus:border-blue-500 transition-colors shadow-inner"
        />
        <button
          on:click={handleSaveProxy}
          aria-label="确定保存代理地址"
          class="bg-blue-600 hover:bg-blue-500 active:scale-95 text-white text-[10px] font-bold px-2 py-1 rounded-md transition-all border border-blue-400/30 shadow-sm shrink-0 cursor-pointer"
        >
          保存
        </button>
        <button
          on:click={handleSetMopsProxy}
          aria-label="设为 MOPS 出口代理"
          title="一键填入并启用 MOPS 本地 SOCKS5 出口代理"
          class="bg-emerald-600/90 hover:bg-emerald-500 active:scale-95 text-white text-[10px] font-bold px-2 py-1 rounded-md transition-all border border-emerald-400/30 shadow-sm shrink-0 flex items-center space-x-1 cursor-pointer"
        >
          <Zap class="w-3 h-3 text-emerald-200" />
          <span>设为 MOPS 代理</span>
        </button>
      </div>
    </div>
  </div>
</header>
