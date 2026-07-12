<script lang="ts">
    import { onMount, onDestroy } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { authStore } from '../../stores/auth.svelte';
    import { appApiPath } from '../../app/url-base';

    interface Props {
        camera: string;
    }
    let { camera }: Props = $props();

    let url = $state<string | null>(null);
    let frameState = $state<'loading' | 'ok' | 'offline'>('loading');

    async function refresh() {
        frameState = url ? 'ok' : 'loading';
        const headers = authStore.token ? { Authorization: `Bearer ${authStore.token}` } : undefined;
        try {
            const resp = await fetch(
                `${appApiPath(`/frigate/camera/${encodeURIComponent(camera)}/latest.jpg`)}?cache=${Date.now()}`,
                { headers }
            );
            if (!resp.ok) {
                frameState = 'offline';
                return;
            }
            const blob = await resp.blob();
            const previous = url;
            url = URL.createObjectURL(blob);
            if (previous) URL.revokeObjectURL(previous);
            frameState = 'ok';
        } catch {
            frameState = 'offline';
        }
    }

    onMount(refresh);
    onDestroy(() => {
        if (url) URL.revokeObjectURL(url);
    });
</script>

<div class="group relative aspect-video overflow-hidden rounded-xl border border-slate-200 bg-slate-100 dark:border-slate-700 dark:bg-slate-800">
    {#if frameState === 'ok' && url}
        <img src={url} alt={camera} class="h-full w-full object-cover" />
    {:else}
        <div class="flex h-full w-full items-center justify-center">
            {#if frameState === 'loading'}
                <div class="h-5 w-5 animate-spin rounded-full border-2 border-slate-300 border-t-teal-500"></div>
            {:else}
                <span class="text-xs font-medium text-slate-400">{$_('setup.cameras.offline', { default: 'No preview' })}</span>
            {/if}
        </div>
    {/if}
    <div class="absolute inset-x-0 bottom-0 flex items-center justify-between bg-gradient-to-t from-black/70 to-transparent px-2 py-1.5">
        <span class="truncate text-xs font-semibold text-white">{camera}</span>
        <span class="h-2 w-2 shrink-0 rounded-full {frameState === 'ok' ? 'bg-emerald-400' : frameState === 'loading' ? 'bg-slate-300' : 'bg-rose-400'}"></span>
    </div>
</div>
