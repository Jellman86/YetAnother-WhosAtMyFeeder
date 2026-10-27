<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { GardenCapture } from '../api/garden';
    import { withAuthParams } from '../api/core';
    import GardenPhotoPreview from './GardenPhotoPreview.svelte';

    let { capture }: { capture: GardenCapture } = $props();
    let failedCrop = $state<string | null>(null);
    let failedOriginal = $state<string | null>(null);
    const cropped = $derived(Boolean(capture.crop_url && capture.crop_url !== failedCrop));
    const src = $derived(cropped ? capture.crop_url : capture.snapshot_url);
</script>

<div class="h-16 w-20 overflow-hidden rounded bg-slate-800">
    {#if src && src !== failedOriginal}
        <GardenPhotoPreview {capture} src={withAuthParams(src)} {cropped} aspect={5 / 4}
            onerror={() => { if (cropped) failedCrop = capture.crop_url ?? null; else failedOriginal = src ?? null; }} />
    {:else}
        <span class="flex h-full items-center justify-center p-1 text-center text-3xs text-white/70">{$_('garden.snapshot_unavailable', { default: 'Snapshot unavailable' })}</span>
    {/if}
</div>
