<script lang="ts" generics="T extends string | boolean">
    /**
     * One control for a short "choose one": a neutral track with the chosen segment raised, set in
     * heavier type and marked with a check, so the choice never rests on tint alone (and holds in
     * high contrast, where every button is painted the same). aria-pressed says it to a screen
     * reader. Four or more long options belong in a list or a select instead (layout-patterns §6);
     * short ones may wrap.
     */
    type Option = { value: T; label: string; disabled?: boolean; /** A small colour sample, as for a colour theme. */ swatch?: string };

    type Props = {
        value: T | null;
        options: Option[];
        onchange: (next: T) => void;
        /** The id of the visible label that names the set. */
        labelledBy?: string;
        /** The set's name when no visible label names it. */
        label?: string;
        /** `row` shares the width evenly, `stack` gives each option a line, `wrap` lets short ones flow. */
        layout?: 'row' | 'stack' | 'wrap';
        /** `fill` takes the width it is given (a rail, a settings row); `content` is as wide as its options (a toolbar). */
        width?: 'fill' | 'content';
        size?: 'sm' | 'md';
        /** Says why every option is off, or what the chosen one means. */
        describedBy?: string;
        /** A data attribute each option carries with its value, for tests and captures. */
        optionAttribute?: `data-${string}`;
        class?: string;
        [data: `data-${string}`]: string | boolean | undefined;
    };

    let { value, options, onchange, labelledBy, label, layout = 'row', width = 'fill', size = 'md', describedBy, optionAttribute, class: className = '', ...data }: Props = $props();

    const track = $derived(
        layout === 'stack' ? 'flex flex-col' : layout === 'wrap' ? 'flex flex-wrap' : 'flex'
    );
</script>

<div class="{track} {width === 'content' ? 'w-fit max-w-full flex-wrap' : 'w-full'} gap-1 rounded-xl bg-surface-raised p-1 {className}" role="group" aria-labelledby={labelledBy} aria-label={labelledBy ? undefined : label} {...data}>
    {#each options as option (String(option.value))}
        {@const chosen = option.value === value}
        <button
            type="button"
            onclick={() => onchange(option.value)}
            aria-pressed={chosen}
            aria-describedby={describedBy}
            disabled={option.disabled}
            data-segment={String(option.value)}
            {...optionAttribute ? { [optionAttribute]: String(option.value) } : {}}
            class="focus-ring flex min-h-11 min-w-11 items-center justify-center gap-1.5 rounded-lg px-3 transition-colors disabled:cursor-not-allowed disabled:opacity-60
                {width === 'content' ? '' : layout === 'wrap' ? 'grow' : 'flex-1'}
                {size === 'sm' ? 'text-xs' : 'text-sm'}
                {chosen ? 'bg-surface font-semibold text-strong shadow-xs ring-1 ring-line' : 'font-medium text-muted hover:text-strong'}"
        >
            {#if chosen}
                <svg class="h-3.5 w-3.5 shrink-0 text-accent-ink" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true" data-segment-check>
                    <path stroke-linecap="round" stroke-linejoin="round" d="m4.5 10.5 3.5 3.5 7.5-8" />
                </svg>
            {/if}
            {#if option.swatch}<span class="h-3 w-3 shrink-0 rounded-full {option.swatch}" aria-hidden="true"></span>{/if}
            <span class="min-w-0 text-center wrap-break-word">{option.label}</span>
        </button>
    {/each}
</div>
