<script lang="ts">
    import { countRegionImageStyle, countRegionOutlineStyle } from '../utils/bird-count-disclosure';
    import type { SourceSize } from '../utils/count-scene';

    let { src, box, alt = '' }: { src: string; box: readonly number[]; alt?: string } = $props();
    let decoded = $state<{ src: string; size: SourceSize } | null>(null);
    let failed = $state<string | null>(null);
    const crop = $derived(countRegionImageStyle(box, decoded?.src === src ? decoded.size : null));
    const outline = $derived(countRegionOutlineStyle(box));

    function loaded(event: Event): void {
        const image = event.currentTarget;
        if (image instanceof HTMLImageElement) decoded = { src, size: { width: image.naturalWidth, height: image.naturalHeight } };
    }
</script>

<span class="relative block h-full w-full overflow-hidden bg-slate-100 dark:bg-slate-800">
    {#if failed !== src}
        <img {src} {alt} loading="lazy" onload={loaded} onerror={() => { failed = src; }}
            style={crop ?? 'visibility:hidden'} class="absolute" />
        {#if crop && outline}
            <!-- White with a dark edge, so the mark stays visible on bright and dark scenes alike. -->
            <span class="pointer-events-none absolute rounded-xs border-2 border-white ring-1 ring-slate-900/70" style={outline} aria-hidden="true"></span>
        {/if}
    {/if}
</span>
