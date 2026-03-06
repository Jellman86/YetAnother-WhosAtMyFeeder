export const ICON_ASSET_VERSION = '20260306-1';

export function withAssetVersion(path: string): string {
    return `${path}?v=${ICON_ASSET_VERSION}`;
}

export const FAVICON_ICO_URL = withAssetVersion('/favicon.ico');
export const FAVICON_PNG_URL = withAssetVersion('/favicon.png');
export const APPLE_TOUCH_ICON_URL = withAssetVersion('/apple-touch-icon.png');
export const MANIFEST_URL = withAssetVersion('/manifest.json');
export const APP_ICON_192_URL = withAssetVersion('/pwa-192x192.png');
export const APP_ICON_512_URL = withAssetVersion('/pwa-512x512.png');
export const FRIGATE_LOGO_URL = withAssetVersion('/frigate-logo.png');
