// @ts-expect-error -- node:fs resolves at runtime, not in the app tsconfig
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import {
    birdDeliveryChannels,
    deliverableChannels,
    gardenAlertChannels,
    leadsOutboundList,
    outboundRequests,
    type NotificationCredentials,
    type OutboundFacts,
    type OutboundState
} from './outbound-requests';

function backendJson<T>(path: string): T {
    return JSON.parse(readFileSync(new URL(`../../../../../backend/${path}`, import.meta.url), 'utf8')) as T;
}

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
    garden: false,
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

    const none = { discord: false, telegram: false, pushover: false, email: false };

    it('counts the channels a Garden alert really goes to', () => {
        const settings = {
            beta: true, enabled: true, useBirdChannels: false, selected: ['telegram'],
            birdEnabled: none, deliverable: { ...none, telegram: true, discord: true }
        };
        expect(gardenAlertChannels(settings)).toBe(1);
        // Following the bird channels means those that are switched on and can deliver.
        expect(gardenAlertChannels({ ...settings, useBirdChannels: true })).toBe(0);
        expect(gardenAlertChannels({ ...settings, useBirdChannels: true, birdEnabled: { ...none, telegram: true, discord: true, pushover: true } })).toBe(2);
        // Off is off: the feature or its alerts.
        expect(gardenAlertChannels({ ...settings, enabled: false })).toBe(0);
        expect(gardenAlertChannels({ ...settings, beta: false })).toBe(0);
    });

    it('does not count a chosen Garden channel that has no credentials: its sender returns before any request', () => {
        const settings = { beta: true, enabled: true, useBirdChannels: false, selected: ['telegram', 'email'], birdEnabled: none, deliverable: none };
        expect(gardenAlertChannels(settings)).toBe(0);
        expect(gardenAlertChannels({ ...settings, deliverable: { ...none, email: true } })).toBe(1);
    });
});

describe('a notification channel is on only when it can deliver', () => {
    interface ChannelCase { name: string; notifications: NotificationCredentials; can_deliver: Record<string, boolean> }
    // The cases the server's `channel_configured` is tested against (backend/tests/pure).
    const shared = backendJson<{ cases: ChannelCase[] }>('tests/fixtures/notification_channel_cases.json');

    it.each(shared.cases)('$name', ({ notifications, can_deliver }) => {
        expect(deliverableChannels(notifications)).toEqual(can_deliver);
    });

    it('treats a blank or whitespace credential as not saved', () => {
        expect(deliverableChannels({ telegram: { bot_token: '  ', chat_id: '42' } }).telegram).toBe(false);
        expect(deliverableChannels({ discord: { webhook_url: '' } }).discord).toBe(false);
    });

    it('does not count Telegram switched on with no token or chat', () => {
        const enabled = { discord: false, telegram: true, pushover: false, email: false };
        expect(birdDeliveryChannels(enabled, deliverableChannels({}))).toEqual([]);
        expect(birdDeliveryChannels(enabled, deliverableChannels({ telegram: { bot_token: 't', chat_id: '1' } }))).toEqual(['telegram']);
        // Credentials alone send nothing while the channel is off.
        expect(birdDeliveryChannels({ ...enabled, telegram: false }, deliverableChannels({ telegram: { bot_token: 't', chat_id: '1' } }))).toEqual([]);
    });
});

describe('requests nobody presses a button for', () => {
    it('lists the deletion request sent when the last telemetry opt-in is switched off', () => {
        expect(groups(owner).telemetry_forget).toBe('server');
        expect(states(owner).telemetry_forget).toBe('on_use');
    });

    it('lists the automatic download of Garden\'s check model, which follows Garden being on', () => {
        expect(groups(owner).garden_model).toBe('server');
        expect(states({ ...owner, garden: false }).garden_model).toBe('off');
        expect(states({ ...owner, garden: true }).garden_model).toBe('on');
        expect(states({ ...owner, garden: null }).garden_model).toBe('unknown');
    });
});

describe('the list and the backend registry of outbound requests', () => {
    const registry = backendJson<{ entries: Array<{ key: string; group: string }> }>('outbound_requests.json');

    it('have the same rows in the same groups, so a registered request always has a row and a row a reason', () => {
        const listed = Object.fromEntries(outboundRequests(owner).map((request) => [request.key, request.group]));
        const registered = Object.fromEntries(registry.entries.map((entry) => [entry.key, entry.group]));
        expect(listed).toEqual(registered);
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
        birdChannels: null, gardenChannels: null, garden: null, locationSet: null, locationAutomatic: null
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

describe('which requests lead the list on About', () => {
    it('leads with what is or may be sent, and folds away only what certainly is not sent now', () => {
        const table: Record<OutboundState, boolean> = { on: true, always: true, unknown: true, off: false, on_use: false };
        for (const [state, leads] of Object.entries(table) as Array<[OutboundState, boolean]>) {
            expect(leadsOutboundList(state), state).toBe(leads);
        }
    });

    it('never folds a request a guest cannot see the setting for', () => {
        const guest: OutboundFacts = {
            ...owner, owner: false, llmKey: null, telemetryUsage: null, telemetryHealth: null, updateChecks: null,
            birdweather: null, birdweatherToken: null, inaturalistSubmissions: null, inaturalistConnected: null,
            birdChannels: null, gardenChannels: null, garden: null, locationSet: null, locationAutomatic: null
        };
        const unknown = outboundRequests(guest).filter((request) => request.state === 'unknown');
        expect(unknown.map((request) => request.key)).toEqual(expect.arrayContaining(['weather', 'notify', 'birdweather', 'telemetry']));
        for (const request of unknown) expect(leadsOutboundList(request.state), request.key).toBe(true);
    });
});

