<script lang="ts">
    import { settingsStore } from '../stores/settings.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { _ } from 'svelte-i18n';
    import { gardenAlertChannels, outboundRequests, type OutboundFacts, type OutboundState } from '../utils/outbound-requests';

    const isOwner = $derived(authStore.showSettings);

    // Table names are identifiers, not copy, so they are never translated.
    const storageTables = [
        { key: 'detections', table: 'detections' },
        { key: 'audio', table: 'audio_detections' },
        { key: 'taxonomy', table: 'taxonomy_cache' }
    ];

    /** Whether the install-count read is on, as the About page learned from the read itself. */
    let { communityReadEnabled = null }: { communityReadEnabled?: boolean | null } = $props();

    // A guest reads no settings, so only what the sign-in status reports is known to them; the
    // rest is said to be the owner's to see, never guessed as off.
    const settings = $derived(isOwner ? settingsStore.settings : null);
    const birdChannels = $derived(
        settings
            ? [
                settings.notifications_discord_enabled,
                settings.notifications_telegram_enabled,
                settings.notifications_pushover_enabled,
                settings.notifications_email_enabled
            ].filter(Boolean).length
            : null
    );
    // A saved secret reaches the page as a placeholder, so "is one saved" is all that is read.
    const saved = (value: string | null | undefined): boolean => Boolean(value && value.trim());
    const facts = $derived<OutboundFacts>({
        owner: isOwner,
        ebird: Boolean(settingsStore.settings?.ebird_enabled ?? authStore.ebirdEnabled),
        llm: Boolean(settingsStore.llmEnabled),
        llmKey: settings ? saved(settings.llm_api_key) : null,
        telemetryUsage: settings ? Boolean(settings.telemetry_enabled) : null,
        telemetryHealth: settings ? Boolean(settings.telemetry_health_enabled) : null,
        updateChecks: communityReadEnabled ?? (settings ? Boolean(settings.update_check_enabled) : null),
        birdweather: settings ? Boolean(settings.birdweather_enabled) : null,
        birdweatherToken: settings ? saved(settings.birdweather_station_token) : null,
        inaturalistSubmissions: settings ? Boolean(settings.inaturalist_enabled) : null,
        inaturalistConnected: settings ? saved(settings.inaturalist_connected_user) : null,
        birdChannels,
        gardenChannels: settings && birdChannels !== null
            ? gardenAlertChannels({
                beta: Boolean(settings.beta_garden_animals),
                enabled: Boolean(settings.garden_notifications_enabled),
                useBirdChannels: settings.garden_notifications_use_bird_channels !== false,
                selected: settings.garden_notification_channels ?? [],
                birdChannels
            })
            : null,
        locationSet: settings ? settings.location_latitude != null && settings.location_longitude != null : null,
        locationAutomatic: settings ? Boolean(settings.location_automatic) : null
    });
    const outbound = $derived(outboundRequests(facts));
    const groups = $derived(
        (['server', 'browser', 'on_demand'] as const).map((group) => ({ group, requests: outbound.filter((request) => request.group === group) }))
    );
    const groupTitle = $derived<Record<(typeof groups)[number]['group'], string>>({
        server: $_('about.outbound.from_server', { default: 'Sent by this server' }),
        browser: $_('about.outbound.from_browser', { default: 'Sent by each viewer’s browser' }),
        on_demand: $_('about.outbound.on_demand', { default: 'When you connect, test or run diagnostics' })
    });

    // One vocabulary for every row: On, Off, Always, When used.
    function stateLabel(state: OutboundState): string {
        if (state === 'on') return $_('status.state_on', { default: 'On' });
        if (state === 'off') return $_('status.state_off', { default: 'Off' });
        if (state === 'always') return $_('about.outbound.state_always', { default: 'Always' });
        if (state === 'on_use') return $_('about.outbound.state_on_use', { default: 'When used' });
        return $_('about.pipeline.owner_only', { default: 'Owner only' });
    }
</script>

    <section aria-labelledby="about-stores-title">
        <h3 id="about-stores-title" class="text-sm font-bold text-slate-900 dark:text-white">
            {$_('about.storage.title', { default: 'What it stores' })}
        </h3>
        <dl class="mt-2 divide-y divide-slate-200/70 text-xs dark:divide-slate-700/50">
            {#each storageTables as row (row.key)}
                <div class="py-1.5">
                    <dt class="font-mono text-2xs font-semibold text-slate-800 dark:text-slate-100">
                        {row.table}
                    </dt>
                    <dd class="text-slate-600 dark:text-slate-400">
                        {$_(`about.storage.${row.key}_desc`)}
                    </dd>
                </div>
            {/each}
        </dl>
        <p class="mt-2 text-2xs text-slate-600 dark:text-slate-400">
            {$_('about.storage.note', {
                default: 'SQLite under /data. Schema changes ship reversible migrations.'
            })}
        </p>
    </section>

    <section aria-labelledby="about-outbound-title">
        <h3 id="about-outbound-title" class="text-sm font-bold text-slate-900 dark:text-white">
            {$_('about.outbound.title', { default: 'What leaves your network' })}
        </h3>
        <p class="mt-1 text-xs text-slate-600 dark:text-slate-400" data-outbound-intro>
            {$_('about.outbound.intro', { default: 'Each request, who makes it and what it sends. Features you add later may make others.' })}
        </p>
        {#each groups as group (group.group)}
            <h4 class="eyebrow mt-3" data-outbound-origin={group.group}>{groupTitle[group.group]}</h4>
            <dl class="mt-1 divide-y divide-slate-200/70 text-xs dark:divide-slate-700/50">
                {#each group.requests as item (item.key)}
                    <!-- Each group is a term and two descriptions (what it is for and sends, and whether it
                         happens) as direct children, which is the only shape a definition list reads correctly in. -->
                    <div class="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 py-1.5" data-outbound={item.key} data-outbound-state={item.state}>
                        <dt class="col-start-1 min-w-0 font-semibold text-slate-800 wrap-break-word dark:text-slate-100">
                            {$_(`about.outbound.${item.key}`)}
                        </dt>
                        <dd class="col-start-1 min-w-0 text-slate-600 wrap-break-word dark:text-slate-400">
                            {$_(`about.outbound.${item.key}_desc`)}
                        </dd>
                        <dd
                            class="col-start-2 row-span-2 row-start-1 shrink-0 rounded-sm px-1.5 py-0.5 text-3xs font-bold {item.state === 'on'
                                ? 'bg-success-100 text-success-800 dark:bg-success-950/50 dark:text-success-300'
                                : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'}"
                        >
                            {stateLabel(item.state)}
                        </dd>
                    </div>
                {/each}
            </dl>
        {/each}
        {#if !isOwner}
            <p class="mt-2 text-2xs text-slate-600 dark:text-slate-400">
                {$_('about.outbound.guest_note', {
                    default: 'Shown for transparency. Only the owner can change these.'
                })}
            </p>
        {/if}
    </section>
