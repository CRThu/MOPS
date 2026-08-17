<script lang="ts">
  import type { NodeInfo } from '../lib/api';
  import { selectFile } from '../lib/tauri';
  import { mopsStore } from '../lib/store';
  import { Monitor, Send, Radio, Wifi } from 'lucide-svelte';

  export let nodes: NodeInfo[] = [];

  $: sortedNodes = [...nodes].sort((a, b) => {
    if (a.is_me && !b.is_me) return -1;
    if (!a.is_me && b.is_me) return 1;
    return a.ip.localeCompare(b.ip, undefined, { numeric: true });
  });

  function formatBytes(bytes: number | undefined): string {
    if (!bytes || bytes <= 0) return '0.000 MB';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let i = 0;
    let val = bytes;
    while (val >= 1024 && i < units.length - 1) {
      val /= 1024;
      i++;
    }
    return `${val.toFixed(2)} ${units[i]}`;
  }

  function formatSpeed(bytesPerSec: number | undefined): string {
    if (!bytesPerSec || bytesPerSec <= 0) return '0.0 KB/s';
    const kb = bytesPerSec / 1024;
    if (kb < 1024) {
      return `${kb.toFixed(1)} KB/s`;
    }
    const mb = kb / 1024;
    if (mb < 1024) {
      return `${mb.toFixed(1)} MB/s`;
    }
    return `${(mb / 1024).toFixed(2)} GB/s`;
  }

  async function handleSendFile(node: NodeInfo) {
    const filePath = await selectFile();
    if (filePath) {
      await mopsStore.startFileTransfer(node.ip, node.port, filePath);
    }
  }
</script>

<div class="p-3 flex-1 overflow-y-auto space-y-2.5 select-none">
  <!-- Section Header -->
  <div class="flex items-center justify-between px-0.5">
    <div class="flex items-center space-x-1.5">
      <Radio class="w-3 h-3 text-blue-400 animate-pulse" />
      <span class="text-[11px] font-extrabold uppercase tracking-wider text-slate-300">
        局域网节点 ({sortedNodes.length})
      </span>
    </div>

    <span class="text-[9px] text-emerald-300 font-mono bg-emerald-950/70 border border-emerald-500/30 px-1.5 py-0.2 rounded-full shadow-sm flex items-center space-x-1">
      <span class="w-1 h-1 rounded-full bg-emerald-400 animate-ping"></span>
      <span>mDNS</span>
    </span>
  </div>

  {#if sortedNodes.length === 0}
    <div class="py-10 text-center text-slate-500 space-y-2 glass-card rounded-xl border-dashed border-slate-800/80 p-4">
      <div class="w-9 h-9 mx-auto rounded-full bg-slate-800/50 flex items-center justify-center text-slate-500 border border-slate-700/40">
        <Wifi class="w-4 h-4 stroke-1 animate-pulse" />
      </div>
      <div class="space-y-0.5">
        <div class="text-[11px] font-semibold text-slate-300">未检索到局域网节点</div>
        <div class="text-[9px] text-slate-500">同一局域网下的 MOPS 节点将自动加入集群</div>
      </div>
    </div>
  {:else}
    <div class="space-y-2">
      {#each sortedNodes as node (node.id)}
        <div class="glass-card glass-card-hover rounded-xl p-2.5 flex flex-col space-y-1.5 group">
          <!-- Top Row: Node Meta Info & Actions -->
          <div class="flex items-center justify-between">
            <div class="flex items-center space-x-2.5 overflow-hidden">
              <div class="p-2 rounded-lg bg-slate-900/80 border border-white/5 text-blue-400 shrink-0 group-hover:border-blue-500/30 transition-colors">
                <Monitor class="w-3.5 h-3.5" />
              </div>
              <div class="overflow-hidden min-w-0">
                <div class="flex items-center space-x-1.5">
                  <span class="text-[11px] font-bold text-slate-100 truncate group-hover:text-blue-300 transition-colors">
                    {node.hostname}
                  </span>
                  {#if node.is_me}
                    <span class="text-[8px] bg-blue-950/80 text-blue-300 border border-blue-600/40 px-1 py-0.2 rounded font-mono shrink-0 shadow-sm">
                      local
                    </span>
                  {:else}
                    <span class="text-[8px] bg-emerald-950/80 text-emerald-300 border border-emerald-600/40 px-1 py-0.2 rounded font-mono shrink-0 shadow-sm">
                      peer
                    </span>
                  {/if}
                </div>
                <div class="text-[9px] font-mono text-slate-400 truncate flex items-center space-x-1.5 mt-0.5">
                  <span>{node.ip}:{node.port}</span>
                  {#if node.status === 'ONLINE'}
                    <span class="inline-flex items-center space-x-1 text-emerald-400 font-sans text-[8px]">
                      <span class="w-1 h-1 rounded-full bg-emerald-400 animate-pulse-glow"></span>
                      <span>ONLINE</span>
                    </span>
                  {:else if node.status === 'NO_INTERNET'}
                    <span class="inline-flex items-center space-x-1 text-amber-400 font-sans text-[8px]">
                      <span class="w-1 h-1 rounded-full bg-amber-400"></span>
                      <span>仅局域网 (无外网)</span>
                    </span>
                  {:else}
                    <span class="inline-flex items-center space-x-1 text-slate-500 font-sans text-[8px]">
                      <span class="w-1 h-1 rounded-full bg-slate-500"></span>
                      <span>已离线</span>
                    </span>
                  {/if}
                </div>
              </div>
            </div>

            <!-- Actions -->
            <div class="shrink-0 flex items-center space-x-2">
              {#if !node.is_me}
                <button
                  on:click={() => handleSendFile(node)}
                  aria-label="传输文件"
                  class="flex items-center space-x-1 text-[10px] font-bold bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white px-2.5 py-1 rounded-lg transition-all duration-200 shadow hover:shadow-blue-500/20 active:scale-95 border border-blue-400/20"
                >
                  <Send class="w-2.5 h-2.5 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
                  <span>传输文件</span>
                </button>
              {/if}
            </div>
          </div>

          <!-- Bottom Row: Realtime Speed & Stats & Total Traffic -->
          <div class="text-[9px] font-mono text-slate-400 flex items-center justify-between border-t border-white/5 pt-1 px-0.5">
            <span class="text-slate-400 font-mono flex items-center space-x-0.5" title="连接统计: 活跃 / 成功 / 失败">
              <span class="text-slate-500 font-semibold">conn:</span>
              <span class="text-blue-400 font-bold">{node.active_conns || 0}</span>
              <span class="text-slate-600">/</span>
              <span class="text-emerald-400 font-bold">{node.success_conns || 0}</span>
              <span class="text-slate-600">/</span>
              <span class="text-rose-400 font-bold">{node.fail_conns || 0}</span>
            </span>
            <span class="text-emerald-400 font-semibold px-1 py-0.2 bg-emerald-950/40 rounded border border-emerald-500/20 shadow-sm">
              ↑ {formatSpeed(node.speed_up)} ↓ {formatSpeed(node.speed_down)}
            </span>
            <span class="text-slate-400">
              ↑ {formatBytes(node.bytes_up)} | ↓ {formatBytes(node.bytes_down)}
            </span>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>
