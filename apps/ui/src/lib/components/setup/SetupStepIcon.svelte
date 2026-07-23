<script lang="ts">
    let { step }: { step: string } = $props();
</script>

<span class="flex h-10 w-10 items-center justify-center rounded-full bg-brand-50 text-brand-700 ring-1 ring-brand-100 dark:bg-brand-950/40 dark:text-brand-300 dark:ring-brand-900/70" aria-hidden="true">
    {#if step === 'welcome'}
        <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v3m6.4-.4-2.1 2.1M21 12h-3M5.6 5.6l2.1 2.1M3 12h3" /><path d="M7 17c1.3-2 2.9-3 5-3s3.7 1 5 3" /><circle cx="12" cy="11" r="7" /></svg>
    {:else if step === 'account'}
        <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="10" width="14" height="10" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 4v2" /></svg>
    {:else if step === 'connection'}
        <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 12h8M6.5 8.5l-2 2a4 4 0 0 0 5.7 5.7l2-2m5.3 1.3 2-2a4 4 0 0 0-5.7-5.7l-2 2" /></svg>
    {:else if step === 'cameras'}
        <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h4l1.5-2h5L16 7h4v12H4Z" /><circle cx="12" cy="13" r="3" /></svg>
    {:else if step === 'model'}
        <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="5" width="14" height="14" rx="2" /><path d="M9 9h6v6H9Zm3-7v3m0 14v3M2 12h3m14 0h3M4 4l2 2m12 12 2 2M20 4l-2 2M6 18l-2 2" /></svg>
    {:else if step === 'quality'}
        <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3 1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5Zm6 11 .8 2.2L21 17l-2.2.8L18 20l-.8-2.2L15 17l2.2-.8ZM5 14l.8 2.2L8 17l-2.2.8L5 20l-.8-2.2L2 17l2.2-.8Z" /></svg>
    {:else if step === 'integrations'}
        <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 4v4H4m12-4v4h4M8 20v-4H4m12 4v-4h4" /><rect x="8" y="8" width="8" height="8" rx="2" /></svg>
    {:else if step === 'history'}
        <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M7 3v4m10-4v4M5 11h14v9H5Z" /><path d="m9 15 2 2 4-4" /></svg>
    {:else if step === 'telemetry'}
        <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 20V10m7 10V4m7 16v-7" /></svg>
    {:else}
        <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9" /><path d="m8 12 2.5 2.5L16 9" /></svg>
    {/if}
</span>
