// @ts-nocheck - uses node:fs/node:path at vitest runtime; types are not in
// the app tsconfig and we don't want to add @types/node for one guard file.
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const componentSource = readFileSync(
    resolve(__dirname, 'BirdnetSettings.svelte'),
    'utf8'
);

describe('BirdNET-Go source mapping helper, set up with the cameras', () => {
    it('keeps manual text mapping while adding detected source picker controls', () => {
        expect(componentSource).toContain('addCameraAudioSource');
        expect(componentSource).toContain('removeCameraAudioSourceToken');
        expect(componentSource).toContain('mappingTokensFor');
        expect(componentSource).toContain('settings.integrations.birdnet.add_detected_source');
        expect(componentSource).toContain('settings.integrations.birdnet.source_token_remove');
        expect(componentSource).toContain('bind:value={cameraAudioMapping[camera]}');
        expect(componentSource).toContain('<select');
    });

    it('saves each detected stream by the value the server lists for it, from the picker and the recent list', () => {
        expect(componentSource).toContain('birdnetSourceOptions.map((source) => ({ value: source.mapping_value, label: sourceLinkLabel(source, birdnetSourceOptions) }))');
        expect(componentSource).toContain('{@const sourceValue = source.mapping_value}');
        expect(componentSource).toContain('addCameraAudioSource(availableCameras[0], sourceValue)');
    });

    it('names each linked token, says when it was last heard, and offers the rename swap', () => {
        expect(componentSource).toContain('describeLinkToken(sourceToken, birdnetSourceOptions)');
        expect(componentSource).toContain('settings.integrations.birdnet.source_last_heard');
        expect(componentSource).toContain('renamedLinks(mappingTokensFor(camera), birdnetSourceOptions)');
        expect(componentSource).toContain('settings.integrations.birdnet.source_link_by_id');
        // The remove target is at least 24 px (1.75rem at the 14 px root) and named by what the row shows.
        expect(componentSource).toContain('inline-flex h-7 w-7 shrink-0');
        expect(componentSource).toContain("values: { source: linked.name, camera }");
        // The last-heard time is a fact, not a warning.
        expect(componentSource).not.toMatch(/source_last_heard[^\n]*text-status/);
    });

    it('keeps separate BirdNET internal and browser URL settings', () => {
        expect(componentSource).toContain('birdnetExternalUrl');
        expect(componentSource).toContain('settings.integrations.birdnet.internal_url_label');
        expect(componentSource).toContain('settings.integrations.birdnet.external_url_label');
        expect(componentSource).toContain('id="birdnet-external-url"');
    });
});
