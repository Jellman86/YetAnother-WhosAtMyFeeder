<script lang="ts" generics="TabId extends string">
    import type { Snippet } from 'svelte';
    import { _ } from 'svelte-i18n';

    interface Props {
        title: string;
        subtitle?: string;
        loading?: boolean;
        onRefresh?: () => void;
        refreshing?: boolean;
        // Why the settings could not be read. While set, the reason and a retry take the place of
        // the form: a form of defaults or of an older copy would look current and could be applied.
        loadFailure?: string | null;
        onRetryLoad?: () => void;
        /** What the draft would change. The save bar shows while `count` is above zero. */
        unsaved?: { count: number; tabs: Array<{ id: TabId; label: string }> };
        saving?: boolean;
        onSave?: () => void;
        onDiscard?: () => void;
        onOpenTab?: (tab: TabId) => void;
        /** Why the last save stored nothing, shown in the save bar until the next save or Discard. */
        saveProblem?: { key: string; values?: Record<string, string>; fallback: string } | null;
        /** Fields the last save refused, each a button that opens it. */
        refusedFields?: Array<{ field: string; label: string }>;
        onOpenField?: (field: string) => void;
        /** Shown when unsaved work left with the page (Back or Forward) and was put back. */
        restoredNotice?: string | null;
        /** Which secrets must be typed again, since they are never kept. */
        retypeSecrets?: string | null;
        /** Restored edits whose saved value changed elsewhere meanwhile. Save waits on each. */
        /** `saved` and `mine` are the two values, worded for the bar, so the choice shows what it keeps. */
        conflicts?: Array<{ field: string; label: string; saved?: string; mine?: string }>;
        onUseSaved?: (field: string) => void;
        onUseMine?: (field: string) => void;
        // Tab strip lives between the header and the body so it stays in
        // tab-order for keyboard users.
        tabs?: Snippet;
        /** The id of the settings column, which the navigation's skip link focuses. */
        contentId?: string;
        children: Snippet;
    }

    let {
        title,
        subtitle,
        loading = false,
        onRefresh,
        refreshing = false,
        loadFailure = null,
        onRetryLoad,
        unsaved = { count: 0, tabs: [] },
        saving = false,
        onSave,
        onDiscard,
        onOpenTab,
        saveProblem = null,
        refusedFields = [],
        onOpenField,
        restoredNotice = null,
        retypeSecrets = null,
        conflicts = [],
        onUseSaved,
        onUseMine,
        tabs,
        contentId = 'settings-content',
        children
    }: Props = $props();

    // Every conflict row has the same two buttons; the hidden words say which setting each one
    // decides, after the visible ones so the name still starts with what is on screen.
    // The space is added here: a translation may not start with one, and markup would trim it.
    const conflictChoiceFor = (label: string): string =>
        ` ${$_('settings.save_bar.conflict_choice_for', { values: { field: label }, default: 'for {field}' })}`;

    // The rule (fields wait for Save; buttons act at once) is one tap away instead of repeated on
    // every change, so the bar stays one line and two buttons even with large text on a phone.
    let saveRuleOpen = $state(false);

    const showSaveBar = $derived((unsaved.count > 0 || Boolean(restoredNotice) || conflicts.length > 0) && !loading && !loadFailure);

    // The bar is stuck to the bottom of the window, so a control focused or scrolled to beneath it
    // would be hidden (WCAG 2.4.11). The page reserves the bar's measured height at the bottom of
    // the scroll area while it shows; the browser then keeps a focused control above it.
    let saveBar = $state<HTMLElement | null>(null);
    $effect(() => {
        const bar = saveBar;
        if (!bar) return;
        const root = document.documentElement;
        const reserve = () => {
            root.style.scrollPaddingBottom = `${Math.ceil(bar.getBoundingClientRect().height) + 16}px`;
        };
        reserve();
        const observer = new ResizeObserver(reserve);
        observer.observe(bar);
        // A control that is already in the window counts as visible even under the bar, so the
        // browser would not move it; this moves it up instead.
        const keepClear = (event: FocusEvent) => {
            const target = event.target;
            if (!(target instanceof HTMLElement) || bar.contains(target)) return;
            const barTop = bar.getBoundingClientRect().top;
            const bottom = target.getBoundingClientRect().bottom;
            if (bottom > barTop - 8) window.scrollBy({ top: bottom - barTop + 16 });
        };
        document.addEventListener('focusin', keepClear);
        return () => {
            observer.disconnect();
            document.removeEventListener('focusin', keepClear);
            root.style.scrollPaddingBottom = '';
        };
    });
