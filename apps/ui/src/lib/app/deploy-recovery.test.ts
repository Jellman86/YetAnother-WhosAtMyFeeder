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

    it.each(['', 'unknown'])('does not recover without a concrete frontend identity (%j)', (appVersion) => {
        const reload = vi.fn();
        const warn = vi.fn();
        const recovery = createDeployRecovery({
            appVersion,
            storage: createStorage(),
            reload,
            warn
        });

        expect(recovery.handleRuntimeFailure({ message: 'ChunkLoadError: Loading chunk 7 failed.' })).toBe(
            'ignore'
        );
        expect(recovery.observeHealth({ version: '2.9.2-dev+new' })).toBe('ignore');
        expect(reload).not.toHaveBeenCalled();
        expect(warn).not.toHaveBeenCalled();
    });

    it('warns without reloading when session storage is unavailable', () => {
        const reload = vi.fn();
        const warn = vi.fn();
        const recovery = createDeployRecovery({
            appVersion: '2.9.1-dev+old',
            storage: null,
            reload,
            warn
        });

        expect(recovery.observeHealth({ version: '2.9.2-dev+new' })).toBe('warn');
        expect(recovery.observeHealth({ version: '2.9.2-dev+new' })).toBe('warn');
        expect(reload).not.toHaveBeenCalled();
        expect(warn).toHaveBeenCalledTimes(1);
    });

    it('reloads for a concrete dev build hash change', () => {
        const storage = createStorage();
        const reload = vi.fn();
        const warn = vi.fn();
        const recovery = createDeployRecovery({
            appVersion: '2.9.1-dev+a1b2c3d',
            storage,
            reload,
            warn
        });

        const result = recovery.observeHealth({
            version: '2.9.1-dev+e4f5a6b',
            startup_instance_id: '20260331T181749.290664Z-1'
        });

        expect(result).toBe('reload');
        expect(reload).toHaveBeenCalledTimes(1);
        expect(warn).not.toHaveBeenCalled();
    });

    it('ignores unavailable build metadata when the semver identity matches', () => {
        const reload = vi.fn();
        const recovery = createDeployRecovery({
            appVersion: '2.9.1-dev+unknown',
            storage: createStorage(),
            reload,
            warn: vi.fn()
        });

        expect(recovery.observeHealth({ version: '2.9.1-dev+a1b2c3d' })).toBe('ignore');
        expect(reload).not.toHaveBeenCalled();
    });

    it('still reloads when the semver core actually changes', () => {
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
            version: '2.9.2-dev+new',
            startup_instance_id: 'instance-1'
        });

        expect(result).toBe('reload');
        expect(reload).toHaveBeenCalledTimes(1);
    });

    it('reloads when transitioning from dev prerelease to a release build of the same version', () => {
        const storage = createStorage();
        const reload = vi.fn();
        const recovery = createDeployRecovery({
            appVersion: '2.9.1-dev+old',
            storage,
            reload,
            warn: vi.fn()
        });

        const result = recovery.observeHealth({
            version: '2.9.1',
            startup_instance_id: 'instance-1'
        });

        expect(result).toBe('reload');
        expect(reload).toHaveBeenCalledTimes(1);
    });

    it('warns instead of reloading again for the same backend/frontend deployment mismatch', () => {
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
            version: '2.9.2-dev+new',
            startup_instance_id: 'instance-1'
        });
        const result = recovery.observeHealth({
            version: '2.9.2-dev+new',
            startup_instance_id: 'instance-2'
        });

        expect(result).toBe('warn');
        expect(reload).toHaveBeenCalledTimes(1);
        expect(warn).toHaveBeenCalledTimes(1);
    });

    it('makes a fresh bounded reload attempt when the backend deployment changes again', () => {
        const storage = createStorage();
        const reload = vi.fn();
        const recovery = createDeployRecovery({
            appVersion: '2.9.1-dev+old',
            storage,
            reload,
            warn: vi.fn()
        });

        expect(recovery.observeHealth({ version: '2.9.2-dev+new' })).toBe('reload');
        expect(recovery.observeHealth({ version: '2.9.2-dev+newer' })).toBe('reload');
        expect(reload).toHaveBeenCalledTimes(2);
    });

    it('does not reload again if health responses oscillate between attempted deployments', () => {
        const storage = createStorage();
        const reload = vi.fn();
        const warn = vi.fn();
        const recovery = createDeployRecovery({
            appVersion: '2.9.1-dev+old',
            storage,
            reload,
            warn
        });

        expect(recovery.observeHealth({ version: '2.9.2-dev+new' })).toBe('reload');
        expect(recovery.observeHealth({ version: '2.9.3-dev+newer' })).toBe('reload');
        expect(recovery.observeHealth({ version: '2.9.2-dev+new' })).toBe('warn');
        expect(reload).toHaveBeenCalledTimes(2);
        expect(warn).toHaveBeenCalledTimes(1);
    });

    it('emits at most one warning per unresolved deployment in one page lifetime', () => {
        const storage = createStorage();
        const warn = vi.fn();
        const recovery = createDeployRecovery({
            appVersion: '2.9.1-dev+old',
            storage,
            reload: vi.fn(),
            warn
        });

        recovery.observeHealth({ version: '2.9.2-dev+new' });
        expect(recovery.observeHealth({ version: '2.9.2-dev+new' })).toBe('warn');
        expect(recovery.observeHealth({ version: '2.9.2-dev+new' })).toBe('warn');
        expect(warn).toHaveBeenCalledTimes(1);
        expect(recovery.getRecoveryCount()).toBe(2);
    });

    it('reports bounded recovery actions with frontend and backend identities', () => {
        const storage = createStorage();
        const report = vi.fn();
        const recovery = createDeployRecovery({
            appVersion: '2.9.1-dev+old',
            storage,
            reload: vi.fn(),
            warn: vi.fn(),
            report
        });

        recovery.observeHealth({ version: '2.9.2-dev+new' });
        recovery.observeHealth({ version: '2.9.2-dev+new' });

        expect(report).toHaveBeenNthCalledWith(1, {
            action: 'reload',
            reason: 'version_mismatch',
            frontendVersion: '2.9.1-dev+old',
            backendVersion: '2.9.2-dev+new'
        });
        expect(report).toHaveBeenNthCalledWith(2, {
            action: 'warn',
            reason: 'version_mismatch',
            frontendVersion: '2.9.1-dev+old',
            backendVersion: '2.9.2-dev+new'
        });
    });

    it('accepts a new deployment target after frontend and backend identities align', () => {
        const storage = createStorage();
        const reload = vi.fn();
        const warn = vi.fn();
        const recovery = createDeployRecovery({
            appVersion: '2.9.2-dev+a1b2c3d',
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
            version: '2.9.2-dev+a1b2c3d',
            startup_instance_id: 'instance-2'
        });

        expect(aligned).toBe('ignore');
        const nextMismatch = recovery.observeHealth({
            version: '2.9.3-dev+future',
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
