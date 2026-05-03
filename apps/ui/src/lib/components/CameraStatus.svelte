<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { onMount, onDestroy } from 'svelte';
    import { authStore } from '../stores/auth.svelte';
    import { fetchSettings } from '../api/settings';

    let cameras = $state<string[]>([]);
    let frames = $state<Record<string, { url: string | null; ok: boolean; loading: boolean }>>({});
    let popoverOpen = $state(false);
    let refreshTimer: ReturnType<typeof setInterval> | null = null;
    let triggerEl: HTMLButtonElement | null = $state(null);
    let menuId = 'camera-status-menu';

    let onlineCount = $derived(
        cameras.reduce((n, c) => n + (frames[c]?.ok ? 1 : 0), 0)
    );

    let statusTone = $derived.by(() => {
        if (cameras.length === 0) return 'idle';
        if (onlineCount === cameras.length) return 'ok';
        if (onlineCount === 0) return 'down';
        return 'mixed';
    });

    let toneDotClass = $derived.by(() => {
        switch (statusTone) {
            case 'ok': return 'bg-emerald-500 ring-emerald-500/40';
            case 'mixed': return 'bg-amber-500 ring-amber-500/40';
            case 'down': return 'bg-rose-500 ring-rose-500/40';
            default: return 'bg-slate-400 ring-slate-400/40';
        }
    });

    async function loadCameras() {
        try {
            const settings = await fetchSettings();
            const list = (settings as any)?.cameras;
            cameras = Array.isArray(list) ? list.filter((c: unknown): c is string => typeof c === 'string' && c.length > 0) : [];
            const next: typeof frames = {};
            for (const camera of cameras) {
                next[camera] = frames[camera] ?? { url: null, ok: false, loading: false };
            }
            frames = next;
        } catch {
            cameras = [];
        }
    }

    async function refreshFrame(camera: string) {
        const headers = authStore.token ? { Authorization: `Bearer ${authStore.token}` } : undefined;
        frames = { ...frames, [camera]: { ...(frames[camera] ?? { url: null, ok: false, loading: false }), loading: true } };
        try {
            const resp = await fetch(`/api/frigate/camera/${encodeURIComponent(camera)}/latest.jpg?cache=${Date.now()}`, { headers });
            if (!resp.ok) {
                frames = { ...frames, [camera]: { ...frames[camera], ok: false, loading: false } };
                return;
            }
            const blob = await resp.blob();
            const previousUrl = frames[camera]?.url;
            const url = URL.createObjectURL(blob);
            if (previousUrl) URL.revokeObjectURL(previousUrl);
            frames = { ...frames, [camera]: { url, ok: true, loading: false } };
        } catch {
            frames = { ...frames, [camera]: { ...frames[camera], ok: false, loading: false } };
        }
    }

    async function refreshAll() {
        await Promise.all(cameras.map((c) => refreshFrame(c)));
    }

    onMount(async () => {
        await loadCameras();
        await refreshAll();
        // Refresh frames every 15s while the page is open. Cheap — one cached jpg per camera.
        refreshTimer = setInterval(() => {
            if (!popoverOpen && document.visibilityState !== 'visible') return;
            refreshAll();
        }, 15_000);
    });

    onDestroy(() => {
        if (refreshTimer) clearInterval(refreshTimer);
        for (const entry of Object.values(frames)) {
            if (entry?.url) URL.revokeObjectURL(entry.url);
        }
    });

    function open() {
        popoverOpen = true;
        // Force-refresh on open so the user always sees fresh frames.
        refreshAll();
    }

    function close() {
        popoverOpen = false;
    }

    function toggle() {
        popoverOpen ? close() : open();
    }

    function handleKeydown(event: KeyboardEvent) {
        if (event.key === 'Escape') close();
    }
</script>

<svelte:window on:keydown={handleKeydown} />

