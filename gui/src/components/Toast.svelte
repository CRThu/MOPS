<script lang="ts">
  import { mopsStore } from '../lib/store';
  import { AlertCircle, X } from 'lucide-svelte';

  export let message: string | null = null;

  function handleDismiss() {
    mopsStore.clearError();
  }
</script>

{#if message}
  <div class="fixed top-3 left-3 right-3 z-50 animate-bounce-in select-none">
    <div class="glass-panel bg-rose-950/80 border border-rose-500/40 text-rose-200 px-3.5 py-2.5 rounded-2xl shadow-2xl flex items-center justify-between space-x-2 backdrop-blur-xl">
      <div class="flex items-center space-x-2 overflow-hidden">
        <AlertCircle class="w-4 h-4 text-rose-400 shrink-0" />
        <span class="text-xs font-semibold truncate">{message}</span>
      </div>

      <button
        on:click={handleDismiss}
        aria-label="关闭错误提示"
        class="p-1 text-rose-300 hover:text-white rounded-lg hover:bg-rose-900/60 transition-colors shrink-0"
      >
        <X class="w-3.5 h-3.5" />
      </button>
    </div>
  </div>
{/if}
