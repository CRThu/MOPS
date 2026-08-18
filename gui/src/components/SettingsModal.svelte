<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { mopsStore } from '../lib/store';
  import { selectFolder } from '../lib/tauri';
  import { Settings, FolderOpen, Check, X, HardDrive } from 'lucide-svelte';

  export let show = false;
  export let currentDownloadDir = '';

  const dispatch = createEventDispatcher();

  let dirInput = '';
  let isSaving = false;

  $: if (show) {
    dirInput = currentDownloadDir || '';
  }

  async function handleBrowseFolder() {
    const selected = await selectFolder();
    if (selected) {
      dirInput = selected;
    }
  }

  async function handleSave() {
    const targetDir = dirInput.trim();
    if (!targetDir) {
      return;
    }
    isSaving = true;
    try {
      await mopsStore.updateDownloadDir(targetDir);
      dispatch('close');
    } finally {
      isSaving = false;
    }
  }

  function handleClose() {
    dispatch('close');
  }
</script>

{#if show}
  <div class="fixed inset-0 z-50 flex items-center justify-center p-3 bg-black/60 backdrop-blur-sm select-none animate-fade-in">
    <div class="w-full max-w-xs bg-slate-900/95 border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col space-y-3 p-3.5 backdrop-blur-xl">
      <!-- Modal Header -->
      <div class="flex items-center justify-between border-b border-slate-800/90 pb-2.5">
        <div class="flex items-center space-x-2">
          <div class="p-1 rounded-lg bg-blue-500/10 border border-blue-500/20 text-blue-400">
            <Settings class="w-4 h-4 animate-spin-slow" />
          </div>
          <span class="text-xs font-bold text-slate-100">系统偏好设置</span>
        </div>
        <button
          on:click={handleClose}
          aria-label="关闭设置"
          class="p-1 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-lg transition-colors"
        >
          <X class="w-3.5 h-3.5" />
        </button>
      </div>

      <!-- Modal Body -->
      <div class="space-y-3 py-1">
        <!-- Download Path Setting -->
        <div class="space-y-1.5">
          <label for="download-path-input" class="flex items-center justify-between text-[11px] font-semibold text-slate-300">
            <span class="flex items-center space-x-1">
              <HardDrive class="w-3.5 h-3.5 text-blue-400" />
              <span>文件接收保存目录</span>
            </span>
          </label>

          <div class="space-y-2">
            <input
              id="download-path-input"
              type="text"
              bind:value={dirInput}
              placeholder="./downloads"
              class="w-full bg-slate-950/80 border border-slate-700/80 focus:border-blue-500/70 rounded-xl px-2.5 py-1.5 text-[10px] font-mono text-slate-200 focus:outline-none transition-all shadow-inner"
            />

            <button
              on:click={handleBrowseFolder}
              type="button"
              class="w-full flex items-center justify-center space-x-1.5 py-1.5 px-2.5 bg-slate-800/80 hover:bg-slate-700/90 border border-slate-700/80 hover:border-blue-500/40 rounded-xl text-[10px] font-medium text-slate-200 transition-all cursor-pointer shadow-sm active:scale-98"
            >
              <FolderOpen class="w-3.5 h-3.5 text-blue-400" />
              <span>浏览并选择目录...</span>
            </button>
          </div>

          <p class="text-[9px] text-slate-400 leading-relaxed pt-0.5">
            所有跨节点接收的文件将自动保存至该目录，配置会自动持久化保存。
          </p>
        </div>
      </div>

      <!-- Modal Footer -->
      <div class="flex items-center justify-end space-x-2 border-t border-slate-800/90 pt-2.5">
        <button
          on:click={handleClose}
          type="button"
          class="px-3 py-1 text-[10px] font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 rounded-lg transition-colors"
        >
          取消
        </button>

        <button
          on:click={handleSave}
          disabled={isSaving}
          type="button"
          class="flex items-center space-x-1 px-3.5 py-1 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white text-[10px] font-bold rounded-lg shadow-md shadow-blue-500/20 active:scale-95 transition-all cursor-pointer disabled:opacity-50"
        >
          <Check class="w-3 h-3" />
          <span>{isSaving ? '保存中...' : '保存'}</span>
        </button>
      </div>
    </div>
  </div>
{/if}
