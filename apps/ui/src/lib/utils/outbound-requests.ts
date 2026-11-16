/**
 * The requests that leave the network, derived from the features that make them.
 *
 * About used to promise that nothing else leaves the network, over a list that left out Google
 * Fonts and Wikipedia and tied the map tiles to eBird. Each entry here is one real request path,
 * with the condition under which it is really made: a switch that is on but has no key or token
 * cannot send, so it is not shown as on, and a feature with its own opt-in (health reports, Garden
 * alerts) has its own row. The page says who makes each request and what it sends, and it makes no
 * promise that the list is all there is.
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
    /** How many bird notification channels (Discord, Telegram, Pushover, email) are switched on. */
    birdChannels: number | null;
    /** How many channels a Garden alert goes to; they can be its own, with every bird channel off. */
    gardenChannels: number | null;
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

/**
 * The channels a Garden alert is sent to, as the server decides it: its own chosen channels, or
 * the bird channels that are switched on. None while Garden or its alerts are off.
 */
export function gardenAlertChannels(settings: {
    beta: boolean;
    enabled: boolean;
    useBirdChannels: boolean;
    selected: readonly string[];
    birdChannels: number;
}): number {
    if (!settings.beta || !settings.enabled) return 0;
    return settings.useBirdChannels ? settings.birdChannels : new Set(settings.selected).size;
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
        ['updates', follows(facts.updateChecks)],
        ['downloads', 'on_use'],
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
