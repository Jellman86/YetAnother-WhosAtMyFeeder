<script lang="ts">
    import { withAssetVersion } from '../assets';

    type LoadingMode = 'eager' | 'lazy';

    let {
        alt = 'YA-WAMF',
        class: className = '',
        sizes = '80px',
        width,
        height,
        loading = 'eager',
    } = $props<{
        alt?: string;
        class?: string;
        sizes?: string;
        width?: number;
        height?: number;
        loading?: LoadingMode;
    }>();

    const srcSet = [
        `${withAssetVersion('/favicon.png')} 32w`,
        `${withAssetVersion('/apple-touch-icon.png')} 180w`,
        `${withAssetVersion('/pwa-192x192.png')} 192w`,
        `${withAssetVersion('/pwa-512x512.png')} 512w`,
    ].join(', ');

    const fallbackSrc = withAssetVersion('/pwa-192x192.png');
</script>

<img
    src={fallbackSrc}
    srcset={srcSet}
    {sizes}
    {width}
    {height}
    {loading}
    decoding="async"
    {alt}
    class={`object-contain bg-transparent ${className}`.trim()}
/>
