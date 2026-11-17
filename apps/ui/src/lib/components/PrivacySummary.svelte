<script lang="ts">
    import { settingsStore } from '../stores/settings.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { _ } from 'svelte-i18n';
    import Disclosure from './ui/Disclosure.svelte';
    import {
        birdDeliveryChannels,
        deliverableChannels,
        gardenAlertChannels,
        leadsOutboundList,
        outboundRequests,
        type OutboundFacts,
        type OutboundRequest,
        type OutboundState
    } from '../utils/outbound-requests';

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
    // A channel that is switched on without its credentials sends nothing, so it is not counted.
    const deliverable = $derived(
        settings
            ? deliverableChannels({
                discord: { webhook_url: settings.notifications_discord_webhook_url },
                telegram: { bot_token: settings.notifications_telegram_bot_token, chat_id: settings.notifications_telegram_chat_id },
                pushover: { user_key: settings.notifications_pushover_user_key, api_token: settings.notifications_pushover_api_token },
                email: {
                    use_oauth: settings.notifications_email_use_oauth,
                    oauth_provider: settings.notifications_email_oauth_provider,
                    connected_email: settings.notifications_email_connected_email,
                    to_email: settings.notifications_email_to_email,
                    smtp_host: settings.notifications_email_smtp_host,
                    from_email: settings.notifications_email_from_email
                }
            })
            : null
    );
    const birdEnabled = $derived(
        settings
            ? {
                discord: Boolean(settings.notifications_discord_enabled),
                telegram: Boolean(settings.notifications_telegram_enabled),
                pushover: Boolean(settings.notifications_pushover_enabled),
                email: Boolean(settings.notifications_email_enabled)
            }
            : null
    );
    const birdChannels = $derived(birdEnabled && deliverable ? birdDeliveryChannels(birdEnabled, deliverable).length : null);
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
        gardenChannels: settings && birdEnabled && deliverable
            ? gardenAlertChannels({
                beta: Boolean(settings.beta_garden_animals),
                enabled: Boolean(settings.garden_notifications_enabled),
                useBirdChannels: settings.garden_notifications_use_bird_channels !== false,
                selected: settings.garden_notification_channels ?? [],
                birdEnabled,
                deliverable
            })
            : null,
        garden: settings ? Boolean(settings.beta_garden_animals) : null,
        locationSet: settings ? settings.location_latitude != null && settings.location_longitude != null : null,
        locationAutomatic: settings ? Boolean(settings.location_automatic) : null
    });
    const outbound = $derived(outboundRequests(facts));
    // The reader's own situation comes first: what is or may be sent now. A setting the viewer cannot
    // read stays in that list as Owner only, never folded away as if it were off. What is certainly not
    // sent now (Off) or made only when someone starts it waits behind one disclosure.
    const byOrigin = (requests: typeof outbound) =>
        (['server', 'browser', 'on_demand'] as const)
            .map((group) => ({ group, requests: requests.filter((request) => request.group === group) }))
            .filter((group) => group.requests.length > 0);
    const nowGroups = $derived(byOrigin(outbound.filter((request) => leadsOutboundList(request.state))));
    const restGroups = $derived(byOrigin(outbound.filter((request) => !leadsOutboundList(request.state))));
    const restCount = $derived(restGroups.reduce((count, group) => count + group.requests.length, 0));
    // When some rows follow settings this viewer cannot read, the heading says the list may hold them.
    const nowIncludesUnknown = $derived(outbound.some((request) => request.state === 'unknown'));
    const groupTitle = $derived<Record<OutboundRequest['group'], string>>({
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

{#snippet requestGroups(list: typeof nowGroups)}
    {#each list as group (group.group)}
        <h5 class="eyebrow mt-3" data-outbound-origin={group.group}>{groupTitle[group.group]}</h5>
        <dl class="mt-1 divide-y divide-line-soft text-xs">
            {#each group.requests as item (item.key)}
                <!-- Each group is a term and two descriptions (what it is for and sends, and whether it
                     happens) as direct children, which is the only shape a definition list reads correctly in. -->
                <div class="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 py-1.5" data-outbound={item.key} data-outbound-state={item.state}>
                    <dt class="col-start-1 min-w-0 font-semibold text-strong wrap-break-word">
                        {$_(`about.outbound.${item.key}`)}
                    </dt>
                    <dd class="col-start-1 min-w-0 text-muted wrap-break-word">
                        {$_(`about.outbound.${item.key}_desc`)}
                    </dd>
                    <dd
                        class="col-start-2 row-span-2 row-start-1 shrink-0 rounded-sm px-1.5 py-0.5 text-3xs font-bold {item.state === 'on'
                            ? 'bg-status-ok-soft text-status-ok'
                            : 'bg-surface-raised text-muted'}"
                    >
                        {stateLabel(item.state)}
                    </dd>
                </div>
            {/each}
        </dl>
    {/each}
{/snippet}

    <section aria-labelledby="about-stores-title">
        <h3 id="about-stores-title" class="text-sm font-bold text-strong">
            {$_('about.storage.title', { default: 'What it stores' })}
        </h3>
        <dl class="mt-2 divide-y divide-line-soft text-xs">
            {#each storageTables as row (row.key)}
                <div class="py-1.5">
                    <dt class="font-mono text-2xs font-semibold text-strong">
                        {row.table}
                    </dt>
                    <dd class="text-muted">
                        {$_(`about.storage.${row.key}_desc`)}
                    </dd>
                </div>
            {/each}
        </dl>
        <p class="mt-2 text-2xs text-muted">
            {$_('about.storage.note', {
                default: 'SQLite under /data. Schema changes ship reversible migrations.'
            })}
        </p>
    </section>

    <section aria-labelledby="about-outbound-title">
        <h3 id="about-outbound-title" class="text-sm font-bold text-strong">
            {$_('about.outbound.title', { default: 'What leaves your network' })}
        </h3>
        <p class="mt-1 text-xs text-muted" data-outbound-intro>
            {$_('about.outbound.intro', { default: 'Each request, who makes it and what it sends. Features you add later may make others.' })}
        </p>
        <div data-outbound-now>
            <h4 class="mt-3 text-xs font-semibold text-strong" data-outbound-now-heading>
                {nowIncludesUnknown
                    ? $_('about.outbound.now_heading_unknown', { default: 'Sending now, or depends on the owner’s settings' })
                    : $_('about.outbound.now_heading', { default: 'Sending now' })}
            </h4>
            {@render requestGroups(nowGroups)}
        </div>
        {#if restCount > 0}
            <Disclosure
                class="mt-3"
                label={$_('about.outbound.show_everything', { default: 'Show everything YA-WAMF can contact' })}
                note={$_('about.outbound.show_everything_note', { values: { count: restCount }, default: '{count}\u00a0more' })}
                data-outbound-everything
            >
                <!-- Names this part for a heading list, where the origins below would otherwise repeat the ones above. -->
                <h4 class="sr-only">{$_('about.outbound.rest_heading', { default: 'Off, or only when someone starts it' })}</h4>
                {@render requestGroups(restGroups)}
            </Disclosure>
        {/if}
        {#if !isOwner}
            <p class="mt-2 text-2xs text-muted">
                {$_('about.outbound.guest_note', {
                    default: 'Shown for transparency. Only the owner can change these.'
                })}
            </p>
        {/if}
    </section>
