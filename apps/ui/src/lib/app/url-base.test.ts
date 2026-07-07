import { describe, expect, it } from 'vitest';

import {
    HA_INGRESS_BASE_PATH,
    appApiPath,
    detectAppBasePath,
    fromAppPath,
    normalizeBackendPath,
    toAppPath
} from './url-base';

describe('url-base helpers', () => {
    it('keeps direct-root builds unchanged', () => {
        expect(toAppPath('/events')).toBe('/events');
        expect(fromAppPath('/events')).toBe('/events');
        expect(appApiPath('/frigate/test')).toBe('/api/frigate/test');
        expect(normalizeBackendPath('/api/frigate/test')).toBe('/api/frigate/test');
    });

    it('detects Home Assistant ingress paths at runtime', () => {
        expect(detectAppBasePath('/')).toBe('');
        expect(detectAppBasePath('/events')).toBe('');
        expect(detectAppBasePath(HA_INGRESS_BASE_PATH)).toBe(HA_INGRESS_BASE_PATH);
        expect(detectAppBasePath(`${HA_INGRESS_BASE_PATH}/events`)).toBe(HA_INGRESS_BASE_PATH);
    });
});
