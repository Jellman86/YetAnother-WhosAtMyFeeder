<script lang="ts">
    import SettingsSubheading from './_primitives/SettingsSubheading.svelte';
    import { _ } from 'svelte-i18n';
    import { notificationLinkPreview, type NotificationLinkTarget } from '../../settings/notification-link';
    import { searchSpecies, type SearchResult } from '../../api';
    import type { BlockedSpeciesEntry, NotificationSpeciesFilterMode } from '../../api/settings';
    import {
        buildBlockedSpeciesEntry,
        formatBlockedSpeciesLabel,
        mergeBlockedSpeciesEntries,
    } from '../../settings/blocked-species';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import NotificationPolicySentence from './NotificationPolicySentence.svelte';
    import { NOTIFICATION_CHANNELS_SECTION_ID, type PolicyChannel } from '../../settings/notification-policy';
    import { requestErrorMessage } from '../../settings/error-message';
    import FieldRefusal from './_primitives/FieldRefusal.svelte';
    import { settingsFieldErrorLookup } from '../../settings/field-error-context';

    // Alerts' rules: when to notify, as one sentence (the section's first screen), and the cooldown,
    // language, link and species filter (under More options). Channels are their own component.
    let {
        // Global filters
        notifyMinConfidence = $bindable(0.7),
        notifyAudioOnly = $bindable(false),
        filterSpeciesMode = $bindable<NotificationSpeciesFilterMode>('none'),
        filterSpeciesEntries = $bindable<BlockedSpeciesEntry[]>([]),
        legacySpeciesWhitelist = $bindable<string[]>([]),
        notifyMode = $bindable<'silent' | 'final' | 'standard' | 'realtime' | 'custom'>('standard'),
        notifyOnInsert = $bindable(true),
        notifyOnUpdate = $bindable(false),
        notifyDelayUntilVideo = $bindable(false),
        notifyVideoFallbackTimeout = $bindable(45),
        notifyCooldownMinutes = $bindable(0),
        notificationLanguage = $bindable('en'),
        instanceUrl = $bindable(''),
        linkTarget = $bindable<NotificationLinkTarget>('yawamf'),
        frigateExternalUrl = '',
        onOpenConnection = () => {},
        channels,
        region
    }: {
        notifyMinConfidence: number;
        notifyAudioOnly: boolean;
        filterSpeciesMode: NotificationSpeciesFilterMode;
        filterSpeciesEntries: BlockedSpeciesEntry[];
        legacySpeciesWhitelist: string[];
        notifyMode: 'silent' | 'final' | 'standard' | 'realtime' | 'custom';
        notifyOnInsert: boolean;
        notifyOnUpdate: boolean;
        notifyDelayUntilVideo: boolean;
        notifyVideoFallbackTimeout: number;
        notifyCooldownMinutes: number;
        notificationLanguage: string;
        instanceUrl: string;
        linkTarget: NotificationLinkTarget;
        frigateExternalUrl?: string;
        /** Opens Connection, where the Frigate public URL is set. */
        onOpenConnection?: () => void;
        /** The channels set up, as the sentence names them. */
        channels: PolicyChannel[];
        /** The sentence on the section's first screen, or the details under More options. */
        region: 'main' | 'more';
    } = $props();

    const fieldErrors = settingsFieldErrorLookup();
    const instanceUrlRefusal = $derived(fieldErrors?.errorFor('notifications_instance_url'));

    const linkPreview = $derived(notificationLinkPreview(linkTarget, instanceUrl, frigateExternalUrl));
    const frigateUrlMissing = $derived(linkTarget === 'frigate' && frigateExternalUrl.trim() === '');


    let speciesSearchQuery = $state('');
    let speciesSearchResults = $state<SearchResult[]>([]);
    let speciesSearchLoading = $state(false);
    let speciesSearchError = $state('');

    function applyPreset(mode: typeof notifyMode) {
        if (mode === 'silent') {
            notifyOnInsert = false;
            notifyOnUpdate = false;
            notifyDelayUntilVideo = false;
            return;
        }
        if (mode === 'final') {
            notifyOnInsert = true;
            notifyOnUpdate = false;
            notifyDelayUntilVideo = true;
            return;
        }
        if (mode === 'realtime') {
            notifyOnInsert = true;
            notifyOnUpdate = true;
            notifyDelayUntilVideo = false;
            return;
        }
        if (mode === 'standard') {
            notifyOnInsert = true;
            notifyOnUpdate = false;
            notifyDelayUntilVideo = false;
        }
    }

    function setMode(mode: typeof notifyMode) {
        notifyMode = mode;
        if (mode !== 'custom') {
            applyPreset(mode);
        }
    }

    const speciesFilterSectionId = 'notification-species-filter-section';
    // What the cooldown goes back to when switched on again; ten minutes the first time.
    // svelte-ignore state_referenced_locally
    let lastCooldownMinutes = $state(notifyCooldownMinutes > 0 ? notifyCooldownMinutes : 10);

    const speciesFilterCount = $derived(
        filterSpeciesEntries.length +
            (filterSpeciesMode === 'whitelist' ? legacySpeciesWhitelist.length : 0)
    );


    function setSpeciesFilterMode(mode: NotificationSpeciesFilterMode) {
        filterSpeciesMode = mode;
        speciesSearchQuery = '';
        speciesSearchResults = [];
        speciesSearchError = '';
        if (mode === 'none') {
            filterSpeciesEntries = [];
            legacySpeciesWhitelist = [];
        }
    }

    function speciesEntryKey(entry: BlockedSpeciesEntry): string {
        if (entry.taxa_id != null) return `taxa:${entry.taxa_id}`;
        if (entry.scientific_name) return `scientific:${entry.scientific_name.toLocaleLowerCase()}`;
        if (entry.common_name) return `common:${entry.common_name.toLocaleLowerCase()}`;
        return 'empty';
    }

    function addSpeciesFilterResult(result: SearchResult) {
        const entry = buildBlockedSpeciesEntry(result);
        if (!entry) return;
        filterSpeciesEntries = mergeBlockedSpeciesEntries([...filterSpeciesEntries, entry]);
        speciesSearchQuery = '';
        speciesSearchResults = [];
        speciesSearchError = '';
    }

    function removeSpeciesFilterEntry(entry: BlockedSpeciesEntry) {
        const key = speciesEntryKey(entry);
        filterSpeciesEntries = filterSpeciesEntries.filter((candidate) => speciesEntryKey(candidate) !== key);
    }

    function removeLegacySpeciesWhitelist(species: string) {
        legacySpeciesWhitelist = legacySpeciesWhitelist.filter((candidate) => candidate !== species);
    }

    function getResultNames(result: SearchResult) {
        const common = result.common_name?.trim() || null;
        const scientific = result.scientific_name?.trim() || null;
        const fallback = result.display_name || result.id;
        if (common && scientific && common !== scientific) {
            return { primary: common, secondary: scientific };
        }
        return { primary: common || scientific || fallback, secondary: null };
    }

    const speciesFilterListTitle = $derived(
        filterSpeciesMode === 'blacklist'
            ? $_('settings.notifications.species_filter_blacklist_list')
            : $_('settings.notifications.species_filter_whitelist_list')
    );

    $effect(() => {
        const query = speciesSearchQuery.trim();
        if (filterSpeciesMode === 'none' || query.length < 2) {
            speciesSearchResults = [];
            speciesSearchLoading = false;
            speciesSearchError = '';
            return;
        }

        speciesSearchLoading = true;
        const timeout = setTimeout(async () => {
            try {
                speciesSearchResults = await searchSpecies(query, 20, true);
                speciesSearchError = '';
            } catch (error) {
                speciesSearchResults = [];
                speciesSearchError = requestErrorMessage(error, $_('settings.notifications.species_filter_search_failed'));
            } finally {
                speciesSearchLoading = false;
            }
        }, 250);

        return () => {
            clearTimeout(timeout);
        };
    });
