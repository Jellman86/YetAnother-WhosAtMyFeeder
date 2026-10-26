<script lang="ts">
    import type { GardenCapture } from '../api/garden';
    import { gardenPreviewStyle } from '../utils/garden-photo';

    let { capture, src, alt = '', aspect = 4 / 3, onload, onerror }: {
        capture: GardenCapture;
        src: string;
        alt?: string;
        aspect?: number;
        onload?: () => void;
        onerror?: () => void;
    } = $props();
    let decoded = $state<{ src: string; size: readonly [number, number] } | null>(null);
    const crop = $derived(gardenPreviewStyle(capture, decoded?.src === src ? decoded.size : undefined, aspect));
    const style = $derived(crop ? `width:${crop.width}%;height:${crop.height}%;left:${crop.left}%;top:${crop.top}%;max-width:none` : undefined);

    function loaded(event: Event): void {
        const image = event.currentTarget;
        if (image instanceof HTMLImageElement) decoded = { src, size: [image.naturalWidth, image.naturalHeight] };
        onload?.();
    }
</script>

<div class="relative h-full w-full overflow-hidden" data-garden-preview={crop ? 'crop' : 'full'}>
    <img {src} {alt} {style} loading="lazy" class="absolute h-full w-full object-cover" onload={loaded} {onerror} />
</div>
