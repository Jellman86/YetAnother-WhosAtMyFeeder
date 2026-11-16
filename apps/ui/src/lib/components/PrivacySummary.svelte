<script lang="ts">
    import { settingsStore } from '../stores/settings.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { _ } from 'svelte-i18n';
    import { outboundRequests, type OutboundFacts, type OutboundState } from '../utils/outbound-requests';

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
    const facts = $derived<OutboundFacts>({
        owner: isOwner,
        ebird: Boolean(settingsStore.settings?.ebird_enabled ?? authStore.ebirdEnabled),
        llm: Boolean(settingsStore.llmEnabled),
        telemetry: settings ? Boolean(settings.telemetry_enabled) : null,
        updateChecks: communityReadEnabled ?? (settings ? Boolean(settings.update_check_enabled) : null),
        birdweather: settings ? Boolean(settings.birdweather_enabled) : null,
        inaturalistSubmissions: settings ? Boolean(settings.inaturalist_enabled) : null,
        notificationChannels: settings
            ? [
                settings.notifications_discord_enabled,
                settings.notifications_telegram_enabled,
                settings.notifications_pushover_enabled,
                settings.notifications_email_enabled
            ].filter(Boolean).length
            : null,
        locationSet: settings ? settings.location_latitude != null && settings.location_longitude != null : null,
        locationAutomatic: settings ? Boolean(settings.location_automatic) : null
    });
    const outbound = $derived(outboundRequests(facts));
    const groups = $derived(
        (['server', 'browser'] as const).map((origin) => ({ origin, requests: outbound.filter((request) => request.origin === origin) }))
    );

    function stateLabel(state: OutboundState): string {
        if (state === 'on') return $_('common.enabled', { default: 'Enabled' });
        if (state === 'off') return $_('common.disabled', { default: 'Disabled' });
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
        {#each groups as group (group.origin)}
            <h4 class="eyebrow mt-3" data-outbound-origin={group.origin}>
                {group.origin === 'server'
                    ? $_('about.outbound.from_server', { default: 'Sent by this server' })
                    : $_('about.outbound.from_browser', { default: 'Sent by each viewer’s browser' })}
            </h4>
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
