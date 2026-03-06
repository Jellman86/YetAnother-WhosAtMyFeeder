import { describe, expect, it } from 'vitest';
import {
    APPLE_TOUCH_ICON_URL,
    APP_ICON_192_URL,
    FAVICON_ICO_URL,
    FAVICON_PNG_URL,
    FRIGATE_LOGO_URL,
    ICON_ASSET_VERSION,
    MANIFEST_URL,
    withAssetVersion,
} from './assets';

describe('icon asset versioning', () => {
    it('appends the shared version token to icon-like assets', () => {
        expect(withAssetVersion('/favicon.png')).toBe(`/favicon.png?v=${ICON_ASSET_VERSION}`);
        expect(FAVICON_ICO_URL).toBe(`/favicon.ico?v=${ICON_ASSET_VERSION}`);
        expect(FAVICON_PNG_URL).toBe(`/favicon.png?v=${ICON_ASSET_VERSION}`);
        expect(APPLE_TOUCH_ICON_URL).toBe(`/apple-touch-icon.png?v=${ICON_ASSET_VERSION}`);
        expect(APP_ICON_192_URL).toBe(`/pwa-192x192.png?v=${ICON_ASSET_VERSION}`);
        expect(FRIGATE_LOGO_URL).toBe(`/frigate-logo.png?v=${ICON_ASSET_VERSION}`);
        expect(MANIFEST_URL).toBe(`/manifest.json?v=${ICON_ASSET_VERSION}`);
    });
});
