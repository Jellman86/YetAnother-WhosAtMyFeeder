export const HA_INGRESS_BASE_PATH = '/api/yawamf/ingress';

function normalizeBasePath(base: string | null | undefined): string {
    const trimmed = (base || '').trim();
    if (!trimmed || trimmed === '/') return '';
    const withLeading = trimmed.startsWith('/') ? trimmed : `/${trimmed}`;
    return withLeading.replace(/\/+$/, '');
}

export function detectAppBasePath(pathname: string | null | undefined): string {
    const path = pathname || '/';
    if (path === HA_INGRESS_BASE_PATH || path.startsWith(`${HA_INGRESS_BASE_PATH}/`)) {
        return HA_INGRESS_BASE_PATH;
    }
    return '';
}

export const APP_BASE_PATH = normalizeBasePath(
    typeof window !== 'undefined' ? detectAppBasePath(window.location.pathname) : ''
);

export function toAppPath(path: string): string {
    if (!path.startsWith('/')) return path;
    if (!APP_BASE_PATH) return path;
    if (path === APP_BASE_PATH || path.startsWith(`${APP_BASE_PATH}/`)) return path;
    return `${APP_BASE_PATH}${path}`;
}

export function fromAppPath(path: string): string {
    if (!APP_BASE_PATH) return path || '/';
    if (path === APP_BASE_PATH) return '/';
    if (path.startsWith(`${APP_BASE_PATH}/`)) {
        return path.slice(APP_BASE_PATH.length) || '/';
    }
    return path || '/';
}

export function appApiPath(path: string): string {
    const normalized = path.startsWith('/') ? path : `/${path}`;
    if (normalized === '/api' || normalized.startsWith('/api/')) {
        return toAppPath(normalized);
    }
    return toAppPath(`/api${normalized}`);
}

export function normalizeBackendPath(url: string): string {
    if (url.startsWith('/api/')) {
        return appApiPath(url);
    }
    if (url.startsWith('/')) {
        return toAppPath(url);
    }
    return url;
}
