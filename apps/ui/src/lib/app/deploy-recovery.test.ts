import { afterEach, describe, expect, it, vi } from 'vitest';
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

    it('treats a stable-labelled bundle and an unlabelled backend of the same build as one deployment (#432)', () => {
        const reload = vi.fn();
        const warn = vi.fn();
        const recovery = createDeployRecovery({
            appVersion: '2.19.4-stable+e6f3ea6',
            storage: createStorage(),
            reload,
            warn
        });

        expect(recovery.observeHealth({ version: '2.19.4+e6f3ea6' })).toBe('ignore');
        expect(recovery.observeHealth({ version: '2.19.4+e6f3ea6' })).toBe('ignore');
        expect(reload).not.toHaveBeenCalled();
        expect(warn).not.toHaveBeenCalled();
    });

    it('still reloads a stable bundle when the backend moves to a new build', () => {
        const reload = vi.fn();
        const recovery = createDeployRecovery({
            appVersion: '2.19.4-stable+e6f3ea6',
            storage: createStorage(),
            reload,
            warn: vi.fn()
        });

        expect(recovery.observeHealth({ version: '2.19.5+0badf00' })).toBe('reload');
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
        const recovery = createDeployRecovery({
            appVersion: '2.9.1-dev+old',
            storage,
            reload: vi.fn(),
            warn: vi.fn()
        });

        expect(recovery.getRecoveryCount()).toBe(0);

        // First trigger → reload, count goes to 1
        recovery.observeHealth({ version: '2.9.2-dev+new' });
        expect(recovery.getRecoveryCount()).toBe(1);

        // Second trigger → warn (same signature), count goes to 2
        recovery.observeHealth({ version: '2.9.2-dev+new' });
        expect(recovery.getRecoveryCount()).toBe(2);
    });
});

/**
 * A failed import looks the same whether a deploy removed the chunk or the browser ended the load
 * because the reader is going elsewhere (Safari does this as a navigation starts, and gives no
 * beforeunload on iPhone). So the server is asked which build it runs, and only a different build
 * reloads; the tab's one automatic reload is spent only when that reload happens.
 */
