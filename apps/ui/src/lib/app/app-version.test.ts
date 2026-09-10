import { describe, expect, it } from 'vitest';
import { RELEASE_LIKE_CHANNELS, composeAppVersion, deploymentIdentity, isReleaseLikeChannel } from './app-version';

describe('app version composition', () => {
    it('omits the label for every release-like channel, stable included', () => {
        for (const channel of RELEASE_LIKE_CHANNELS) {
            expect(composeAppVersion('2.19.4', channel, 'e6f3ea6')).toBe('2.19.4+e6f3ea6');
        }
    });

    it('treats a tag name as a release, as the backend does', () => {
        expect(isReleaseLikeChannel('v2.19.4')).toBe(true);
        expect(composeAppVersion('2.19.4', 'v2.19.4', 'e6f3ea6')).toBe('2.19.4+e6f3ea6');
    });

    it('keeps the label for a working channel', () => {
        expect(composeAppVersion('2.19.4', 'dev', 'e6f3ea6')).toBe('2.19.4-dev+e6f3ea6');
        expect(composeAppVersion('2.19.4', 'feature/x', 'e6f3ea6')).toBe('2.19.4-feature/x+e6f3ea6');
    });
});

describe('deployment identity', () => {
    it('is the same for a stable-labelled bundle and an unlabelled backend (#432)', () => {
        expect(deploymentIdentity('2.19.4-stable+e6f3ea6')).toBe('2.19.4');
        expect(deploymentIdentity('2.19.4+e6f3ea6')).toBe('2.19.4');
    });

    it('keeps a working channel distinct from a release', () => {
        expect(deploymentIdentity('2.19.4-dev+e6f3ea6')).toBe('2.19.4-dev');
        expect(deploymentIdentity('2.19.4')).toBe('2.19.4');
    });
});