</script>

<!-- The shell sets the width; a narrower column here sat inside the full-width header. The page is
     a container so the rail is chosen by room measured in rem: with the reader's text doubled the
     rail would squeeze the settings, so they stack as on a phone instead. -->
<div class="@container space-y-6">
    {#if onRefresh}
        <div class="flex items-center justify-end gap-3 -mt-2">
            <button
                type="button"
                onclick={() => onRefresh?.()}
                disabled={refreshing}
                class="btn btn-secondary px-3 py-2 text-xs font-bold shrink-0"
                aria-label={$_('common.refresh')}
            >
                <svg class="w-4 h-4 {refreshing ? 'animate-spin' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                {$_('common.refresh')}
            </button>
        </div>
    {/if}

    {#if loading}
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6" aria-busy="true">
            {#each [1, 2, 3, 4] as _}
                <div class="h-48 bg-slate-100 dark:bg-slate-800/50 rounded-2xl animate-pulse border border-slate-200 dark:border-slate-700/50"></div>
            {/each}
        </div>
    {:else if loadFailure}
        <div
            role="alert"
            class="card-base flex flex-col items-start gap-4 border-red-200 bg-red-50/80 p-6 text-red-800 dark:border-red-800/70 dark:bg-red-950/30 dark:text-red-200"
            data-settings-load-failed
        >
            <p class="text-sm font-semibold">{loadFailure}</p>
            {#if onRetryLoad}
                <button type="button" class="btn btn-secondary min-h-11 px-4" onclick={() => onRetryLoad?.()}>
                    {$_('events.try_again', { default: 'Try again' })}
                </button>
            {/if}
        </div>
    {:else}
        <div class="relative space-y-6 @4xl:flex @4xl:items-start @4xl:gap-8 @4xl:space-y-0">
            {#if tabs}
                <div class="@4xl:sticky @4xl:top-6 @4xl:w-56 @4xl:shrink-0">
                    {@render tabs()}
                </div>
            {/if}
            <!-- One readable column of rows (48rem), however wide the window. -->
            <div class="min-w-0 max-w-3xl flex-1 space-y-6">
                <div id={contentId} class="space-y-8 focus:outline-hidden" tabindex="-1" data-settings-content>
                    {@render children()}
                </div>
                {#if showSaveBar}
                    <!-- In the page's flow and stuck to the bottom of the screen: it always sits after the last
                         setting, so it can never cover one, and it follows the column's width. -->
                    <section
                        bind:this={saveBar}
                        class="save-bar sticky bottom-0 z-30 rounded-t-2xl border border-b-0 border-line-soft bg-surface px-4 py-3 sm:px-5"
                        aria-labelledby="settings-save-bar-title"
                        data-settings-save-bar
                    >
                        <h2 id="settings-save-bar-title" class="sr-only">{$_('settings.save_bar.region', { default: 'Unsaved changes' })}</h2>
                        <div class="save-bar-row flex items-center justify-between gap-4">
                            <!-- Two sibling regions, each announced its own way: the running count politely, a
                                 save problem at once. Nesting one inside the other could announce it twice. -->
                            <div class="min-w-0 space-y-1.5">
                                {#if restoredNotice}
                                    <p class="text-sm font-semibold text-slate-900 dark:text-white" data-restored-draft>{restoredNotice}</p>
                                    {#if retypeSecrets}
                                        <p class="text-sm text-slate-700 dark:text-slate-200" data-restored-secrets>{retypeSecrets}</p>
                                    {/if}
                                {/if}
                                {#if unsaved.count > 0}
                                <!-- The text flows inline, and the save rule's toggle sits at the end of its first line. -->
                                <p class="text-sm leading-snug text-slate-700 dark:text-slate-200">
                                    <!-- Said where it matters, once something is waiting: what waits and what does not. It floats at
                                         the end of the first line, so a long section name never leaves it a line of its own. -->
                                    <button
                                        type="button"
                                        class="focus-ring float-right ml-2 inline-flex h-6 w-6 items-center justify-center rounded-full align-middle text-brand-700 hover:text-brand-900 dark:text-brand-300 dark:hover:text-brand-100"
                                        aria-label={$_('settings.save_bar.how_saving_works', { default: 'How saving works' })}
                                        title={$_('settings.save_bar.how_saving_works', { default: 'How saving works' })}
                                        aria-expanded={saveRuleOpen}
                                        aria-controls="settings-save-rule"
                                        onclick={() => (saveRuleOpen = !saveRuleOpen)}
                                        data-settings-save-rule-toggle
                                    >
                                        <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                            <circle cx="12" cy="12" r="9" />
                                            <path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6M12 17h.01" />
                                        </svg>
                                    </button>
                                    <span aria-live="polite" data-save-summary>
                                        <span class="font-semibold text-slate-900 dark:text-white">{$_('settings.save_bar.summary', {
                                            values: { count: unsaved.count },
                                            default: '{count, plural, one {# unsaved change in} other {# unsaved changes in}}'
                                        })}</span>
                                        <!-- Each name flows with the sentence, so a long section name wraps where the
                                             line ends instead of dropping to a line of its own (a target inside a sentence,
                                             WCAG 2.5.8). -->
                                        {#each unsaved.tabs as tab (tab.id)}
                                            <button
                                                type="button"
                                                class="focus-ring inline rounded-sm px-1 text-left box-decoration-clone font-semibold text-brand-700 underline decoration-1 underline-offset-2 hover:text-brand-900 dark:text-brand-300 dark:hover:text-brand-100"
                                                onclick={() => onOpenTab?.(tab.id)}
                                            >{tab.label}</button>
                                        {/each}
                                    </span>
                                </p>
                                {#if saveRuleOpen}
                                    <p id="settings-save-rule" class="text-sm text-slate-600 dark:text-slate-300" data-settings-save-rule>
                                        {$_('settings.save_rule', { default: 'Changes to settings wait until you choose Save changes. Buttons such as Test, Run and Download act straight away.' })}
                                    </p>
                                {/if}
                                {/if}
                                {#if conflicts.length > 0}
                                    <div class="space-y-1.5 text-sm text-slate-700 dark:text-slate-200" data-draft-conflicts>
                                        <p class="font-semibold text-attention-800 dark:text-attention-200" id="settings-conflicts-note">{$_('settings.save_bar.conflicts', {
                                            values: { count: conflicts.length },
                                            default: '{count, plural, one {A setting you changed was also changed elsewhere. Choose which value to keep before saving:} other {# settings you changed were also changed elsewhere. Choose which value to keep before saving:}}'
                                        })}</p>
                                        <ul class="space-y-1.5">
                                            {#each conflicts as conflict (conflict.field)}
                                                <li class="flex flex-wrap items-center gap-x-3 gap-y-1.5" data-draft-conflict={conflict.field}>
                                                    <span class="min-w-0">
                                                        <span class="block font-semibold text-slate-900 dark:text-white">{conflict.label}</span>
                                                        {#if conflict.saved !== undefined && conflict.mine !== undefined}
                                                            <span class="block wrap-break-word text-slate-700 dark:text-slate-200" data-conflict-values>{$_('settings.save_bar.conflict_values', { values: { saved: conflict.saved, mine: conflict.mine }, default: 'Saved elsewhere: {saved} · Yours: {mine}' })}</span>
                                                        {/if}
                                                    </span>
                                                    <span class="flex flex-wrap gap-2">
                                                        <button type="button" class="btn btn-secondary min-h-9 px-3 text-sm" onclick={() => onUseSaved?.(conflict.field)}>
                                                            {$_('settings.save_bar.use_saved', { default: 'Use the saved value' })}<span class="sr-only">{conflictChoiceFor(conflict.label)}</span>
                                                        </button>
                                                        <button type="button" class="btn btn-secondary min-h-9 px-3 text-sm" onclick={() => onUseMine?.(conflict.field)}>
                                                            {$_('settings.save_bar.use_mine', { default: 'Use my change' })}<span class="sr-only">{conflictChoiceFor(conflict.label)}</span>
                                                        </button>
                                                    </span>
                                                </li>
                                            {/each}
                                        </ul>
                                    </div>
                                {/if}
                                {#if saveProblem}
                                    <div class="space-y-1.5 text-sm text-red-700 dark:text-red-300" role="alert" data-save-problem>
                                        <p class="flex items-start gap-1.5 font-semibold">
                                            <svg class="mt-0.5 h-4 w-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                            </svg>
                                            <span>{$_(saveProblem.key, { values: saveProblem.values, default: saveProblem.fallback })}</span>
                                        </p>
                                        {#if refusedFields.length > 0}
                                            <ul class="flex flex-wrap gap-x-3 gap-y-1 pl-5">
                                                {#each refusedFields as refused (refused.field)}
                                                    <li>
                                                        <button
                                                            type="button"
                                                            class="min-h-6 rounded-sm font-semibold underline decoration-1 underline-offset-2 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-red-500"
                                                            onclick={() => onOpenField?.(refused.field)}
                                                        >{refused.label}</button>
                                                    </li>
                                                {/each}
                                            </ul>
                                        {/if}
                                    </div>
                                {/if}
                            </div>
                            <div class="save-bar-actions flex shrink-0 items-center gap-2">
                                <button
                                    type="button"
                                    onclick={() => onDiscard?.()}
                                    disabled={saving}
                                    class="btn btn-secondary min-h-11 px-4"
                                    aria-label={$_('settings.save_bar.discard', { default: 'Discard changes' })}
                                >
                                    <!-- In a narrow bar the visible word is the short one, so both buttons share a row. -->
                                    <span class="save-bar-long" aria-hidden="true">{$_('settings.save_bar.discard', { default: 'Discard changes' })}</span>
                                    <span class="save-bar-short" aria-hidden="true">{$_('settings.save_bar.discard_short', { default: 'Discard' })}</span>
                                </button>
                                <!-- While a conflict waits, Save shows disabled with the reason beside it. -->
                                {#if unsaved.count > 0 || conflicts.length > 0}
                                <button
                                    type="button"
                                    onclick={() => onSave?.()}
                                    disabled={saving || conflicts.length > 0}
                                    aria-describedby={conflicts.length > 0 ? 'settings-conflicts-note' : undefined}
                                    class="btn btn-primary min-h-11 px-6"
                                    aria-label={saving ? $_('common.saving') : $_('settings.save_bar.save', { default: 'Save changes' })}
                                >
                                    {#if saving}
                                        <span aria-hidden="true">{$_('common.saving')}</span>
                                    {:else}
                                        <span class="save-bar-long" aria-hidden="true">{$_('settings.save_bar.save', { default: 'Save changes' })}</span>
                                        <span class="save-bar-short" aria-hidden="true">{$_('settings.save_bar.save_short', { default: 'Save' })}</span>
                                    {/if}
                                </button>
                                {/if}
                            </div>
                        </div>
                    </section>
                {/if}
            </div>
        </div>
    {/if}

</div>

<style>
    /* Measured against the bar's own width in rem, so the row also stacks when the reader's
       text size grows on a phone, not only when the screen narrows. */
    .save-bar {
        container-type: inline-size;
    }

    .save-bar-short {
        display: none;
    }

    @container (max-width: 34rem) {
        .save-bar-long {
            display: none;
        }

        .save-bar-short {
            display: inline;
        }

        .save-bar-row {
            flex-direction: column;
            align-items: stretch;
            gap: 0.75rem;
        }

        /* Side by side while both fit; with enlarged text each takes its own line. */
        .save-bar-actions {
            flex-wrap: wrap;
        }

        .save-bar-actions > :global(button) {
            flex: 1 1 auto;
            white-space: normal;
            /* Narrower padding lets the two short labels share one row on a phone, even at 200 % text. */
            padding-inline: 0.625rem;
        }
    }
</style>
