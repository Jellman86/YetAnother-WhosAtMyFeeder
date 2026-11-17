/**
 * The requests that leave the network, derived from the features that make them.
 *
 * About used to promise that nothing else leaves the network, over a list that left out Google
 * Fonts and Wikipedia and tied the map tiles to eBird. Each entry here is one real request path,
 * with the condition under which it is really made: a switch that is on but has no key or token
 * cannot send, so it is not shown as on, and a feature with its own opt-in (health reports, Garden
 * alerts) has its own row. The page says who makes each request and what it sends, and it makes no
 * promise that the list is all there is.
 *
 * The rows are held to `backend/outbound_requests.json`, the registry a backend test holds every
 * module that can send a request to. A new request therefore needs a registry entry, a row here
 * and its wording in every locale before the tests pass.
 */

/**
 * `server`: YA-WAMF's server, in normal operation. `browser`: the browser of whoever is looking at
 * the page. `on_demand`: made only while someone connects an account, presses a test button or
 * runs diagnostics, whatever the feature switches say.
 */
type OutboundGroup = 'server' | 'browser' | 'on_demand';

/**
 * `always`: made on every install. `on` / `off`: follows the feature's real conditions.
 * `on_use`: made only when someone starts it. `unknown`: follows a setting this viewer cannot read.
 */
export type OutboundState = 'always' | 'on' | 'off' | 'on_use' | 'unknown';

export interface OutboundRequest {
    key: string;
    group: OutboundGroup;
    state: OutboundState;
}

/** What the viewer knows of the install. Null is a setting this viewer cannot read. */
export interface OutboundFacts {
    owner: boolean;
    ebird: boolean;
    llm: boolean;
    /** An API key is saved for the AI provider; without one no request can be made. */
    llmKey: boolean | null;
    /** Anonymous usage statistics. */
    telemetryUsage: boolean | null;
    /** Health reports, a separate opt-in that sends with usage statistics off. */
    telemetryHealth: boolean | null;
    updateChecks: boolean | null;
    birdweather: boolean | null;
    birdweatherToken: boolean | null;
    inaturalistSubmissions: boolean | null;
    inaturalistConnected: boolean | null;
    /** How many bird notification channels are switched on and hold the credentials to deliver. */
    birdChannels: number | null;
    /** How many channels a Garden alert can reach; they can be its own, with every bird channel off. */
    gardenChannels: number | null;
    /** Garden is on, so its automatic checks run and can download their model. */
    garden: boolean | null;
    /** The feeder has coordinates saved. */
    locationSet: boolean | null;
    /** With no coordinates saved, the server looks the location up from its public IP address. */
    locationAutomatic: boolean | null;
}

function follows(condition: boolean | null): OutboundState {
    if (condition === null) return 'unknown';
    return condition ? 'on' : 'off';
}

/** Both must hold for a request to be made. Off is certain as soon as one is off. */
function both(first: boolean | null, second: boolean | null): boolean | null {
    if (first === false || second === false) return false;
    if (first === null || second === null) return null;
    return true;
}

const NOTIFICATION_CHANNELS = ['discord', 'telegram', 'pushover', 'email'] as const;
export type NotificationChannel = (typeof NOTIFICATION_CHANNELS)[number];
type Saved = string | null | undefined;

/** The saved credentials each channel's sender checks before it makes any request. */
export interface NotificationCredentials {
    discord?: { webhook_url?: Saved };
    telegram?: { bot_token?: Saved; chat_id?: Saved };
    pushover?: { user_key?: Saved; api_token?: Saved };
    email?: {
        use_oauth?: boolean | null;
        oauth_provider?: Saved;
        /** The address of the connected account: present only while its tokens are held. */
        connected_email?: Saved;
        to_email?: Saved;
        smtp_host?: Saved;
        from_email?: Saved;
    };
}

// A saved secret reaches the page as a placeholder, so "is one saved" is all that is read.
const saved = (value: Saved): boolean => Boolean(value && value.trim());

/**
 * Which channels can deliver with what is saved: the server's `channel_configured`, plus the email
 * account's real connection, which the server checks when it looks the tokens up. Both sides are
 * held to `backend/tests/fixtures/notification_channel_cases.json`: a channel that is switched on
 * without these sends nothing, because its sender returns before any request.
 */