</script>

<!-- When to notify, as one sentence, on the section's first screen; the cooldown, language, link
 and species filter under More options. The sentence's species and channels are links to them. -->
{#if region === 'main'}
<SettingsCard id="settings-group-notifications-global-filters" title={$_('settings.notifications.global_filters')}>
        <!-- Delivery policy as one sentence; every slot is editable in place -->
        <NotificationPolicySentence
            mode={notifyMode}
            onModeChange={setMode}
            minConfidence={notifyMinConfidence}
            onMinConfidenceChange={(value) => (notifyMinConfidence = value)}
            videoFallbackTimeout={notifyVideoFallbackTimeout}
            onVideoFallbackChange={(value) => (notifyVideoFallbackTimeout = value)}
            audioOnly={notifyAudioOnly}
            onAudioOnlyChange={(value) => (notifyAudioOnly = value)}
            speciesMode={filterSpeciesMode}
            speciesCount={speciesFilterCount}
            speciesSectionId={speciesFilterSectionId}
            {channels}
            channelsSectionId={NOTIFICATION_CHANNELS_SECTION_ID}
        />
</SettingsCard>
{:else}
<SettingsCard id="settings-group-notifications-details" nested title={$_('settings.notifications.details_title', { default: 'Cooldown, language, links and species' })}>

        <!-- Off is zero minutes: a switch says so instead of asking for "0 to disable". -->
        <div class="settings-row space-y-3 md:grid md:settings-row-columns md:items-start md:gap-x-8 md:space-y-0" data-settings-row data-notification-cooldown>
            <div class="min-w-0">
                <span id="notification-cooldown-label" class="block text-base font-semibold text-slate-900 dark:text-white">{$_('settings.notifications.cooldown')}</span>
                <span class="mt-1 block max-w-prose text-sm leading-snug text-slate-600 dark:text-slate-400">{$_('settings.notifications.cooldown_desc')}</span>
            </div>
            <div class="min-w-0 space-y-3">
                <SettingsToggle
                    checked={notifyCooldownMinutes > 0}
                    labelledBy="notification-cooldown-label"
                    srLabel={$_('settings.notifications.cooldown')}
                    onchange={(on) => (notifyCooldownMinutes = on ? lastCooldownMinutes : 0)}
                />
                {#if notifyCooldownMinutes > 0}
                    <div class="flex flex-wrap items-center gap-2">
                        <input
                            id="notification-cooldown-minutes"
                            type="number"
                            min="1"
                            step="1"
                            value={notifyCooldownMinutes}
                            oninput={(event) => {
                                const minutes = Math.max(1, Math.floor(Number(event.currentTarget.value) || 1));
                                notifyCooldownMinutes = minutes;
                                lastCooldownMinutes = minutes;
                            }}
                            onblur={(event) => {
                                // Show what will be saved: whole minutes, at least one.
                                event.currentTarget.value = String(notifyCooldownMinutes);
                            }}
                            class="input-base min-h-11 w-24"
                            aria-labelledby="notification-cooldown-label notification-cooldown-unit"
                        />
                        <span id="notification-cooldown-unit" class="text-sm text-slate-600 dark:text-slate-400">{$_('settings.notifications.cooldown_unit')}</span>
                    </div>
                {/if}
            </div>
        </div>

        <!-- Notification Language -->
        <div class="settings-row space-y-2 md:grid md:settings-row-columns md:items-start md:gap-x-8 md:space-y-0" data-settings-row>
            <div class="min-w-0">
                <label for="notification-language" class="block text-base font-semibold text-slate-900 dark:text-white">{$_('settings.notifications.notification_language')}</label>
                <p id="notification-language-desc" class="mt-1 max-w-prose text-sm text-slate-600 dark:text-slate-400">{$_('settings.notifications.notification_language_desc')}</p>
            </div>
            <select
                id="notification-language"
                bind:value={notificationLanguage}
                aria-describedby="notification-language-desc"
                class="select-base min-h-11 w-full"
            >
                <option value="en">English</option>
                <option value="es">Español</option>
                <option value="fr">Français</option>
                <option value="de">Deutsch</option>
                <option value="ja">日本語</option>
                <option value="zh">中文</option>
                <option value="ru">Русский</option>
                <option value="pt">Português</option>
                <option value="it">Italiano</option>
            </select>
        </div>

        <!-- Instance address: where notifications link back to -->
        <div class="settings-row space-y-2 md:grid md:settings-row-columns md:items-start md:gap-x-8 md:space-y-0" data-settings-row>
            <div class="min-w-0">
                <label for="notification-instance-url" class="block text-base font-semibold text-slate-900 dark:text-white">{$_('settings.notifications.instance_url')}</label>
                <p id="notification-instance-url-hint" class="mt-1 max-w-prose text-sm text-slate-600 dark:text-slate-400">{$_('settings.notifications.instance_url_desc')}</p>
            </div>
            <div class="min-w-0">
                <input
                    id="notification-instance-url"
                    type="url"
                    bind:value={instanceUrl}
                    placeholder={$_('settings.notifications.instance_url_placeholder')}
                    aria-describedby={instanceUrlRefusal ? 'notification-instance-url-hint notification-instance-url-error' : 'notification-instance-url-hint'}
                    aria-invalid={instanceUrlRefusal && !instanceUrlRefusal.conflict ? 'true' : undefined}
                    class="input-base min-h-11 w-full"
                />
                <FieldRefusal id="notification-instance-url-error" refusal={instanceUrlRefusal} />
            </div>
        </div>

        <!-- Where the notification link opens -->
        <div>
            <div class="mb-3"><SettingsSubheading id="notification-link-opens" size="label">{$_('settings.notifications.link_opens')}</SettingsSubheading></div>
            <div class="space-y-1" role="radiogroup" aria-label={$_('settings.notifications.link_opens')}>
                <label class="flex min-h-11 cursor-pointer items-start gap-3 rounded-lg px-2 py-2 text-left hover:bg-surface-raised has-focus-visible:ring-2 has-focus-visible:ring-focus">
                    <input class="mt-1 h-4 w-4 shrink-0 accent-brand-600" type="radio" name="notification-link-target" value="yawamf" bind:group={linkTarget} />
                    <span class="min-w-0">
                        <span class="block text-sm font-medium text-slate-900 dark:text-white">{$_('settings.notifications.link_opens_yawamf')}</span>
                        <span class="mt-0.5 block text-sm leading-snug text-slate-600 dark:text-slate-400">{$_('settings.notifications.link_opens_yawamf_desc')}</span>
                        <span class="mt-0.5 block text-sm leading-snug text-slate-600 dark:text-slate-400">{$_('settings.notifications.link_opens_yawamf_req')}</span>
                    </span>
                </label>
                <label class="flex min-h-11 cursor-pointer items-start gap-3 rounded-lg px-2 py-2 text-left hover:bg-surface-raised has-focus-visible:ring-2 has-focus-visible:ring-focus">
                    <input class="mt-1 h-4 w-4 shrink-0 accent-brand-600" type="radio" name="notification-link-target" value="frigate" bind:group={linkTarget} />
                    <span class="min-w-0">
                        <span class="block text-sm font-medium text-slate-900 dark:text-white">{$_('settings.notifications.link_opens_frigate')}</span>
                        <span class="mt-0.5 block text-sm leading-snug text-slate-600 dark:text-slate-400">{$_('settings.notifications.link_opens_frigate_desc')}</span>
                        <span class="mt-0.5 block text-sm leading-snug text-slate-600 dark:text-slate-400">{$_('settings.notifications.link_opens_frigate_req')}</span>
                    </span>
                </label>
            </div>
            {#if frigateUrlMissing}
                <div class="mt-3 flex flex-wrap items-center justify-between gap-3 text-sm text-attention-800 dark:text-attention-200" role="status">
                    <span>{$_('settings.notifications.link_frigate_url_missing')}</span>
                    <button type="button" class="btn btn-ghost text-xs" onclick={onOpenConnection}>{$_('settings.notifications.link_open_connection', { default: 'Open Connection' })}</button>
                </div>
            {/if}
            <div class="mt-4 grid gap-1 text-xs">
                <div class="flex flex-wrap gap-x-3 gap-y-1">
                    <span class="text-slate-600 dark:text-slate-400">{$_('settings.notifications.link_preview_telegram')}</span>
                    {#if linkPreview}
                        <span class="font-mono break-all text-slate-900 dark:text-white">{linkPreview}</span>
                    {:else}
                        <span class="text-slate-600 dark:text-slate-400">{$_('settings.notifications.link_preview_none')}</span>
                    {/if}
                </div>
                <span class="text-slate-600 dark:text-slate-400">{$_('settings.notifications.link_preview_others')}</span>
            </div>
        </div>

        <!-- Species Filter -->
        <div id={speciesFilterSectionId} class="scroll-mt-24">
            <div class="mb-3"><SettingsSubheading size="label">{$_('settings.notifications.species_filter')}</SettingsSubheading></div>
            <div class="space-y-1" role="radiogroup" aria-label={$_('settings.notifications.species_filter')}>
                <label class="flex min-h-11 cursor-pointer items-start gap-3 rounded-lg px-2 py-2 text-left hover:bg-surface-raised has-focus-visible:ring-2 has-focus-visible:ring-focus">
                    <input class="mt-1 h-4 w-4 shrink-0 accent-brand-600" type="radio" name="notification-species-filter-mode" checked={filterSpeciesMode === 'none'} onchange={() => setSpeciesFilterMode('none')} />
                    <span class="min-w-0">
                        <span class="block text-sm font-medium text-slate-900 dark:text-white">{$_('settings.notifications.species_filter_none')}</span>
                        <span class="mt-0.5 block text-sm leading-snug text-slate-600 dark:text-slate-400">{$_('settings.notifications.species_filter_none_desc')}</span>
                    </span>
                </label>
                <label class="flex min-h-11 cursor-pointer items-start gap-3 rounded-lg px-2 py-2 text-left hover:bg-surface-raised has-focus-visible:ring-2 has-focus-visible:ring-focus">
                    <input class="mt-1 h-4 w-4 shrink-0 accent-brand-600" type="radio" name="notification-species-filter-mode" checked={filterSpeciesMode === 'blacklist'} onchange={() => setSpeciesFilterMode('blacklist')} />
                    <span class="min-w-0">
                        <span class="block text-sm font-medium text-slate-900 dark:text-white">{$_('settings.notifications.species_filter_blacklist')}</span>
                        <span class="mt-0.5 block text-sm leading-snug text-slate-600 dark:text-slate-400">{$_('settings.notifications.species_filter_blacklist_desc')}</span>
                    </span>
                </label>
                <label class="flex min-h-11 cursor-pointer items-start gap-3 rounded-lg px-2 py-2 text-left hover:bg-surface-raised has-focus-visible:ring-2 has-focus-visible:ring-focus">
                    <input class="mt-1 h-4 w-4 shrink-0 accent-brand-600" type="radio" name="notification-species-filter-mode" checked={filterSpeciesMode === 'whitelist'} onchange={() => setSpeciesFilterMode('whitelist')} />
                    <span class="min-w-0">
                        <span class="block text-sm font-medium text-slate-900 dark:text-white">{$_('settings.notifications.species_filter_whitelist')}</span>
                        <span class="mt-0.5 block text-sm leading-snug text-slate-600 dark:text-slate-400">{$_('settings.notifications.species_filter_whitelist_desc')}</span>
                    </span>
                </label>
            </div>

            {#if filterSpeciesMode !== 'none'}
                <div class="mt-5">
                    <label for="notification-species-search" class="block text-sm font-semibold text-slate-700 mb-2 dark:text-slate-200">{speciesFilterListTitle}</label>
                    <input
                        id="notification-species-search"
                        bind:value={speciesSearchQuery}
                        placeholder={$_('settings.notifications.species_filter_search_placeholder')}
                        aria-label={$_('settings.notifications.species_filter_search_placeholder')}
                        class="input-base w-full"
                    />
                    {#if speciesSearchLoading}
                        <p class="mt-2 text-xs text-slate-600 dark:text-slate-400">{$_('common.loading')}</p>
                    {:else if speciesSearchError}
                        <p class="mt-2 text-xs text-red-700 dark:text-red-300">{speciesSearchError}</p>
                    {:else if speciesSearchQuery.trim().length >= 2 && speciesSearchResults.length === 0}
                        <p class="mt-2 text-xs text-slate-600 dark:text-slate-400">{$_('settings.notifications.species_filter_no_results')}</p>
                    {/if}

                    {#if speciesSearchResults.length > 0}
                        <div class="mt-3 max-h-56 overflow-y-auto rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950">
                            {#each speciesSearchResults as result}
                                {@const names = getResultNames(result)}
                                <button
                                    type="button"
                                    onclick={() => addSpeciesFilterResult(result)}
                                    class="block w-full px-4 py-3 text-left hover:bg-brand-50 dark:hover:bg-slate-800"
                                >
                                    <span class="block text-sm font-semibold text-slate-900 dark:text-white">{names.primary}</span>
                                    {#if names.secondary}
                                        <span class="block text-xs font-semibold italic text-slate-600 dark:text-slate-400">{names.secondary}</span>
                                    {/if}
                                </button>
                            {/each}
                        </div>
                    {/if}

                    <div class="mt-4 flex flex-wrap gap-2">
                        {#each filterSpeciesEntries as entry}
                            <span class="group flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-slate-800 border border-brand-200 dark:border-brand-700/50 rounded-xl text-xs font-semibold text-slate-700 dark:text-slate-300">
                                {formatBlockedSpeciesLabel(entry)}
                                <button
                                    onclick={() => removeSpeciesFilterEntry(entry)}
                                    aria-label={$_('settings.notifications.species_filter_remove_label', { values: { species: formatBlockedSpeciesLabel(entry) } })}
                                    class="text-slate-600 dark:text-slate-400 hover:text-red-500 transition-colors"
                                >
                                    x
                                </button>
                            </span>
                        {/each}
                        {#if filterSpeciesEntries.length === 0 && legacySpeciesWhitelist.length === 0}
                            <p class="text-xs text-slate-600 dark:text-slate-400">{$_('settings.notifications.no_species_filter')}</p>
                        {/if}
                    </div>

                    {#if filterSpeciesMode === 'whitelist' && legacySpeciesWhitelist.length > 0}
                        <div class="mt-4 border-t border-brand-200/60 pt-3 dark:border-brand-700/30">
                            <p class="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-200">{$_('settings.notifications.species_filter_legacy')}</p>
                            <div class="flex flex-wrap gap-2">
                                {#each legacySpeciesWhitelist as species}
                                    <span class="group flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-xs font-semibold text-slate-700 dark:text-slate-300">
                                        {species}
                                        <button
                                            onclick={() => removeLegacySpeciesWhitelist(species)}
                                            aria-label={$_('settings.notifications.remove_species_label', { values: { species } })}
                                            class="text-slate-600 dark:text-slate-400 hover:text-red-500 transition-colors"
                                        >
                                            x
                                        </button>
                                    </span>
                                {/each}
                            </div>
                        </div>
                    {/if}
                </div>
            {/if}
        </div>

</SettingsCard>
{/if}
