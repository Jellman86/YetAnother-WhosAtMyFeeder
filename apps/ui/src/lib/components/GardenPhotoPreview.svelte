<script lang="ts">
    import type { GardenCapture } from '../api/garden';
    import { gardenPreviewStyle } from '../utils/garden-photo';

    let { capture, src, alt = '', aspect = 4 / 3, cropped = false, fill = false, onload, onerror }: {
        capture: GardenCapture;
        src: string;
        alt?: string;
        aspect?: number;
        cropped?: boolean;
        /** A saved crop fills its frame, as a bird thumbnail does, instead of sitting in bars. */
        fill?: boolean;
        onload?: () => void;
        onerror?: () => void;
    } = $props();
    let decoded = $state<{ src: string; size: readonly [number, number] } | null>(null);
    const crop = $derived(cropped ? null : gardenPreviewStyle(capture, decoded?.src === src ? decoded.size : undefined, aspect));
    const style = $derived(crop ? `width:${crop.width}%;height:${crop.height}%;left:${crop.left}%;top:${crop.top}%;max-width:none` : undefined);

    function loaded(event: Event): void {
        const image = event.currentTarget;
        if (image instanceof HTMLImageElement) decoded = { src, size: [image.naturalWidth, image.naturalHeight] };
        onload?.();
    }
</script>

<div class="relative h-full w-full overflow-hidden" data-garden-preview={cropped || crop ? 'crop' : 'full'}>
    <img {src} {alt} {style} loading="lazy" class="absolute h-full w-full {cropped && !fill ? 'object-contain' : 'object-cover'}" onload={loaded} {onerror} />
</div>