export function deliverableChannels(credentials: NotificationCredentials): Record<NotificationChannel, boolean> {
    const email = credentials.email ?? {};
    // A provider name outlives its tokens: disconnecting an account deletes the tokens and leaves
    // the name. Only the connection itself, reported as the connected address, can send.
    const mailer = email.use_oauth
        ? saved(email.oauth_provider) && saved(email.connected_email)
        : saved(email.smtp_host) && saved(email.from_email);
    return {
        discord: saved(credentials.discord?.webhook_url),
        telegram: saved(credentials.telegram?.bot_token) && saved(credentials.telegram?.chat_id),
        pushover: saved(credentials.pushover?.user_key) && saved(credentials.pushover?.api_token),
        email: saved(email.to_email) && mailer
    };
}

/** The bird channels that send: switched on, and able to deliver. */
export function birdDeliveryChannels(
    enabled: Record<NotificationChannel, boolean>,
    deliverable: Record<NotificationChannel, boolean>
): NotificationChannel[] {
    return NOTIFICATION_CHANNELS.filter((channel) => enabled[channel] && deliverable[channel]);
}

/**
 * How many channels a Garden alert really reaches: the bird channels that send, or its own chosen
 * channels that hold credentials. None while Garden or its alerts are off.
 */
export function gardenAlertChannels(settings: {
    beta: boolean;
    enabled: boolean;
    useBirdChannels: boolean;
    selected: readonly string[];
    birdEnabled: Record<NotificationChannel, boolean>;
    deliverable: Record<NotificationChannel, boolean>;
}): number {
    if (!settings.beta || !settings.enabled) return 0;
    if (settings.useBirdChannels) return birdDeliveryChannels(settings.birdEnabled, settings.deliverable).length;
    const chosen = new Set(settings.selected);
    return NOTIFICATION_CHANNELS.filter((channel) => chosen.has(channel) && settings.deliverable[channel]).length;
}

/**
 * Whether a request leads About's list rather than waiting behind "Show everything". Everything
 * that is or may be sent leads: On, Always, and a setting this viewer cannot read, because a privacy
 * list errs towards showing a request that might be made. Only what is certainly not being sent (Off)
 * or is made only when someone starts it (When used) waits.
 */
export function leadsOutboundList(state: OutboundState): boolean {
    return state !== 'off' && state !== 'on_use';
}

export function outboundRequests(facts: OutboundFacts): OutboundRequest[] {
    const located = facts.locationSet === null || facts.locationAutomatic === null
        ? null
        : facts.locationSet || facts.locationAutomatic;
    const lookedUpByIp = facts.locationSet === null || facts.locationAutomatic === null
        ? null
        : !facts.locationSet && facts.locationAutomatic;
    const server: Array<[string, OutboundState]> = [
        ['inat', 'always'],
        ['inat_local', 'on_use'],
        ['wikipedia', 'always'],
        ['gbif', 'on_use'],
        ['weather', follows(located)],
        ['geolocate', follows(lookedUpByIp)],
        ['places', 'on_use'],
        ['ebird', follows(facts.ebird)],
        ['birdweather', follows(both(facts.birdweather, facts.birdweatherToken))],
        ['inat_submit', follows(both(facts.inaturalistSubmissions, facts.inaturalistConnected))],
        ['llm', follows(both(facts.llm, facts.llmKey))],
        ['notify', follows(facts.birdChannels === null ? null : facts.birdChannels > 0)],
        ['garden_notify', follows(facts.gardenChannels === null ? null : facts.gardenChannels > 0)],
        ['telemetry', follows(facts.telemetryUsage)],
        ['telemetry_health', follows(facts.telemetryHealth)],
        // Sent once, when the last of the two opt-ins is switched off.
        ['telemetry_forget', 'on_use'],
        ['updates', follows(facts.updateChecks)],
        ['downloads', 'on_use'],
        // Nobody starts this one either: a due automatic Garden check fetches its model when the
        // file is missing or fails its checksum.
        ['garden_model', follows(facts.garden)],
        // Nobody starts this one: at every start, an installed model without its configuration
        // file has it fetched.
        ['model_repair', 'always']
    ];
    // The map tiles are drawn by the location map in Settings, the range map in species details
    // and the sighting maps, so they do not depend on eBird.
    const browser: Array<[string, OutboundState]> = [
        ['fonts', 'always'],
        ['photos', 'always'],
        ['osm', 'on_use'],
        ['gbif_tiles', 'on_use']
    ];
    // These reach a provider with what is typed in a form or held for a connection, whether or
    // not the feature's switch is on.
    const onDemand = ['oauth_browser', 'oauth_server', 'tests', 'diagnostics'];
    return [
        ...server.map(([key, state]): OutboundRequest => ({ key, group: 'server', state })),
        ...browser.map(([key, state]): OutboundRequest => ({ key, group: 'browser', state })),
        ...onDemand.map((key): OutboundRequest => ({ key, group: 'on_demand', state: 'on_use' }))
    ];
}