describe('a failed import', () => {
    afterEach(() => {
        vi.useRealTimers();
    });

    const IMPORT_FAILED = { message: 'Importing a module script failed.' };

    function setUp(answer: () => Promise<{ version?: string } | null>, storage = createStorage()) {
        const reload = vi.fn();
        const warn = vi.fn();
        const report = vi.fn();
        const readDeployment = vi.fn(answer);
        const recovery = createDeployRecovery({ appVersion: '2.9.1-dev+old', storage, reload, warn, report, readDeployment, deploymentCheckMs: 5000 });
        return { recovery, reload, warn, report, readDeployment, storage };
    }

    it('on the same build does not reload, warn or spend the attempt: the route offers its own retry', async () => {
        vi.useFakeTimers();
        const storage = createStorage();
        const same = setUp(async () => ({ version: '2.9.1-dev+old' }), storage);
        expect(same.recovery.handleRuntimeFailure(IMPORT_FAILED)).toBe('checking');
        await vi.advanceTimersByTimeAsync(0);
        expect(same.reload).not.toHaveBeenCalled();
        expect(same.warn).not.toHaveBeenCalled();
        expect(same.report).not.toHaveBeenCalled();

        // The attempt is still there for a real deploy later in the same tab.
        const later = setUp(async () => ({ version: '2.9.2-dev+new' }), storage);
        later.recovery.handleRuntimeFailure(IMPORT_FAILED);
        await vi.advanceTimersByTimeAsync(0);
        expect(later.reload).toHaveBeenCalledTimes(1);
    });

    it('on a different build reloads once, spending the attempt as it reloads', async () => {
        vi.useFakeTimers();
        const { recovery, reload, warn, report, storage } = setUp(async () => ({ version: '2.9.2-dev+new' }));
        recovery.handleRuntimeFailure(IMPORT_FAILED);
        expect(storage.getItem('yawamf_deploy_recovery_attempt_v1')).toBeNull();
        await vi.advanceTimersByTimeAsync(0);
        expect(reload).toHaveBeenCalledTimes(1);
        expect(warn).not.toHaveBeenCalled();
        expect(report).toHaveBeenCalledWith({ action: 'reload', reason: 'runtime_failure', frontendVersion: '2.9.1-dev+old', backendVersion: '2.9.2-dev+new' });
        expect(storage.getItem('yawamf_deploy_recovery_attempt_v1')).toContain('2.9.2-dev+new');
        // One deploy, one reload: the pushed status naming the same build does not reload again.
        expect(recovery.observeHealth({ version: '2.9.2-dev+new' })).toBe('warn');
        expect(reload).toHaveBeenCalledTimes(1);
    });

    it('after the reload it caused, a reloaded page on the same old build says Refresh rather than looping', async () => {
        vi.useFakeTimers();
        const first = setUp(async () => ({ version: '2.9.2-dev+new' }));
        first.recovery.handleRuntimeFailure(IMPORT_FAILED);
        await vi.advanceTimersByTimeAsync(0);
        const again = setUp(async () => ({ version: '2.9.2-dev+new' }), first.storage);
        again.recovery.handleRuntimeFailure(IMPORT_FAILED);
        await vi.advanceTimersByTimeAsync(0);
        expect(again.reload).not.toHaveBeenCalled();
        expect(again.warn).toHaveBeenCalledTimes(1);
    });

    it('when the server cannot be asked, does not reload and shows the Refresh message', async () => {
        vi.useFakeTimers();
        const { recovery, reload, warn, storage } = setUp(async () => {
            throw new TypeError('Load failed');
        });
        recovery.handleRuntimeFailure(IMPORT_FAILED);
        await vi.advanceTimersByTimeAsync(0);
        expect(reload).not.toHaveBeenCalled();
        expect(warn).toHaveBeenCalledTimes(1);
        expect(storage.getItem('yawamf_deploy_recovery_attempt_v1')).toBeNull();
    });

    it('when the server does not answer in time, does not reload and shows the Refresh message', async () => {
        vi.useFakeTimers();
        const { recovery, reload, warn } = setUp(() => new Promise(() => undefined));
        recovery.handleRuntimeFailure(IMPORT_FAILED);
        await vi.advanceTimersByTimeAsync(4999);
        expect(warn).not.toHaveBeenCalled();
        await vi.advanceTimersByTimeAsync(1);
        expect(reload).not.toHaveBeenCalled();
        expect(warn).toHaveBeenCalledTimes(1);
    });

    it('two failures together ask once and reload once, with no Refresh message flashed first', async () => {
        vi.useFakeTimers();
        const { recovery, reload, warn, readDeployment } = setUp(async () => ({ version: '2.9.2-dev+new' }));
        recovery.handleRuntimeFailure(IMPORT_FAILED);
        recovery.handleRuntimeFailure({ message: 'Failed to fetch dynamically imported module' });
        await vi.advanceTimersByTimeAsync(0);
        // A third, while the page is already reloading, says nothing either.
        recovery.handleRuntimeFailure(IMPORT_FAILED);
        await vi.advanceTimersByTimeAsync(0);
        expect(readDeployment).toHaveBeenCalledTimes(1);
        expect(reload).toHaveBeenCalledTimes(1);
        expect(warn).not.toHaveBeenCalled();
    });

    it('a leave the reader cancels cannot swallow the reload: it happens as the server answers, with nothing left waiting', async () => {
        // Settings asks "Leave site?" when there are unsaved changes. Nothing here waits on a timer or
        // reads whether the page is leaving, so choosing Stay leaves no reload skipped and no attempt spent.
        vi.useFakeTimers();
        const { recovery, reload } = setUp(async () => ({ version: '2.9.2-dev+new' }));
        recovery.handleRuntimeFailure(IMPORT_FAILED);
        await vi.advanceTimersByTimeAsync(0);
        expect(reload).toHaveBeenCalledTimes(1);
        expect(vi.getTimerCount()).toBe(0);
        expect(recovery.observeHealth({ version: '2.9.3-dev+newer' })).toBe('reload');
        expect(vi.getTimerCount()).toBe(0);
    });

    it('without a way to ask the server, never reloads on a failed import', async () => {
        vi.useFakeTimers();
        const reload = vi.fn();
        const warn = vi.fn();
        const recovery = createDeployRecovery({ appVersion: '2.9.1-dev+old', storage: createStorage(), reload, warn });
        recovery.handleRuntimeFailure(IMPORT_FAILED);
        await vi.advanceTimersByTimeAsync(0);
        expect(reload).not.toHaveBeenCalled();
        expect(warn).toHaveBeenCalledTimes(1);
    });
});
