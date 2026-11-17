<script lang="ts">
    import type { Snippet } from 'svelte';
    import DialogCloseButton from '../DialogCloseButton.svelte';

    /**
     * The one header every dialog wears: a strip with the dialog's name on the left, its own
     * controls and the shared round × on the right, ruled off from what scrolls beneath it. `title`
     * is the dialog's heading (its h2, named by `titleId` for aria-labelledby); a dialog whose
     * heading is further down, as the record's species name is, passes a quiet `label` instead.
     * `media` is the same strip on the player's dark ground.
     */
    type Props = {
        title?: string;
        titleId?: string;
        /** A hover hint on the title, such as the raw event id when the title is generic. */
        titleHint?: string;
        label?: string;
        subtitle?: string;
        tone?: 'surface' | 'media';
        onClose: () => void;
        closeLabel?: string;
        closeElement?: HTMLButtonElement | null;
        /** The close button waits, as while a decision is being saved. */
        closeDisabled?: boolean;
        /** Attributes for the close button, such as a test hook. */
        closeData?: Record<`data-${string}`, string | boolean>;
        /** More under the title: a breadcrumb, an expiry line. */
        details?: Snippet;
        /** The dialog's own controls, beside the close button. */
        actions?: Snippet;
        class?: string;
        [data: `data-${string}`]: string | boolean | undefined;
    };

    let {
        title,
        titleId,
        titleHint,
        label,
        subtitle,
        tone = 'surface',
        onClose,
        closeLabel,
        closeElement = $bindable(null),
        closeDisabled = false,
        closeData = {},
        details,
        actions,
        class: className = '',
        ...data
    }: Props = $props();

    const media = $derived(tone === 'media');
</script>

<div
    class="flex shrink-0 flex-wrap {title ? 'items-start' : 'items-center'} justify-between gap-x-3 gap-y-2 border-b py-2 pl-4 pr-2 sm:pl-5 {media ? 'border-on-media/20 bg-media-raised' : 'border-line-soft'} {className}"
    data-dialog-header
    {...data}
>
    <div class="min-w-0 flex-1 basis-48 space-y-1 py-1.5">
        {#if title}
            <h2 id={titleId} title={titleHint} class="font-display text-lg font-bold leading-tight wrap-break-word {media ? 'text-on-media' : 'text-strong'}">{title}</h2>
        {:else if label}
            <p class="text-xs font-semibold wrap-anywhere {media ? 'text-on-media/80' : 'text-muted'}">{label}</p>
        {/if}
        {#if subtitle}
            <p class="text-xs wrap-break-word {media ? 'text-on-media/80' : 'text-muted'}">{subtitle}</p>
        {/if}
        {#if details}{@render details()}{/if}
    </div>
    <div class="ml-auto flex shrink-0 flex-wrap items-center gap-2">
        {#if actions}{@render actions()}{/if}
        <DialogCloseButton tone={media ? 'media' : 'surface'} bind:element={closeElement} label={closeLabel} onclick={onClose} disabled={closeDisabled} {...closeData} />
    </div>
</div>
