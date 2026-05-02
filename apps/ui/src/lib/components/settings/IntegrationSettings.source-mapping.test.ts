// @ts-nocheck - uses node:fs/node:path at vitest runtime; types are not in
// the app tsconfig and we don't want to add @types/node for one guard file.
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const componentSource = readFileSync(
    resolve(__dirname, 'IntegrationSettings.svelte'),
    'utf8'
);

describe('IntegrationSettings BirdNET source mapping helper', () => {
    it('keeps manual text mapping while adding detected source picker controls', () => {
        expect(componentSource).toContain('addCameraAudioSource');
        expect(componentSource).toContain('removeCameraAudioSourceToken');
        expect(componentSource).toContain('mappingTokensFor');
        expect(componentSource).toContain('settings.integrations.birdnet.add_detected_source');
        expect(componentSource).toContain('settings.integrations.birdnet.source_token_remove');
        expect(componentSource).toContain('bind:value={cameraAudioMapping[camera]}');
        expect(componentSource).toContain('<select');
    });
});
