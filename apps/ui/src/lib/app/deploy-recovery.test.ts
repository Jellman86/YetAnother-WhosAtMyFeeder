import { describe, expect, it, vi } from 'vitest';
import { createDeployRecovery, isLikelyStaleBundleError } from './deploy-recovery';

function createStorage() {
    const map = new Map<string, string>();
    return {
        getItem: (key: string) => map.get(key) ?? null,
        setItem: (key: string, value: string) => {
            map.set(key, value);
        },
        removeItem: (key: string) => {
            map.delete(key);
        }
    };
}

describe('isLikelyStaleBundleError', () => {
    it('matches dynamic import and chunk-load failures', () => {
        expect(isLikelyStaleBundleError({ message: 'Failed to fetch dynamically imported module' })).toBe(true);
        expect(isLikelyStaleBundleError({ message: 'error loading dynamically imported module' })).toBe(true);
        expect(isLikelyStaleBundleError({ message: 'ChunkLoadError: Loading chunk 7 failed.' })).toBe(true);
        expect(isLikelyStaleBundleError({ name: 'ChunkLoadError', message: 'Loading chunk app failed' })).toBe(true);
    });

    it('ignores generic runtime errors', () => {
        expect(isLikelyStaleBundleError({ message: 'Cannot read properties of undefined' })).toBe(false);
        expect(isLikelyStaleBundleError({ message: 'Network request failed' })).toBe(false);
    });
});

describe('createDeployRecovery', () => {
    it('reloads once for a stale-bundle runtime failure signature', () => {
        const storage = createStorage();
        const reload = vi.fn();
        const warn = vi.fn();
        const recovery = createDeployRecovery({
            appVersion: '2.9.1-dev+old',
            storage,
            reload,
            warn
        });

        const result = recovery.handleRuntimeFailure({
            message: 'error loading dynamically imported module: http://127.0.0.1:9852/assets/leaflet-src-DYyUWJOP.js'
        });

        expect(result).toBe('reload');
        expect(reload).toHaveBeenCalledTimes(1);
        expect(warn).not.toHaveBeenCalled();
    });

    it('warns instead of reloading again for the same stale-bundle runtime signature', () => {
        const storage = createStorage();
        const reload = vi.fn();
        const warn = vi.fn();
        const recovery = createDeployRecovery({
            appVersion: '2.9.1-dev+old',
            storage,
            reload,
            warn
        });

        recovery.handleRuntimeFailure({
            message: 'Failed to fetch dynamically imported module'
        });
        const result = recovery.handleRuntimeFailure({
            message: 'Failed to fetch dynamically imported module'
        });

        expect(result).toBe('warn');
        expect(reload).toHaveBeenCalledTimes(1);
        expect(warn).toHaveBeenCalledTimes(1);
    });

    it('ignores generic runtime failures', () => {
        const recovery = createDeployRecovery({
            appVersion: '2.9.1-dev+old',
            storage: createStorage(),
            reload: vi.fn(),
            warn: vi.fn()
        });

        expect(recovery.handleRuntimeFailure({ message: 'Cannot read properties of undefined' })).toBe('ignore');
    });

    it('reloads once when backend health reports a different build version', () => {
        const storage = createStorage();
        const reload = vi.fn();
        const warn = vi.fn();
        const recovery = createDeployRecovery({
            appVersion: '2.9.1-dev+old',
            storage,
            reload,
            warn
        });

        const result = recovery.observeHealth({
            version: '2.9.1-dev+new',
            startup_instance_id: '20260331T181749.290664Z-1'
        });

        expect(result).toBe('reload');
        expect(reload).toHaveBeenCalledTimes(1);
        expect(warn).not.toHaveBeenCalled();
    });

    it('warns instead of reloading again for the same backend/frontend version mismatch', () => {
        const storage = createStorage();
        const reload = vi.fn();
        const warn = vi.fn();
        const recovery = createDeployRecovery({
            appVersion: '2.9.1-dev+old',
            storage,
            reload,
            warn
        });

        recovery.observeHealth({
            version: '2.9.1-dev+new',
            startup_instance_id: 'instance-1'
        });
        const result = recovery.observeHealth({
            version: '2.9.1-dev+new',
            startup_instance_id: 'instance-2'
        });

        expect(result).toBe('warn');
        expect(reload).toHaveBeenCalledTimes(1);
        expect(warn).toHaveBeenCalledTimes(1);
    });

    it('clears any mismatch marker once frontend and backend versions align again', () => {
        const storage = createStorage();
        const reload = vi.fn();
        const warn = vi.fn();
        const recovery = createDeployRecovery({
            appVersion: '2.9.1-dev+new',
            storage,
            reload,
            warn
        });

        recovery.observeHealth({
            version: '2.9.1-dev+old',
            startup_instance_id: 'instance-1'
        });
        expect(reload).toHaveBeenCalledTimes(1);

        const aligned = recovery.observeHealth({
            version: '2.9.1-dev+new',
            startup_instance_id: 'instance-2'
        });

        expect(aligned).toBe('ignore');
        const nextMismatch = recovery.observeHealth({
            version: '2.9.1-dev+future',
            startup_instance_id: 'instance-3'
        });
        expect(nextMismatch).toBe('reload');
        expect(reload).toHaveBeenCalledTimes(2);
    });

    it('increments recovery count on every trigger and exposes it via getRecoveryCount', () => {
        const storage = createStorage();
        const reload = vi.fn();
        const warn = vi.fn();
        const recovery = createDeployRecovery({
            appVersion: '2.9.1-dev+old',
            storage,
            reload,
            warn
        });

        expect(recovery.getRecoveryCount()).toBe(0);

        // First trigger → reload, count goes to 1
        recovery.handleRuntimeFailure({
            message: 'Failed to fetch dynamically imported module'
        });
        expect(recovery.getRecoveryCount()).toBe(1);

        // Second trigger → warn (same signature), count goes to 2
        recovery.handleRuntimeFailure({
            message: 'Failed to fetch dynamically imported module'
        });
        expect(recovery.getRecoveryCount()).toBe(2);
    });
});
