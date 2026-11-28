import { describe, expect, it } from 'vitest';

import type { AudioSourceOption } from '../api/audio';
import {
    addLinkToken,
    describeLinkToken,
    linkTokens,
    relinkByStreamId,
    renamedLinks,
    sourceLinkLabel
} from './audio-source-links';

const esp32: AudioSourceOption = {
    source_name: 'ESP32 v3.0 X',
    mapping_value: 'rtsp_52d54d7d',
    source_id: 'rtsp_52d54d7d',
    earlier_names: [{ name: 'ESP32 v3.0', last_seen: '2026-11-27T09:00:00Z', has_calls_without_id: false }],
    last_seen: '2026-11-28T08:00:00Z',
    seen_count: 3
};

const reolink: AudioSourceOption = {
    source_name: 'Reolink TEST',
    mapping_value: 'rtsp_68763a4d',
    source_id: 'rtsp_68763a4d',
    earlier_names: [{ name: 'Reolink', last_seen: '2026-11-12T09:00:00Z', has_calls_without_id: true }],
    last_seen: '2026-11-28T08:30:00Z',
    seen_count: 4078
};

const patio: AudioSourceOption = {
    source_name: 'Patio Mic',
    mapping_value: 'Patio Mic',
    source_id: null,
    earlier_names: [],
    last_seen: '2026-11-01T09:00:00Z',
    seen_count: 5
};

const sources = [esp32, reolink, patio];

describe('linking a camera to a BirdNET-Go source', () => {
    it('offers a stream by its current name and id, and saves the id', () => {
        expect(sourceLinkLabel(esp32)).toBe('ESP32 v3.0 X · rtsp_52d54d7d');
        expect(sourceLinkLabel(patio)).toBe('Patio Mic');
        // Both the picker and the recent list add the entry's mapping value.
        expect(addLinkToken(['ESP32 v2.4'], esp32.mapping_value)).toEqual(['ESP32 v2.4', 'rtsp_52d54d7d']);
        expect(addLinkToken(['RTSP_52D54D7D'], esp32.mapping_value)).toEqual(['RTSP_52D54D7D']);
        expect(addLinkToken(['Patio Mic'], '  ')).toEqual(['Patio Mic']);
    });

    it('splits a typed link the way the server reads it', () => {
        expect(linkTokens('ESP32 v3.0, rtsp_52d54d7d;Reolink\n|')).toEqual(['ESP32 v3.0', 'rtsp_52d54d7d', 'Reolink']);
        expect(linkTokens(undefined)).toEqual([]);
    });

    it('shows a linked id as the stream it names, with when it was last heard', () => {
        expect(describeLinkToken('RTSP_52d54d7d', sources)).toEqual({
            text: 'ESP32 v3.0 X · rtsp_52d54d7d',
            lastHeard: '2026-11-28T08:00:00Z'
        });
        expect(describeLinkToken(' patio mic ', sources)).toEqual({ text: 'patio mic', lastHeard: '2026-11-01T09:00:00Z' });
    });

    it('shows an earlier name as typed, with when a call last carried it', () => {
        expect(describeLinkToken('ESP32 v3.0', sources)).toEqual({
            text: 'ESP32 v3.0',
            lastHeard: '2026-11-27T09:00:00Z'
        });
    });

    it('shows a token that matches no known source verbatim, with no time', () => {
        expect(describeLinkToken('rtsp_deadbeef', sources)).toEqual({ text: 'rtsp_deadbeef', lastHeard: null });
        expect(describeLinkToken('Shed', sources)).toEqual({ text: 'Shed', lastHeard: null });
    });
});

describe('a camera linked by a name its stream no longer uses', () => {
    it('says which stream the old name is now called', () => {
        expect(renamedLinks(['ESP32 v3.0', 'ESP32 v2.4'], sources)).toEqual([
            { token: 'ESP32 v3.0', source: esp32 }
        ]);
    });

    it('says nothing for a current name, an id, an unknown name or a stream already linked by id', () => {
        expect(renamedLinks(['ESP32 v3.0 X', 'rtsp_68763a4d', 'Shed', 'Patio Mic'], sources)).toEqual([]);
        expect(renamedLinks(['Reolink', 'rtsp_68763a4d'], sources)).toEqual([]);
    });

    it('says nothing when the old name is another stream\'s current name', () => {
        const reused: AudioSourceOption = { ...patio, source_name: 'ESP32 v3.0', mapping_value: 'ESP32 v3.0' };
        expect(renamedLinks(['ESP32 v3.0'], [esp32, reused])).toEqual([]);
    });

    it('says nothing when two streams carried the old name', () => {
        const other: AudioSourceOption = { ...esp32, source_name: 'Hedge', mapping_value: 'rtsp_1', source_id: 'rtsp_1' };
        expect(renamedLinks(['ESP32 v3.0'], [esp32, other])).toEqual([]);
    });

    it('replaces the old name with the id when every call under it has an id', () => {
        expect(relinkByStreamId(['ESP32 v3.0', 'ESP32 v2.4'], 'ESP32 v3.0', esp32)).toEqual([
            'rtsp_52d54d7d',
            'ESP32 v2.4'
        ]);
    });

    it('adds the id and keeps the old name when calls from before ids still match it alone', () => {
        expect(relinkByStreamId(['Reolink'], 'Reolink', reolink)).toEqual(['Reolink', 'rtsp_68763a4d']);
    });
});
