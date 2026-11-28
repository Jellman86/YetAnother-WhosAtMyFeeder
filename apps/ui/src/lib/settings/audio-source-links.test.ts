import { describe, expect, it } from 'vitest';

import type { AudioSourceOption } from '../api/audio';
import {
    addLinkToken,
    describeLinkToken,
    linkTokens,
    relinkByStreamId,
    renamedLinks,
    sameLinkToken,
    sourceLines,
    sourceLinkLabel
} from './audio-source-links';

const esp32: AudioSourceOption = {
    source_name: 'ESP32 v3.0 X',
    mapping_value: 'rtsp_52d54d7d',
    source_id: 'rtsp_52d54d7d',
    source_node: 'Quark',
    last_seen: '2026-11-28T08:00:00Z',
    names: [
        { name: 'ESP32 v3.0 X', last_seen: '2026-11-28T08:00:00Z', current: true, offer_link_by_id: false },
        { name: 'ESP32 v3.0', last_seen: '2026-11-27T09:00:00Z', current: false, offer_link_by_id: true }
    ]
};

const reolink: AudioSourceOption = {
    source_name: 'Reolink TEST',
    mapping_value: 'rtsp_68763a4d',
    source_id: 'rtsp_68763a4d',
    source_node: 'Quark',
    last_seen: '2026-11-28T08:30:00Z',
    names: [
        { name: 'Reolink TEST', last_seen: '2026-11-28T08:30:00Z', current: true, offer_link_by_id: false },
        { name: 'Reolink', last_seen: null, current: false, offer_link_by_id: true }
    ]
};

const patio: AudioSourceOption = {
    source_name: 'Patio Mic',
    mapping_value: 'Patio  Mic',
    source_id: null,
    source_node: 'Quark',
    last_seen: '2026-11-01T09:00:00Z',
    names: [{ name: 'Patio Mic', last_seen: '2026-11-01T09:00:00Z', current: true, offer_link_by_id: false }]
};

const sources = [esp32, reolink, patio];

function sharedCard(node: string, name: string, lastSeen: string): AudioSourceOption {
    return {
        installs_sharing_id: ['House', 'Shed'],
        source_name: name,
        mapping_value: 'audio_card_22a9b331',
        source_id: 'audio_card_22a9b331',
        source_node: node,
        last_seen: lastSeen,
        names: [{ name, last_seen: lastSeen, current: true, offer_link_by_id: false }]
    };
}

describe('comparing links as the server matches them', () => {
    it('trims and folds case fully, and nothing more', () => {
        expect(sameLinkToken(' Straße ', 'STRASSE')).toBe(true);
        expect(sameLinkToken('RTSP_52D54D7D', 'rtsp_52d54d7d')).toBe(true);
        expect(sameLinkToken('Garden  Mic', 'Garden Mic')).toBe(false);
    });

    it('splits a typed link the way the server reads it', () => {
        expect(linkTokens('ESP32 v3.0, rtsp_52d54d7d;Reolink\n|')).toEqual(['ESP32 v3.0', 'rtsp_52d54d7d', 'Reolink']);
        expect(linkTokens(undefined)).toEqual([]);
    });
});

