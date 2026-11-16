<script lang="ts">
    import type { Snippet } from 'svelte';
    import { _ } from 'svelte-i18n';
    import StatusIcon from './StatusIcon.svelte';
    import { isInsideCard } from './surface';

    /**
     * What a section shows instead of its data, kept apart so a pending or failed read never looks
     * like an empty one (layout-patterns.md §1.5). Every state says its cause, and may offer one
     * next step. Only a failure takes a colour; the rest are calm.
     */
    export type ReadState = 'loading' | 'empty' | 'failed' | 'stale' | 'off' | 'not-measured';

    type Props = {
        state: ReadState;
        /** The cause, in a sentence: why it is empty, what failed, when it was last read. */
        cause: string;
        /**
         * A heading over the cause. A block shows the state's own heading ("Could not load") when
         * none is given; an inline state shows one only when it is given, because the sentence
         * already says what is missing.
         */
        title?: string;
        /** One next step. */
        action?: { label: string; onclick: () => void; busy?: boolean };
        /** Anything more the state needs below its cause (a disclosure of the server's words). */
        children?: Snippet;
        /**
         * `inline` is a line of text for inside a card or panel, where a bordered box would be a
         * card within a card; `block` stands on the page. Inside a Panel or a Settings card it
         * defaults to inline.
         */
        variant?: 'inline' | 'block';
        compact?: boolean;
        class?: string;
    };

    let { state, cause, title, action, children, variant, compact = false, class: className = '' }: Props = $props();

    const insideCard = isInsideCard();
    const inline = $derived((variant ?? (insideCard ? 'inline' : 'block')) === 'inline');

    const DEFAULT_TITLE: Record<ReadState, [string, string]> = {
        loading: ['ui.state.loading', 'Loading…'],
        empty: ['ui.state.empty', 'Nothing here yet'],
        failed: ['ui.state.failed', 'Could not load'],
        stale: ['ui.state.stale', 'May be out of date'],
        off: ['ui.state.off', 'Switched off'],
        'not-measured': ['ui.state.not_measured', 'Not measured']
    };

    const heading = $derived(title ?? (inline ? null : $_(DEFAULT_TITLE[state][0], { default: DEFAULT_TITLE[state][1] })));
    const frame = $derived(
        inline ? '' : `rounded-xl border ${state === 'failed' ? 'border-status-fail-line bg-status-fail-soft' : 'border-line-soft bg-surface-sunken'} ${compact ? 'p-3' : 'p-4'}`
    );
    const iconTone = $derived(state === 'failed' ? 'fail' : state === 'stale' ? 'attention' : 'neutral');
    // Inline, an empty, off or unmeasured state is its sentence alone; only work in progress, a
    // failure or an old reading earns a mark beside it.
    const showIcon = $derived(!inline || state === 'loading' || state === 'failed' || state === 'stale');
</script>

<div
    class="flex items-start {inline ? 'gap-2' : 'gap-3'} {frame} {className}"
    role={state === 'loading' || state === 'failed' || state === 'stale' ? 'status' : undefined}
    aria-busy={state === 'loading' || undefined}
    data-read-state={state}
    data-read-state-variant={inline ? 'inline' : 'block'}
>
    {#if !showIcon}
        <!-- No mark: the sentence says it. -->
    {:else if state === 'loading'}
        <svg class="mt-0.5 h-4 w-4 shrink-0 animate-spin text-muted" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <circle cx="8" cy="8" r="6.25" stroke="currentColor" stroke-opacity="0.3" stroke-width="1.75" />
            <path d="M14.25 8A6.25 6.25 0 008 1.75" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" />
        </svg>
    {:else if state === 'stale'}
        <svg class="mt-0.5 h-4 w-4 shrink-0 text-muted" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" aria-hidden="true">
            <circle cx="8" cy="8" r="6.25" />
            <path d="M8 4.75V8l2.25 1.5" />
        </svg>
    {:else}
        <span class="mt-0.5 {iconTone === 'fail' ? 'text-status-fail' : 'text-muted'}">
            <StatusIcon tone={iconTone} />
        </span>
    {/if}
    <div class="min-w-0 flex-1">
        {#if heading}
            <p class="text-sm font-semibold text-strong wrap-break-word">{heading}</p>
        {/if}
        <p class="text-sm wrap-break-word {heading ? 'mt-1' : ''} {inline && state === 'failed' ? 'text-ink' : 'text-muted'}">{cause}</p>
        {#if children}
            <div class="mt-2">{@render children()}</div>
        {/if}
        {#if action}
            <button type="button" class="btn btn-secondary mt-3" onclick={action.onclick} disabled={action.busy} aria-busy={action.busy || undefined}>
                {action.label}
            </button>
        {/if}
    </div>
</div>
