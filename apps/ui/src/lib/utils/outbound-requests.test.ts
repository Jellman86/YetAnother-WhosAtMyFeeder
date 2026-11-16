import { describe, expect, it } from 'vitest';
import { outboundRequests, type OutboundFacts } from './outbound-requests';

const owner: OutboundFacts = {
    owner: true,
    ebird: false,
    llm: false,
    telemetry: false,
    updateChecks: true,
    birdweather: false,
    inaturalistSubmissions: false,
    notificationChannels: 0,
    locationSet: false,
    locationAutomatic: true
};

function states(facts: OutboundFacts): Record<string, string> {
    return Object.fromEntries(outboundRequests(facts).map((request) => [request.key, request.state]));
}

function origins(facts: OutboundFacts): Record<string, string> {
    return Object.fromEntries(outboundRequests(facts).map((request) => [request.key, request.origin]));
}

describe('what leaves the network, from the features that send it', () => {
    it('lists the requests every viewer\'s browser makes, apart from the server\'s', () => {
        const from = origins(owner);
        expect(from.fonts).toBe('browser');
        expect(from.photos).toBe('browser');
        expect(from.osm).toBe('browser');
        expect(from.gbif_tiles).toBe('browser');
        expect(from.inat).toBe('server');
        expect(from.wikipedia).toBe('server');
        expect(from.llm).toBe('server');
    });

    it('names Google Fonts and Wikipedia, which load on every install', () => {
        const state = states(owner);
        expect(state.fonts).toBe('always');
        expect(state.wikipedia).toBe('always');
        expect(state.inat).toBe('always');
        expect(state.photos).toBe('always');
    });

    it('does not tie the map tiles to eBird: the location map and range maps draw them too', () => {
        expect(states({ ...owner, ebird: false }).osm).toBe('on_use');
        expect(states({ ...owner, ebird: true }).osm).toBe('on_use');
        expect(states({ ...owner, ebird: false }).ebird).toBe('off');
        expect(states({ ...owner, ebird: true }).ebird).toBe('on');
    });

    it('turns each optional request on by its own setting', () => {
        const all = states({
            ...owner, llm: true, telemetry: true, birdweather: true, inaturalistSubmissions: true, notificationChannels: 2
        });
        for (const key of ['llm', 'telemetry', 'birdweather', 'inat_submit', 'notify', 'updates']) expect(all[key], key).toBe('on');
        const none = states({ ...owner, updateChecks: false });
        for (const key of ['llm', 'telemetry', 'birdweather', 'inat_submit', 'notify', 'updates']) expect(none[key], key).toBe('off');
    });

    it('asks for weather only where the feeder has a location, and looks one up by IP only when none is set', () => {
        expect(states({ ...owner, locationSet: true, locationAutomatic: false })).toMatchObject({ weather: 'on', geolocate: 'off' });
        expect(states({ ...owner, locationSet: true, locationAutomatic: true })).toMatchObject({ weather: 'on', geolocate: 'off' });
        expect(states({ ...owner, locationSet: false, locationAutomatic: true })).toMatchObject({ weather: 'on', geolocate: 'on' });
        expect(states({ ...owner, locationSet: false, locationAutomatic: false })).toMatchObject({ weather: 'off', geolocate: 'off' });
    });

    it('marks what only happens when someone starts it', () => {
        const state = states(owner);
        expect(state.places).toBe('on_use');
        expect(state.downloads).toBe('on_use');
        expect(state.gbif_tiles).toBe('on_use');
    });

    it('does not guess for a guest: settings a guest cannot read are owner only', () => {
        const guest = states({
            owner: false, ebird: true, llm: false, telemetry: null, updateChecks: null, birdweather: null,
            inaturalistSubmissions: null, notificationChannels: null, locationSet: null, locationAutomatic: null
        });
        expect(guest.ebird).toBe('on');
        expect(guest.llm).toBe('off');
        for (const key of ['telemetry', 'updates', 'birdweather', 'inat_submit', 'notify', 'weather', 'geolocate']) {
            expect(guest[key], key).toBe('unknown');
        }
        expect(guest.fonts).toBe('always');
    });

    it('lists the server\'s requests before the browser\'s, each once', () => {
        const requests = outboundRequests(owner);
        const firstBrowser = requests.findIndex((request) => request.origin === 'browser');
        expect(requests.slice(firstBrowser).every((request) => request.origin === 'browser')).toBe(true);
        expect(new Set(requests.map((request) => request.key)).size).toBe(requests.length);
    });
});
