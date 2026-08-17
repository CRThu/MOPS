<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { mopsStore, type AppState } from './lib/store';
  import Header from './components/Header.svelte';
  import NodeList from './components/NodeList.svelte';
  import Toast from './components/Toast.svelte';
  import { FileText, Network, ChevronDown, Check, X } from 'lucide-svelte';

  let state: AppState;
  let showIfaceModal = false;
  let customAdvertiseInput = '';

  const unsubscribe = mopsStore.subscribe((val) => {
    state = val;
  });

  onMount(() => {
    mopsStore.startPolling(1500);
  });

  onDestroy(() => {
    mopsStore.stopPolling();
    unsubscribe();
  });

  function handleSelectAdvertise(ip: string) {
    mopsStore.updateAdvertise(ip);
    showIfaceModal = false;
    customAdvertiseInput = '';
  }
</script>

<main class="w-full h-screen bg-[#0b0f19] text-slate-100 flex flex-col justify-between overflow-hidden relative selection:bg-blue-500 selection:text-white">
  <!-- Cyber Light Glow Effects -->
  <div class="absolute top-1/4 -left-20 w-56 h-56 bg-blue-600/10 rounded-full blur-3xl pointer-events-none"></div>
  <div class="absolute bottom-1/3 -right-20 w-56 h-56 bg-teal-500/10 rounded-full blur-3xl pointer-events-none"></div>

  <!-- Global Toast Notification -->
  <Toast message={state?.error} />

  <!-- Header Dashboard -->
  <Header status={state?.status} />

  <!-- Main Node List -->
  <NodeList nodes={state?.nodes || []} />

  <!-- Realtime File Transfer Overlay Progress Bar -->
  {#if state?.progress && state.progress.status === 'TRANSFERRING'}
    <div class="glass-panel border-t border-blue-500/30 p-2.5 flex items-center space-x-2.5 shadow-2xl relative z-30 animate-fade-in">
      <div class="p-2 bg-blue-500/10 text-blue-400 rounded-lg border border-blue-500/20 shrink-0">
        <FileText class="w-4 h-4 animate-bounce" />
      </div>
      <div class="flex-1 overflow-hidden space-y-1">
        <div class="flex items-center justify-between text-[11px] font-bold">
          <span class="truncate text-slate-100">{state.progress.file_name}</span>
          <span class="font-mono text-teal-300 bg-teal-950/60 px-1 py-0.2 rounded border border-teal-500/30 text-[9px]">
            {state.progress.percentage.toFixed(1)}%
          </span>
        </div>
        <div class="w-full bg-slate-900/90 rounded-full h-1.5 overflow-hidden border border-slate-700/60 shadow-inner">
          <div
            class="animate-shimmer h-full transition-all duration-300 rounded-full"
            style="width: {state.progress.percentage}%"
          ></div>
        </div>
      </div>
    </div>
  {/if}

  <!-- Broadcast Interface Selection Popover Modal -->
  {#if showIfaceModal}
    <div class="absolute bottom-9 right-3 w-72 bg-slate-900/95 backdrop-blur-xl border border-slate-700/80 rounded-xl shadow-2xl p-3 z-40 space-y-2.5 select-none animate-fade-in">
      <div class="flex items-center justify-between border-b border-slate-800 pb-2">
        <div class="flex items-center space-x-1.5">
          <Network class="w-3.5 h-3.5 text-blue-400" />
          <span class="text-[11px] font-bold text-slate-200">广播网卡设置 (mDNS)</span>
        </div>
        <button
          on:click={() => (showIfaceModal = false)}
          class="text-slate-400 hover:text-slate-200 p-0.5 rounded hover:bg-slate-800"
        >
          <X class="w-3.5 h-3.5" />
        </button>
      </div>

      <div class="space-y-1 max-h-40 overflow-y-auto pr-0.5">
        <!-- Auto option -->
        <button
          on:click={() => handleSelectAdvertise('')}
          class="w-full flex items-center justify-between p-1.5 rounded-lg text-[10px] transition-colors border {state?.status?.advertise === '' ? 'bg-blue-900/40 border-blue-500/50 text-blue-200' : 'bg-slate-800/40 border-transparent text-slate-300 hover:bg-slate-800'}"
        >
          <span class="font-medium">自动检测 (Auto)</span>
          {#if !state?.status?.advertise}
            <Check class="w-3 h-3 text-blue-400" />
          {/if}
        </button>

        <!-- Listed interfaces -->
        {#each state?.interfaces || [] as iface}
          <button
            on:click={() => handleSelectAdvertise(iface.name)}
            class="w-full flex items-center justify-between p-1.5 rounded-lg text-[10px] transition-colors border {state?.status?.advertise === iface.ip ? 'bg-blue-900/40 border-blue-500/50 text-blue-200' : 'bg-slate-800/40 border-transparent text-slate-300 hover:bg-slate-800'}"
          >
            <div class="flex items-center space-x-1.5 truncate">
              <span class="font-bold text-slate-200">{iface.name}</span>
              <span class="text-[9px] font-mono text-slate-400 truncate">({iface.ip})</span>
              {#if iface.is_virtual}
                <span class="text-[8px] bg-slate-800 text-slate-400 px-1 py-0.2 rounded border border-slate-700">虚拟</span>
              {/if}
            </div>
            {#if state?.status?.advertise === iface.ip}
              <Check class="w-3 h-3 text-blue-400 shrink-0" />
            {/if}
          </button>
        {/each}
      </div>

      <!-- Custom IP input -->
      <div class="pt-1.5 border-t border-slate-800 flex items-center space-x-1.5">
        <input
          type="text"
          bind:value={customAdvertiseInput}
          placeholder="指定 IP (例 192.168.1.100)"
          class="flex-1 bg-slate-950 border border-slate-700 rounded-md px-2 py-1 text-[10px] font-mono text-slate-200 focus:outline-none focus:border-blue-500"
        />
        <button
          on:click={() => customAdvertiseInput.trim() && handleSelectAdvertise(customAdvertiseInput.trim())}
          class="bg-blue-600 hover:bg-blue-500 text-white text-[10px] font-bold px-2 py-1 rounded-md transition-all border border-blue-400/30 shrink-0"
        >
          指定
        </button>
      </div>
    </div>
  {/if}

  <!-- Footer Status Bar -->
  <footer class="bg-slate-950/90 backdrop-blur-md border-t border-white/5 px-3 py-1.5 flex items-center justify-between text-[10px] text-slate-400 select-none relative z-20">
    <div class="flex items-center space-x-1.5 font-mono">
      <div class="relative flex items-center justify-center">
        <div class="w-1.5 h-1.5 rounded-full {state?.isOnline ? 'bg-emerald-400' : 'bg-rose-500'}"></div>
        {#if state?.isOnline}
          <div class="absolute w-3 h-3 rounded-full bg-emerald-400/40 animate-ping"></div>
        {/if}
      </div>
      <span class="font-bold text-slate-300">
        {state?.isOnline ? '已连接' : '未连接'}
      </span>
    </div>

    <!-- Broadcast Network Card IP Selector Trigger -->
    <div class="flex items-center space-x-2">
      <button
        on:click={() => (showIfaceModal = !showIfaceModal)}
        aria-label="选择广播网卡"
        title="点击设置 mDNS 组网广播网卡 IP"
        class="flex items-center space-x-1 px-2 py-0.5 bg-slate-900 hover:bg-slate-800 text-slate-300 rounded border border-slate-800 transition-colors cursor-pointer font-mono text-[9px]"
      >
        <Network class="w-3 h-3 text-blue-400" />
        <span>广播: {state?.status?.advertise || '自动检测'}</span>
        <ChevronDown class="w-3 h-3 text-slate-500 transition-transform {showIfaceModal ? 'rotate-180' : ''}" />
      </button>

      <div class="font-mono text-slate-500 flex items-center space-x-1">
        <span class="text-[9px] bg-slate-900 border border-slate-800 px-1.5 py-0.2 rounded text-slate-400">
          v1.7.0
        </span>
      </div>
    </div>
  </footer>
</main>

