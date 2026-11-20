<script lang="ts">
    import { _, json } from 'svelte-i18n';
    import { messageWords, searchSettings, type SearchableSetting } from '../../settings/settings-search';
    import type { SettingsSection } from '../../settings/settings-route';
    import {
        SETTINGS_SEARCH_INDEX,
        settingsSearchEntry,
        settingsSearchInMore,
        settingsSearchIsAdvanced,
        settingsSearchSection,
        type SettingsSearchEntry
    } from '../../settings/settings-search-index';

    /** Where a chosen result ended up: on the setting, on the switch that shows it, or nowhere. */
    export type SettingsSearchLanding = 'shown' | 'behind' | 'missing';

    interface Props {
        /** Opens the setting an anchor names and moves focus to it. */
        onchoose: (anchor: string) => Promise<SettingsSearchLanding>;
        /** The open section: among equal matches, its settings are listed first. */
        activeSection: SettingsSection;
    }

    let { onchoose, activeSection }: Props = $props();

    const uid = $props.id();
    const listboxId = `${uid}-results`;
    const statusId = `${uid}-status`;
    const optionId = (index: number): string => `${uid}-result-${index}`;

    let input = $state<HTMLInputElement | null>(null);
    let text = $state('');
    let open = $state(false);
    let activeIndex = $state(0);
    /** Said after a result opened the switch that shows a setting, not the setting itself. */
    let landingNote = $state('');

    /** A message as the reader's language has it, as plain words; empty when the key has no text. */
    const words = (key: string | undefined): string => {
        const message = key ? $json(key) : undefined;
        return typeof message === 'string' ? messageWords(message) : '';
    };

    // The whole index in the reader's language. English keywords are searched in every language:
    // "gpu", "mqtt" and "backup" are what people type whatever the interface says.
    const searchable = $derived<SearchableSetting<SettingsSearchEntry>[]>(
        SETTINGS_SEARCH_INDEX.map((entry) => ({
            item: entry,
            label: words(entry.labelKey),
            help: words(entry.helpKey),
            keywords: entry.keywords,
            group: entry.kind === 'group'
        })).filter((setting) => setting.label !== '')
    );

    const query = $derived(text.trim());
    const results = $derived(searchSettings(query, searchable, { near: (entry) => settingsSearchSection(entry) === activeSection }).map((match) => match.item));
    const expanded = $derived(open && query !== '' && results.length > 0);
    const showEmpty = $derived(open && query !== '' && results.length === 0);

    /** "Alerts › More options › Advanced": the section, then each thing that opens on the way. */
    function whereOf(entry: SettingsSearchEntry): string {
        const steps = [$_(`settings.sections.${settingsSearchSection(entry)}`)];
        if (settingsSearchInMore(entry)) steps.push($_('settings.more.title', { default: 'More options' }));
        if (settingsSearchIsAdvanced(entry)) steps.push($_('settings.search.advanced', { default: 'Advanced' }));
        return steps.join(' › ');
    }

    function close(): void {
        open = false;
        activeIndex = 0;
    }

    async function choose(entry: SettingsSearchEntry): Promise<void> {
        close();
        text = '';
        landingNote = '';
        const landing = await onchoose(entry.anchor);
        if (landing === 'shown') return;
        const behind = entry.behind ? settingsSearchEntry(entry.behind) : null;
        landingNote = landing === 'behind' && behind
            ? $_('settings.search.behind', {
                  values: { setting: words(entry.labelKey), switch: words(behind.labelKey) },
                  default: '“{setting}” is shown once “{switch}” is turned on.'
              })
            : $_('settings.search.not_shown', { values: { setting: words(entry.labelKey) }, default: '“{setting}” is not shown on this install.' });
    }

    function handleKeydown(event: KeyboardEvent): void {
        if (event.key === 'Escape') {
            // The first press closes the list; the next clears the words.
            if (open && query !== '') {
                event.preventDefault();
                event.stopPropagation();
                close();
            } else if (text !== '') {
                event.preventDefault();
                event.stopPropagation();
                text = '';
            }
            return;
        }
        if (query === '') return;
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            if (!open) {
                open = true;
                return;
            }
            if (results.length === 0) return;
            const step = event.key === 'ArrowDown' ? 1 : -1;
            activeIndex = (activeIndex + step + results.length) % results.length;
            document.getElementById(optionId(activeIndex))?.scrollIntoView({ block: 'nearest' });
        } else if (event.key === 'Home' && expanded) {
            event.preventDefault();
            activeIndex = 0;
        } else if (event.key === 'End' && expanded) {
            event.preventDefault();
            activeIndex = results.length - 1;
        } else if (event.key === 'Enter' && expanded) {
            event.preventDefault();
            void choose(results[activeIndex] ?? results[0]);
        }
    }

    function isTextField(target: EventTarget | null): boolean {
        if (!(target instanceof HTMLElement)) return false;
        if (target.isContentEditable) return true;
        if (target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) return true;
        return target instanceof HTMLInputElement && !['button', 'checkbox', 'radio', 'submit', 'reset', 'range', 'color', 'file'].includes(target.type);
    }

    // "/" from anywhere on Settings that is not a text field, as on the Explorer. Not while a
    // dialog is open: the page behind it is not the one being worked in.
    function handleWindowKeydown(event: KeyboardEvent): void {
        if (event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey || event.defaultPrevented) return;
        if (isTextField(event.target) || !input || input.getClientRects().length === 0) return;
        if (document.querySelector('[role="dialog"][aria-modal="true"], dialog[open]')) return;
        event.preventDefault();
        input.focus();
        input.select();
    }