describe('linking a camera to a BirdNET-Go source', () => {
    it('offers a stream by its current name and id, and saves the id', () => {
        expect(sourceLinkLabel(esp32)).toBe('ESP32 v3.0 X · rtsp_52d54d7d');
        expect(sourceLinkLabel(patio)).toBe('Patio Mic');
        expect(addLinkToken(['ESP32 v2.4'], esp32.mapping_value)).toEqual(['ESP32 v2.4', 'rtsp_52d54d7d']);
        expect(addLinkToken(['RTSP_52D54D7D'], esp32.mapping_value)).toEqual(['RTSP_52D54D7D']);
        expect(addLinkToken(['Patio Mic'], '  ')).toEqual(['Patio Mic']);
    });

    it('saves a source without an id by the name its calls carry, spaces and all', () => {
        expect(addLinkToken([], patio.mapping_value)).toEqual(['Patio  Mic']);
        expect(addLinkToken(['Patio Mic'], patio.mapping_value)).toEqual(['Patio Mic', 'Patio  Mic']);
    });

    it('names the install on its own line whenever two installs send the stream id', () => {
        const shared = [sharedCard('House', 'House Mic', '2026-11-28T09:00:00Z'), sharedCard('Shed', 'Shed Mic', '2026-11-28T08:00:00Z')];
        expect(sourceLinkLabel(shared[1])).toBe('Shed Mic · audio_card_22a9b331 · Shed');
        expect(sourceLines(shared[1])).toEqual({ id: 'audio_card_22a9b331', install: 'Shed' });
        expect(sourceLines(esp32)).toEqual({ id: 'rtsp_52d54d7d', install: null });
        expect(sourceLines(patio)).toEqual({ id: null, install: null });
        expect(describeLinkToken('audio_card_22a9b331', shared)).toEqual({
            name: 'House Mic, Shed Mic',
            id: 'audio_card_22a9b331',
            install: 'House, Shed',
            lastHeard: '2026-11-28T09:00:00Z'
        });
        // The other install's stream may be beyond the list; the server still says the id is shared.
        expect(describeLinkToken('audio_card_22a9b331', [shared[0]])).toMatchObject({ install: 'House, Shed' });
    });

    it('names a nameless stream by its id once, with its install when the id is shared', () => {
        const card = 'audio_card_22a9b331';
        const nameless = (node: string): AudioSourceOption => ({ ...sharedCard(node, card, '2026-11-28T09:00:00Z'), names: [] });
        expect(sourceLinkLabel(nameless('Shed'))).toBe(`${card} · Shed`);
        expect(sourceLines(nameless('Shed'))).toEqual({ id: null, install: 'Shed' });
        const alone = { ...nameless('Shed'), installs_sharing_id: [] };
        expect(describeLinkToken(card, [alone])).toEqual({ name: card, id: null, install: null, lastHeard: '2026-11-28T09:00:00Z' });
    });

    it('shows a linked id as the stream it names, with the newest call carrying the id', () => {
        expect(describeLinkToken('RTSP_52d54d7d', sources)).toEqual({
            name: 'ESP32 v3.0 X',
            id: 'rtsp_52d54d7d',
            install: null,
            lastHeard: '2026-11-28T08:00:00Z'
        });
    });

    it('shows a name as typed, with the newest call under that name from any source', () => {
        const garden = (id: string, lastSeen: string, current: boolean): AudioSourceOption => ({
            ...esp32,
            source_name: current ? 'Garden' : 'Hedge',
            mapping_value: id,
            source_id: id,
            names: [{ name: 'Garden', last_seen: lastSeen, current, offer_link_by_id: false }]
        });
        const both = [garden('rtsp_a', '2026-11-01T09:00:00Z', false), garden('rtsp_b', '2026-11-25T09:00:00Z', true)];
        expect(describeLinkToken(' garden ', both)).toEqual({ name: 'garden', id: null, install: null, lastHeard: '2026-11-25T09:00:00Z' });
        expect(describeLinkToken('ESP32 v3.0', sources)).toEqual({ name: 'ESP32 v3.0', id: null, install: null, lastHeard: '2026-11-27T09:00:00Z' });
        expect(describeLinkToken('Reolink', sources)).toEqual({ name: 'Reolink', id: null, install: null, lastHeard: null });
    });

    it('shows a token that matches no known source verbatim, with no time', () => {
        expect(describeLinkToken('rtsp_deadbeef', sources)).toEqual({ name: 'rtsp_deadbeef', id: null, install: null, lastHeard: null });
    });
});

describe('a camera linked by a name its stream no longer uses', () => {
    it('says which stream the old name is now called, when the server offers it', () => {
        expect(renamedLinks(['ESP32 v3.0', 'ESP32 v2.4'], sources)).toEqual([{ token: 'ESP32 v3.0', source: esp32 }]);
        expect(renamedLinks(['reolink'], sources)).toEqual([{ token: 'reolink', source: reolink }]);
    });

    it('says nothing for a current name, an id, an unknown name, or a stream already linked by id', () => {
        expect(renamedLinks(['ESP32 v3.0 X', 'rtsp_68763a4d', 'Shed', 'Patio Mic'], sources)).toEqual([]);
        expect(renamedLinks(['Reolink', 'RTSP_68763A4D'], sources)).toEqual([]);
    });

    it('says nothing for an earlier name the server does not offer', () => {
        const unoffered = { ...esp32, names: (esp32.names ?? []).map((name) => ({ ...name, offer_link_by_id: false })) };
        expect(renamedLinks(['ESP32 v3.0'], [unoffered])).toEqual([]);
    });

    it('adds the id after the old name and keeps the name', () => {
        expect(relinkByStreamId(['ESP32 v3.0', 'ESP32 v2.4'], 'ESP32 v3.0', esp32)).toEqual([
            'ESP32 v3.0',
            'rtsp_52d54d7d',
            'ESP32 v2.4'
        ]);
    });

    it('adds the id and changes no other link, even one only display treats as the same', () => {
        const garden: AudioSourceOption = { ...esp32, mapping_value: 'rtsp_a', source_id: 'rtsp_a' };
        expect(relinkByStreamId(['Garden Mic', 'Pinar', 'Pınar'], 'Garden Mic', garden)).toEqual([
            'Garden Mic',
            'rtsp_a',
            'Pinar',
            'Pınar'
        ]);
        expect(relinkByStreamId(['ESP32 v3.0', 'esp32 v3.0'], 'ESP32 v3.0', esp32)).toEqual([
            'ESP32 v3.0',
            'rtsp_52d54d7d',
            'esp32 v3.0'
        ]);
    });

    it('adds nothing when the id is linked already', () => {
        expect(relinkByStreamId(['ESP32 v3.0', ' rtsp_52d54d7d '], 'ESP32 v3.0', esp32)).toEqual(['ESP32 v3.0', ' rtsp_52d54d7d ']);
    });

    it('compares names for display only: Pinar and Pınar share a date but neither is ever removed', () => {
        expect(sameLinkToken('Pinar', 'Pınar')).toBe(true);
        expect(relinkByStreamId(['Pınar', 'Pinar'], 'Pınar', esp32)).toEqual(['Pınar', 'rtsp_52d54d7d', 'Pinar']);
    });
});
