<script lang="ts" generics="TabId extends string">
    import { tick, type Snippet } from 'svelte';
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
        /**
         * The open section's status and its parts. Rendered twice, with only one shown: first on a
         * phone (`top`), and after the settings in a third column when the page has room (`side`),
         * so the keyboard reaches it in the order it is seen.
         */
        aside?: Snippet<[placement: 'top' | 'side']>;
        /** The open section's name, restated above its settings and kept in view while they scroll. */
        sectionTitle?: string;
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
        aside,
        sectionTitle,
        contentId = 'settings-content',
        children
    }: Props = $props();

    // Every conflict row has the same two buttons; the hidden words say which setting each one
    // decides, after the visible ones so the name still starts with what is on screen.
    // The space is added here: a translation may not start with one, and markup would trim it.
    const conflictChoiceFor = (label: string): string =>
        ` ${$_('settings.save_bar.conflict_choice_for', { values: { field: label }, default: 'for {field}' })}`;

    // The bar is one line. What waits, in full, is in the details just above it: opened on request,
    // and by itself for a conflict, a refused value or changes kept from before, which need a look.
    let detailsOpen = $state(false);
    let saveDetails = $state<HTMLElement | null>(null);
    const problemShown = $derived(saveProblem !== null);
    // While something there needs a look the details cannot close, so the button only goes to them.
    const detailsHeldOpen = $derived(conflicts.length > 0 || problemShown || Boolean(restoredNotice));
    const detailsShown = $derived(detailsOpen || detailsHeldOpen);

    async function openDetails(): Promise<void> {
        if (detailsHeldOpen) {
            saveDetails?.scrollIntoView({ block: 'center' });
            saveDetails?.focus({ preventScroll: true });
            return;
        }
        detailsOpen = !detailsOpen;
        if (!detailsOpen) return;
        await tick();
        saveDetails?.scrollIntoView({ block: 'center' });
        saveDetails?.focus({ preventScroll: true });
    }

    const showSaveBar = $derived((unsaved.count > 0 || Boolean(restoredNotice) || conflicts.length > 0) && !loading && !loadFailure);

    // The section's name stays at the top of the window, so anything scrolled to or focused must
    // stop below it (WCAG 2.4.11): the page reserves its measured height, and whatever is above it.
    // While jobs run, the shell's jobs strip is stuck there too once the page has scrolled; the name
    // then sticks just below the strip, so both stay readable.
    let sectionHeading = $state<HTMLElement | null>(null);
    $effect(() => {
        const heading = sectionHeading;
        if (!heading) return;
        const root = document.documentElement;
        const strip = document.querySelector<HTMLElement>('[data-jobs-strip]');
        const place = () => {
            const stuck = strip && getComputedStyle(strip).position === 'sticky' ? Math.ceil(strip.getBoundingClientRect().height) : 0;
            // On the layout, so the rail and the status column, which stick as well, clear the strip too.
            (heading.closest<HTMLElement>('[data-settings-layout]') ?? heading).style.setProperty('--settings-jobs-strip-height', `${stuck}px`);
            const top = Number.parseFloat(getComputedStyle(heading).top) || 0;
            root.style.scrollPaddingTop = `${Math.ceil(top + heading.getBoundingClientRect().height) + 16}px`;
        };
        place();
        const sizes = new ResizeObserver(place);
        sizes.observe(heading);
        // The strip grows and shrinks with its jobs, and sticks only once the page has scrolled.
        const sticking = new MutationObserver(place);
        if (strip) {
            sizes.observe(strip);
            sticking.observe(strip, { attributes: true, attributeFilter: ['class'] });
        }
        return () => {
            sizes.disconnect();
            sticking.disconnect();
            root.style.scrollPaddingTop = '';
        };
    });

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
                class="btn btn-secondary px-3 py-2 text-xs shrink-0"
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
        <!-- One grid, measured on the page in rem, so doubled text gets the narrower layout: the
             sections, then the section's name, the status and the settings on a phone; the section list beside them
             from 42rem; and from 68rem the status and the section's parts in a third column, while
             the settings keep one readable column of at most 48rem. -->
        <div class="settings-layout relative" data-settings-layout>
            {#if tabs}
                <div class="settings-layout-nav">
                    {@render tabs()}
                </div>
            {/if}
            <div class="settings-layout-main min-w-0 space-y-6">
                {#if sectionTitle}
                    <!-- Which section this is, said once in the page and kept in view: the rail scrolls
                         away on a phone, and a long section is several screens of groups. -->
                    <header bind:this={sectionHeading} class="settings-section-heading sticky z-20 border-b border-line-soft py-3" data-settings-section-heading>
                        <h2 id="settings-section-title" class="text-2xl font-bold text-strong">{sectionTitle}</h2>
                    </header>
                {/if}
                {#if aside}
                    <div class="settings-layout-aside-top" data-settings-aside="top">
                        {@render aside('top')}
                    </div>
                {/if}
                <div id={contentId} class="space-y-8 focus:outline-hidden" tabindex="-1" data-settings-content>
                    {@render children()}
                </div>
                {#if showSaveBar}
                    {#if detailsShown}
                        <!-- What waits, in full: in the page's flow just above the bar, so it scrolls with the
                             settings and the bar itself stays one line. It opens by itself for something that
                             needs a decision: a conflict, a refused value, or changes kept from before. -->
                        <section
                            bind:this={saveDetails}
                            id="settings-save-details"
                            class="card-base space-y-3 p-4 text-sm text-ink sm:p-5"
                            aria-labelledby="settings-save-details-title"
                            tabindex="-1"
                            data-settings-save-details
                        >
                            <h2 id="settings-save-details-title" class="text-sm font-semibold text-strong">{$_('settings.save_bar.details_title', { default: 'Changes waiting to be saved' })}</h2>
                            {#if restoredNotice}
                                <p class="font-semibold text-strong" data-restored-draft>{restoredNotice}</p>
                                {#if retypeSecrets}
                                    <p data-restored-secrets>{retypeSecrets}</p>
                                {/if}
                            {/if}
                            {#if unsaved.count > 0}
                                <!-- Each name flows with the sentence (a target inside a sentence, WCAG 2.5.8). -->
                                <p class="leading-snug">
                                    <span class="font-semibold text-strong">{$_('settings.save_bar.summary', {
                                        values: { count: unsaved.count },
                                        default: '{count, plural, one {# unsaved change in} other {# unsaved changes in}}'
                                    })}</span>
                                    {#each unsaved.tabs as tab (tab.id)}
                                        <button
                                            type="button"
                                            class="focus-ring inline rounded-sm px-1 text-left box-decoration-clone font-semibold text-accent-ink underline decoration-1 underline-offset-2"
                                            onclick={() => onOpenTab?.(tab.id)}
                                        >{tab.label}</button>
                                    {/each}
                                </p>
                                <p id="settings-save-rule" class="text-muted" data-settings-save-rule>
                                    {$_('settings.save_rule', { default: 'Changes to settings wait until you choose Save changes. Buttons such as Test, Run and Download act straight away.' })}
                                </p>
                            {/if}
                            {#if conflicts.length > 0}
                                <div class="space-y-1.5" data-draft-conflicts>
                                    <p class="font-semibold text-status-attention" id="settings-conflicts-note">{$_('settings.save_bar.conflicts', {
                                        values: { count: conflicts.length },
                                        default: '{count, plural, one {A setting you changed was also changed elsewhere. Choose which value to keep before saving:} other {# settings you changed were also changed elsewhere. Choose which value to keep before saving:}}'
                                    })}</p>
                                    <ul class="space-y-1.5">
                                        {#each conflicts as conflict (conflict.field)}
                                            <li class="flex flex-wrap items-center gap-x-3 gap-y-1.5" data-draft-conflict={conflict.field}>
                                                <span class="min-w-0">
                                                    <span class="block font-semibold text-strong">{conflict.label}</span>
                                                    {#if conflict.saved !== undefined && conflict.mine !== undefined}
                                                        <span class="block wrap-break-word" data-conflict-values>{$_('settings.save_bar.conflict_values', { values: { saved: conflict.saved, mine: conflict.mine }, default: 'Saved elsewhere: {saved} · Yours: {mine}' })}</span>
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
                                <div class="space-y-1.5 text-status-fail" role="alert" data-save-problem>
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
                                                        class="focus-ring min-h-6 rounded-sm font-semibold underline decoration-1 underline-offset-2"
                                                        onclick={() => onOpenField?.(refused.field)}
                                                    >{refused.label}</button>
                                                </li>
                                            {/each}
                                        </ul>
                                    {/if}
                                </div>
                            {/if}
                        </section>
                    {/if}
                    <!-- Stuck to the bottom of the screen and one line: what waits, the details, and the two
                         actions. In the page's flow, it always sits after the last setting and follows the
                         column's width. -->
                    <section
                        bind:this={saveBar}
                        class="save-bar sticky bottom-0 z-30 rounded-t-2xl border border-b-0 border-line-soft bg-surface px-4 py-2 sm:px-5"
                        aria-labelledby="settings-save-bar-title"
                        data-settings-save-bar
                    >
                        <h2 id="settings-save-bar-title" class="sr-only">{$_('settings.save_bar.region', { default: 'Unsaved changes' })}</h2>
                        <div class="save-bar-row flex flex-wrap items-center gap-x-3 gap-y-1">
                            <!-- The count and its details share a line; on a narrow phone Discard and Save take
                                 the line below, so the bar is two short lines at most. -->
                            <div class="save-bar-status flex min-w-0 flex-auto items-center gap-1">
                                <!-- One line whatever the font's metrics: a count too long for it ends in an ellipsis,
                                     and the full words are in the details and said to a screen reader. -->
                                <p class="min-w-0 flex-auto truncate text-sm font-semibold {problemShown ? 'text-status-fail' : conflicts.length > 0 ? 'text-status-attention' : 'text-strong'}" aria-live="polite" data-save-summary>
                                    {#if conflicts.length > 0}
                                        {$_('settings.save_bar.line_conflicts', { values: { count: conflicts.length }, default: '{count, plural, one {# change to decide} other {# changes to decide}}' })}
                                    {:else if problemShown}
                                        {$_('settings.save_bar.line_not_saved', { default: 'Not saved' })}
                                    {:else}
                                        <!-- On a narrow bar the short count keeps this to one line; a screen reader hears it whole. -->
                                        <span class="save-bar-long">{$_('settings.save_bar.line', { values: { count: unsaved.count }, default: '{count, plural, one {# unsaved change} other {# unsaved changes}}' })}</span>
                                        <span class="save-bar-short" aria-hidden="true">{$_('settings.save_bar.line_short', { values: { count: unsaved.count }, default: '{count, plural, one {# unsaved} other {# unsaved}}' })}</span>
                                        <span class="save-bar-short sr-only">{$_('settings.save_bar.line', { values: { count: unsaved.count }, default: '{count, plural, one {# unsaved change} other {# unsaved changes}}' })}</span>
                                    {/if}
                                </p>
                                <button
                                    type="button"
                                    class="btn btn-ghost min-h-6 min-w-6 shrink-0 px-1.5 py-0.5"
                                    aria-label={detailsHeldOpen ? $_('settings.save_bar.go_to_details', { default: 'Go to details' }) : $_('settings.save_bar.details', { default: 'Details' })}
                                    aria-expanded={detailsHeldOpen ? undefined : detailsShown}
                                    aria-controls="settings-save-details"
                                    onclick={openDetails}
                                    data-settings-save-details-toggle
                                >
                                    <span class="save-bar-long" aria-hidden="true">{$_('settings.save_bar.details', { default: 'Details' })}</span>
                                    <svg class="h-5 w-5 transition-transform motion-reduce:transition-none {detailsShown ? '' : 'rotate-180'}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9" /></svg>
                                </button>
                            </div>
                            <div class="save-bar-actions flex shrink-0 items-center gap-2">
                                <button
                                    type="button"
                                    onclick={() => onDiscard?.()}
                                    disabled={saving}
                                    class="btn btn-secondary min-h-11 px-4"
                                    aria-label={$_('settings.save_bar.discard', { default: 'Discard changes' })}
                                >
                                    <!-- In a narrow bar the visible word is the short one, so the buttons share a row. -->
                                    <span class="save-bar-long" aria-hidden="true">{$_('settings.save_bar.discard', { default: 'Discard changes' })}</span>
                                    <span class="save-bar-short" aria-hidden="true">{$_('settings.save_bar.discard_short', { default: 'Discard' })}</span>
                                </button>
                                <!-- While a conflict waits, Save shows disabled with the reason in the details. -->
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
            {#if aside}
                <div class="settings-layout-aside-side" data-settings-aside="side">
                    {@render aside('side')}
                </div>
            {/if}
        </div>
    {/if}

</div>

<style>
    /* A readable measure for every paragraph in Settings, however wide its card or column, and for
       the items of a list marked as prose. A list item is otherwise a row (a divider, a value at
       its right edge) and keeps the card's width. It sits in the base layer, under the utilities,
       so a width a paragraph sets for itself (max-w-full on a chip) still wins. */
    @layer base {
        :global(:is([data-settings-content], [data-settings-aside]) :is(p, [data-settings-prose] > li)) {
            max-inline-size: 72ch;
        }
    }

    /* The section's name covers what scrolls beneath it, on the page's own ground. */
    .settings-section-heading {
        background-color: var(--app-bg);
        /* Below the phone's top bar, and below the jobs strip while that is stuck there. */
        top: calc(var(--app-chrome-height, 0rem) + var(--settings-jobs-strip-height, 0px));
    }

    /* The status beside the settings is the one after them in the page, so the keyboard reaches it
       after the settings it sits beside; on a phone the one before them is shown. */
    .settings-layout-aside-side {
        display: none;
    }

    .settings-layout {
        display: grid;
        grid-template-columns: minmax(0, 1fr);
        gap: 1.5rem;
    }

    /* The search's results open over the settings, above the section's name that stays in view. */
    .settings-layout-nav {
        position: relative;
        z-index: 25;
    }

    @container (min-width: 42rem) {
        .settings-layout {
            grid-template-columns: 12rem minmax(0, 48rem);
            column-gap: 2rem;
            align-items: start;
        }

        .settings-layout-nav {
            grid-column: 1;
            position: sticky;
            top: calc(1.5rem + var(--settings-jobs-strip-height, 0px));
        }

        .settings-layout-main {
            grid-column: 2;
        }
    }

    @container (min-width: 68rem) {
        .settings-layout {
            grid-template-columns: 12rem minmax(0, 48rem) minmax(15rem, 22rem);
        }

        .settings-layout-main {
            grid-row: 1;
        }

        .settings-layout-aside-top {
            display: none;
        }

        .settings-layout-aside-side {
            display: block;
            grid-column: 3;
            grid-row: 1;
            position: sticky;
            top: calc(1.5rem + var(--settings-jobs-strip-height, 0px));
        }
    }

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

        /* The count takes the line above the buttons when they cannot share one; the three buttons
           always share theirs, with the short labels and narrower padding, even at 200 % text. */
        .save-bar-actions {
            flex: 1 1 100%;
            min-width: 0;
        }

        .save-bar-actions > :global(button) {
            flex: 1 1 auto;
            min-width: 0;
            white-space: nowrap;
            padding-inline: 0.5rem;
        }

        /* A font wider than ours shortens a label with an ellipsis rather than pushing the bar off
           the screen; the button's name still says the whole of it. */
        .save-bar-actions .save-bar-short {
            display: block;
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
        }
    }
</style>