</script>

<svelte:window onkeydown={handleWindowKeydown} />

<search class="relative block" data-settings-search>
    <label for="{uid}-input" class="sr-only">{$_('settings.search.label', { default: 'Search settings' })}</label>
    <div class="relative">
        <svg class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
            <circle cx="9" cy="9" r="5.5" /><path stroke-linecap="round" d="m13 13 4 4" />
        </svg>
        <input
            bind:this={input}
            bind:value={text}
            id="{uid}-input"
            class="input-base input-focus-inset min-h-11 pl-9 pr-9 text-sm [&::-webkit-search-cancel-button]:hidden"
            type="search"
            role="combobox"
            autocomplete="off"
            spellcheck="false"
            maxlength="80"
            placeholder={$_('settings.search.placeholder', { default: 'Find a setting' })}
            aria-autocomplete="list"
            aria-expanded={expanded}
            aria-controls={listboxId}
            aria-activedescendant={expanded ? optionId(activeIndex) : undefined}
            aria-describedby={statusId}
            aria-keyshortcuts="/"
            oninput={() => { open = true; activeIndex = 0; landingNote = ''; }}
            onkeydown={handleKeydown}
            onfocus={() => { if (query) open = true; }}
            onblur={close}
            data-settings-search-input
        />
        {#if text}
            <button
                type="button"
                class="absolute right-0 top-0 inline-flex h-11 w-11 items-center justify-center rounded-lg text-muted hover:text-strong focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-focus"
                onmousedown={(event) => event.preventDefault()}
                onclick={() => { text = ''; close(); input?.focus(); }}
            >
                <svg class="h-4 w-4" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path stroke-linecap="round" d="m6 6 8 8M14 6l-8 8" /></svg>
                <span class="sr-only">{$_('settings.search.clear', { default: 'Clear search' })}</span>
            </button>
        {:else}
            <kbd class="pointer-events-none absolute right-3 top-1/2 hidden -translate-y-1/2 rounded-sm border border-line-soft px-1.5 text-2xs text-muted sm:block" aria-hidden="true">/</kbd>
        {/if}
    </div>

    <!-- The count, said politely as the reader types; the empty state says it in the panel as well. -->
    <p id={statusId} class="sr-only" role="status" aria-live="polite" data-settings-search-status>
        {#if query !== '' && open}
            {results.length > 0
                ? $_('settings.search.count', { values: { count: results.length }, default: '{count, plural, one {# setting found} other {# settings found}}' })
                : $_('settings.search.none', { values: { query }, default: 'No setting matches “{query}”.' })}
        {/if}
    </p>

    {#if landingNote}
        <p class="mt-2 text-sm text-ink" role="status" data-settings-search-note>{landingNote}</p>
    {/if}

    <!-- Wider than the rail it sits in, so a result's name and where it lives each keep a line. -->
    <div
        class="dialog-surface absolute left-0 top-full z-30 mt-1 w-full rounded-xl p-1 @2xl:w-96 {expanded || showEmpty ? '' : 'hidden'}"
        data-settings-search-panel
    >
        <div id={listboxId} role="listbox" aria-label={$_('settings.search.label', { default: 'Search settings' })} class="max-h-96 overflow-y-auto overscroll-contain {expanded ? '' : 'hidden'}">
            {#each results as entry, index (entry.anchor)}
                {@const active = index === activeIndex}
                <!-- svelte-ignore a11y_click_events_have_key_events -->
                <!-- Focus stays in the input, which owns the keyboard: arrows move and Enter chooses. -->
                <div
                    id={optionId(index)}
                    role="option"
                    aria-selected={active}
                    tabindex="-1"
                    class="flex min-h-11 cursor-pointer flex-col justify-center rounded-lg px-3 py-1.5 text-left {active ? 'choice-active' : 'text-strong'}"
                    onmousedown={(event) => event.preventDefault()}
                    onpointermove={() => (activeIndex = index)}
                    onclick={() => void choose(entry)}
                    data-settings-search-option={entry.anchor}
                >
                    <span class="text-sm wrap-anywhere">{words(entry.labelKey)}</span>
                    <span class="text-xs font-normal text-muted wrap-anywhere">{whereOf(entry)}{#if entry.kind === 'group'}{' · '}{$_('settings.search.group', { default: 'group of settings' })}{/if}</span>
                </div>
            {/each}
        </div>
        {#if showEmpty}
            <div class="space-y-1 px-3 py-2" data-settings-search-empty>
                <p class="text-sm text-strong wrap-anywhere">{$_('settings.search.none', { values: { query }, default: 'No setting matches “{query}”.' })}</p>
                <p class="text-xs text-muted">{$_('settings.search.none_hint', { default: 'Search by a setting’s name, by what it does, or by a word such as password, GPU or backup.' })}</p>
            </div>
        {/if}
    </div>
</search>
