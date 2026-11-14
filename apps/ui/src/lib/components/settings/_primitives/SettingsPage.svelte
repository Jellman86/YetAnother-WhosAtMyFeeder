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
        // Tab strip lives between the header and the body so it stays in
        // tab-order for keyboard users.
        tabs?: Snippet;
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
        tabs,
        children
    }: Props = $props();

    const showSaveBar = $derived(unsaved.count > 0 && !loading && !loadFailure);
</script>

<!-- The shell sets the width; a narrower column here sat inside the full-width header. -->
<div class="space-y-6">
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
        {#if tabs}
            {@render tabs()}
        {/if}
        <div class="space-y-6 focus:outline-hidden" tabindex="-1" data-settings-content>
            {@render children()}
        </div>
    {/if}

    {#if showSaveBar}
        <!-- In the page's flow and stuck to the bottom of the screen: it always sits after the last
             setting, so it can never cover one, and it follows the column's width. -->
        <section
            class="save-bar sticky bottom-0 z-30 rounded-t-2xl border border-b-0 border-line-soft bg-surface px-4 py-3 sm:px-5"
            aria-labelledby="settings-save-bar-title"
            data-settings-save-bar
        >
            <h2 id="settings-save-bar-title" class="sr-only">{$_('settings.save_bar.region', { default: 'Unsaved changes' })}</h2>
            <div class="save-bar-row flex items-center justify-between gap-4">
                <!-- Two sibling regions, each announced its own way: the running count politely, a
                     save problem at once. Nesting one inside the other could announce it twice. -->
                <div class="min-w-0 space-y-1.5">
                    <p class="flex flex-wrap items-baseline gap-x-1 gap-y-1 text-sm text-slate-700 dark:text-slate-200" aria-live="polite" data-save-summary>
                        <span class="font-semibold text-slate-900 dark:text-white">{$_('settings.save_bar.summary', {
                            values: { count: unsaved.count },
                            default: '{count, plural, one {# unsaved change in} other {# unsaved changes in}}'
                        })}</span>
                        {#each unsaved.tabs as tab (tab.id)}
                            <button
                                type="button"
                                class="min-h-6 rounded-sm px-1 font-semibold text-brand-700 underline decoration-1 underline-offset-2 hover:text-brand-900 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-brand-500 dark:text-brand-300 dark:hover:text-brand-100"
                                onclick={() => onOpenTab?.(tab.id)}
                            >{tab.label}</button>
                        {/each}
                    </p>
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
                    >
                        {$_('settings.save_bar.discard', { default: 'Discard changes' })}
                    </button>
                    <button
                        type="button"
                        onclick={() => onSave?.()}
                        disabled={saving}
                        class="btn btn-primary min-h-11 px-6"
                    >
                        {saving ? $_('common.saving') : $_('settings.save_bar.save', { default: 'Save changes' })}
                    </button>
                </div>
            </div>
        </section>
    {/if}
</div>

<style>
    /* Measured against the bar's own width in rem, so the row also stacks when the reader's
       text size grows on a phone, not only when the screen narrows. */
    .save-bar {
        container-type: inline-size;
    }

    @container (max-width: 34rem) {
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
        }
    }
</style>