<div class="relative">
    <button
        type="button"
        bind:this={triggerEl}
        onclick={toggle}
        onmouseenter={open}
        onmouseleave={close}
        class="relative p-2.5 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 dark:text-slate-400 transition-all duration-200 focus-ring"
        aria-haspopup="menu"
        aria-expanded={popoverOpen}
        aria-controls={menuId}
        aria-label={$_('header.cameras_label', { default: 'Camera status', values: { online: onlineCount, total: cameras.length } })}
        title={cameras.length === 0
            ? $_('header.cameras_none', { default: 'No cameras configured' })
            : `${onlineCount}/${cameras.length} ${$_('header.cameras_online', { default: 'cameras online' })}`}
    >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
        </svg>
        {#if cameras.length > 0}
            <span class="absolute -top-0.5 -right-0.5 inline-flex items-center justify-center min-w-[16px] h-4 px-1 rounded-full bg-slate-900 text-white text-[9px] font-black tabular-nums leading-none">{cameras.length}</span>
            <span class="absolute bottom-1 right-1 h-2 w-2 rounded-full ring-2 {toneDotClass}" aria-hidden="true"></span>
        {/if}
    </button>

    {#if popoverOpen}
        <div
            class="absolute right-0 top-full mt-2 w-72 max-h-[420px] overflow-y-auto rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-2xl z-[60] p-3 animate-in fade-in zoom-in-95"
            id={menuId}
            role="menu"
            tabindex="-1"
            onmouseenter={open}
            onmouseleave={close}
        >
            <div class="flex items-center justify-between mb-2 px-1">
                <span class="text-[10px] font-black uppercase tracking-widest text-slate-500">
                    {$_('header.cameras_title', { default: 'Cameras' })}
                </span>
                <span class="text-[10px] font-bold text-slate-400 tabular-nums">{onlineCount}/{cameras.length}</span>
            </div>

            {#if cameras.length === 0}
                <p class="text-xs text-slate-500 italic font-bold px-1 py-3">
                    {$_('header.cameras_empty', { default: 'No cameras configured. Add cameras in Settings → Connection.' })}
                </p>
            {:else}
                <ul class="space-y-2">
                    {#each cameras as camera}
                        {@const entry = frames[camera]}
                        <li class="flex items-center gap-3 rounded-xl border border-slate-200/70 dark:border-slate-700/60 bg-slate-50 dark:bg-slate-900/60 p-2">
                            <div class="relative w-20 h-14 shrink-0 rounded-lg overflow-hidden bg-slate-200 dark:bg-slate-800">
                                {#if entry?.url}
                                    <img src={entry.url} alt="" class="absolute inset-0 w-full h-full object-cover" />
                                {:else if entry?.loading}
                                    <div class="absolute inset-0 flex items-center justify-center">
                                        <div class="w-4 h-4 border-2 border-slate-400 border-t-transparent rounded-full animate-spin"></div>
                                    </div>
                                {:else}
                                    <div class="absolute inset-0 flex items-center justify-center text-[9px] font-bold uppercase tracking-widest text-slate-400">
                                        {$_('header.cameras_no_frame', { default: 'No frame' })}
                                    </div>
                                {/if}
                            </div>
                            <div class="min-w-0 flex-1">
                                <div class="flex items-center gap-1.5">
                                    <span class="h-2 w-2 rounded-full {entry?.ok ? 'bg-emerald-500' : 'bg-rose-500'}" aria-hidden="true"></span>
                                    <span class="text-xs font-black text-slate-800 dark:text-slate-100 truncate">{camera}</span>
                                </div>
                                <div class="text-[10px] font-bold text-slate-400 mt-0.5">
                                    {entry?.ok
                                        ? $_('header.cameras_status_online', { default: 'Online' })
                                        : $_('header.cameras_status_offline', { default: 'No recent frame' })}
                                </div>
                            </div>
                        </li>
                    {/each}
                </ul>
            {/if}
        </div>
    {/if}
</div>
