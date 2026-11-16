/**
 * The requests that leave the network, derived from the features that make them.
 *
 * About used to promise that nothing else leaves the network, over a list that left out Google
 * Fonts and Wikipedia and tied the map tiles to eBird. Each entry here is one real request path,
 * with the setting that turns it on. The page says who makes the request (this server, or each
 * viewer's browser) and what it sends, and it makes no promise that the list is all there is.
 */

/** Who makes the request: YA-WAMF's server, or the browser of whoever is looking at the page. */
type OutboundOrigin = 'server' | 'browser';

/**
 * `always`: made on every install. `on` / `off`: follows a setting. `on_use`: made only when
 * someone starts the feature. `unknown`: follows a setting this viewer cannot read.
 */
export type OutboundState = 'always' | 'on' | 'off' | 'on_use' | 'unknown';

export interface OutboundRequest {
    key: string;
    origin: OutboundOrigin;
    state: OutboundState;
}

/** What the viewer knows of the install. Null is a setting this viewer cannot read. */
export interface OutboundFacts {
    owner: boolean;
    ebird: boolean;
    llm: boolean;
    telemetry: boolean | null;
    updateChecks: boolean | null;
    birdweather: boolean | null;
    inaturalistSubmissions: boolean | null;
    /** How many notification channels (Discord, Telegram, Pushover, email) are switched on. */
    notificationChannels: number | null;
    /** The feeder has coordinates saved. */
    locationSet: boolean | null;
    /** With no coordinates saved, the server looks the location up from its public IP address. */
    locationAutomatic: boolean | null;
}

function follows(setting: boolean | null): OutboundState {
    if (setting === null) return 'unknown';
    return setting ? 'on' : 'off';
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
        ['wikipedia', 'always'],
        ['gbif', 'on_use'],
        ['weather', follows(located)],
        ['geolocate', follows(lookedUpByIp)],
        ['places', 'on_use'],
        ['ebird', follows(facts.ebird)],
        ['birdweather', follows(facts.birdweather)],
        ['inat_submit', follows(facts.inaturalistSubmissions)],
        ['llm', follows(facts.llm)],
        ['notify', follows(facts.notificationChannels === null ? null : facts.notificationChannels > 0)],
        ['telemetry', follows(facts.telemetry)],
        ['updates', follows(facts.updateChecks)],
        ['downloads', 'on_use']
    ];
    // The map tiles are drawn by the location map in Settings, the range map in species details
    // and the sighting maps, so they do not depend on eBird.
    const browser: Array<[string, OutboundState]> = [
        ['fonts', 'always'],
        ['photos', 'always'],
        ['osm', 'on_use'],
        ['gbif_tiles', 'on_use']
    ];
    return [
        ...server.map(([key, state]): OutboundRequest => ({ key, origin: 'server', state })),
        ...browser.map(([key, state]): OutboundRequest => ({ key, origin: 'browser', state }))
    ];
}
