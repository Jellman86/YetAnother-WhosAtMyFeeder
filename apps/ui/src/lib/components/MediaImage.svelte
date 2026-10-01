<script lang="ts">
    import type { HTMLImgAttributes } from 'svelte/elements';

    /**
     * A picture that never leaves a hole (CLAUDE.md §5).
     *
     * Draws the first source that has not failed: the caller lists the picture it wants, then
     * any still worth showing if that one is gone. A source that fails is skipped from then on.
     * When none is left, a placeholder takes the same box, so nothing around it moves.
     *
     * Each source gets its own element, so a late load or error can only describe the URL it
     * was fetched for. It cannot mark the source that replaced it.
     */
    interface Props extends Omit<HTMLImgAttributes, 'src' | 'alt' | 'class' | 'onload' | 'onerror'> {
        sources: ReadonlyArray<string | null | undefined>;
        alt: string;
        /** Geometry and fit, shared by the image and its placeholder. */
        class?: string;
        /** Placeholder surface and tone, which differ between light rows and dark media. */
        placeholderClass?: string;
        iconClass?: string;
        element?: HTMLImageElement | null;
        onload?: (image: HTMLImageElement) => void;
        /** One source failed; the next one, or the placeholder, is already being drawn. */
        onfail?: (src: string) => void;
    }

    let {
        sources,
        alt,
        class: className = '',
        placeholderClass = 'bg-slate-100 text-slate-300 dark:bg-slate-800 dark:text-slate-600',
        iconClass = 'h-5 w-5',
        element = $bindable(null),
        onload,
        onfail,
        ...rest
    }: Props = $props();

    let failed = $state<ReadonlySet<string>>(new Set());
    const src = $derived(sources.find((source): source is string => !!source && !failed.has(source)) ?? null);

    function fail(event: Event): void {
        const attempted = (event.currentTarget as HTMLImageElement).getAttribute('src');
        if (!attempted || failed.has(attempted)) return;
        failed = new Set([...failed, attempted]);
        onfail?.(attempted);
    }
</script>

{#if src}
    {#key src}
        <img
            bind:this={element}
            {...rest}
            {src}
            {alt}
            class={className}
            onload={(event) => onload?.(event.currentTarget as HTMLImageElement)}
            onerror={fail}
        />
    {/key}
{:else}
    <span class="flex items-center justify-center {className} {placeholderClass}" aria-hidden="true" data-media-placeholder>
        <svg class={iconClass} fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2 1.586-1.586a2 2 0 012.828 0L20 14M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
        </svg>
    </span>
{/if}
