import { describe, expect, it } from 'vitest';
import { gardenAlertChannels, outboundRequests, type OutboundFacts } from './outbound-requests';

const owner: OutboundFacts = {
    owner: true,
    ebird: false,
    llm: false,
    llmKey: false,
    telemetryUsage: false,
    telemetryHealth: false,
    updateChecks: true,
    birdweather: false,
    birdweatherToken: false,
    inaturalistSubmissions: false,
    inaturalistConnected: false,
    birdChannels: 0,
    gardenChannels: 0,
    locationSet: false,
    locationAutomatic: true
};

function states(facts: OutboundFacts): Record<string, string> {
    return Object.fromEntries(outboundRequests(facts).map((request) => [request.key, request.state]));
}

function groups(facts: OutboundFacts): Record<string, string> {
    return Object.fromEntries(outboundRequests(facts).map((request) => [request.key, request.group]));
}

describe('what leaves the network, from the features that send it', () => {
    it('lists the requests every viewer\'s browser makes, apart from the server\'s', () => {
        const from = groups(owner);
        for (const key of ['fonts', 'photos', 'osm', 'gbif_tiles']) expect(from[key], key).toBe('browser');
        for (const key of ['inat', 'wikipedia', 'llm', 'telemetry', 'telemetry_health']) expect(from[key], key).toBe('server');
    });

    it('names Google Fonts and Wikipedia, which load on every install', () => {
        const state = states(owner);
        for (const key of ['fonts', 'wikipedia', 'inat', 'photos']) expect(state[key], key).toBe('always');
    });

    it('does not tie the map tiles to eBird: the location map and range maps draw them too', () => {
        expect(states({ ...owner, ebird: false }).osm).toBe('on_use');
        expect(states({ ...owner, ebird: true }).osm).toBe('on_use');
        expect(states({ ...owner, ebird: false }).ebird).toBe('off');
        expect(states({ ...owner, ebird: true }).ebird).toBe('on');
    });

    it('asks for weather only where the feeder has a location, and looks one up by IP only when none is set', () => {
        expect(states({ ...owner, locationSet: true, locationAutomatic: false })).toMatchObject({ weather: 'on', geolocate: 'off' });
        expect(states({ ...owner, locationSet: true, locationAutomatic: true })).toMatchObject({ weather: 'on', geolocate: 'off' });
        expect(states({ ...owner, locationSet: false, locationAutomatic: true })).toMatchObject({ weather: 'on', geolocate: 'on' });
        expect(states({ ...owner, locationSet: false, locationAutomatic: false })).toMatchObject({ weather: 'off', geolocate: 'off' });
    });
});

describe('two telemetry opt-ins, each with its own row', () => {
    it('says health reports are on when they are, even with usage statistics off', () => {
        expect(states({ ...owner, telemetryUsage: false, telemetryHealth: true })).toMatchObject({ telemetry: 'off', telemetry_health: 'on' });
    });

    it('says usage statistics are on without implying health reports are', () => {
        expect(states({ ...owner, telemetryUsage: true, telemetryHealth: false })).toMatchObject({ telemetry: 'on', telemetry_health: 'off' });
    });
});

describe('notifications that send while the bird channels are off', () => {
    it('lists Garden alerts on their own row, on when they have a channel of their own', () => {
        expect(states({ ...owner, birdChannels: 0, gardenChannels: 1 })).toMatchObject({ notify: 'off', garden_notify: 'on' });
        expect(states({ ...owner, birdChannels: 2, gardenChannels: 0 })).toMatchObject({ notify: 'on', garden_notify: 'off' });
    });

    it('counts the channels a Garden alert really goes to', () => {
        const settings = { beta: true, enabled: true, useBirdChannels: false, selected: ['telegram'], birdChannels: 0 };
        expect(gardenAlertChannels(settings)).toBe(1);
        // Following the bird channels means those that are switched on.
        expect(gardenAlertChannels({ ...settings, useBirdChannels: true })).toBe(0);
        expect(gardenAlertChannels({ ...settings, useBirdChannels: true, birdChannels: 2 })).toBe(2);
        // Off is off: the feature or its alerts.
        expect(gardenAlertChannels({ ...settings, enabled: false })).toBe(0);
        expect(gardenAlertChannels({ ...settings, beta: false })).toBe(0);
    });
});

describe('a switch that cannot send is not shown as on', () => {
    it('needs a key for the AI provider and a station token for BirdWeather', () => {
        expect(states({ ...owner, llm: true, llmKey: false }).llm).toBe('off');
        expect(states({ ...owner, llm: true, llmKey: true }).llm).toBe('on');
        expect(states({ ...owner, birdweather: true, birdweatherToken: false }).birdweather).toBe('off');
        expect(states({ ...owner, birdweather: true, birdweatherToken: true }).birdweather).toBe('on');
    });

    it('needs a connected account before an observation can be submitted to iNaturalist', () => {
        expect(states({ ...owner, inaturalistSubmissions: true, inaturalistConnected: false }).inat_submit).toBe('off');
        expect(states({ ...owner, inaturalistSubmissions: true, inaturalistConnected: true }).inat_submit).toBe('on');
    });
});

describe('what only happens when someone connects, tests or runs diagnostics', () => {
    it('keeps those apart from normal operation, whatever the switches say', () => {
        const request = outboundRequests({ ...owner, telemetryUsage: false, birdChannels: 0, birdweather: false });
        const onDemand = request.filter((entry) => entry.group === 'on_demand').map((entry) => entry.key);
        expect(onDemand).toEqual(['oauth_browser', 'oauth_server', 'tests', 'diagnostics']);
        for (const entry of request.filter((item) => item.group === 'on_demand')) expect(entry.state, entry.key).toBe('on_use');
    });

    it('lists the startup repair of a model\'s missing configuration, which nobody starts', () => {
        expect(states(owner).model_repair).toBe('always');
        expect(groups(owner).model_repair).toBe('server');
        expect(states(owner).downloads).toBe('on_use');
    });
});

describe('a viewer who cannot read the settings', () => {
    const guest: OutboundFacts = {
        owner: false, ebird: true, llm: false, llmKey: null, telemetryUsage: null, telemetryHealth: null, updateChecks: null,
        birdweather: null, birdweatherToken: null, inaturalistSubmissions: null, inaturalistConnected: null,
        birdChannels: null, gardenChannels: null, locationSet: null, locationAutomatic: null
    };

    it('is not told that a setting is off: it is the owner\'s to see', () => {
        const state = states(guest);
        for (const key of ['telemetry', 'telemetry_health', 'updates', 'birdweather', 'inat_submit', 'notify', 'garden_notify', 'weather', 'geolocate']) {
            expect(state[key], key).toBe('unknown');
        }
        expect(state.fonts).toBe('always');
    });

    it('is told what the sign-in status itself reports', () => {
        expect(states(guest).ebird).toBe('on');
        // AI is reported off, and off needs no key to be true.
        expect(states(guest).llm).toBe('off');
        // Reported on, with a key the guest cannot see: not claimed either way.
        expect(states({ ...guest, llm: true }).llm).toBe('unknown');
    });
});

describe('the list as a whole', () => {
    it('groups the server\'s requests, then the browser\'s, then the on-demand ones, each key once', () => {
        const order = outboundRequests(owner).map((request) => request.group);
        expect(order).toEqual([...order].sort((a, b) => ['server', 'browser', 'on_demand'].indexOf(a) - ['server', 'browser', 'on_demand'].indexOf(b)));
        const keys = outboundRequests(owner).map((request) => request.key);
        expect(new Set(keys).size).toBe(keys.length);
    });
});
