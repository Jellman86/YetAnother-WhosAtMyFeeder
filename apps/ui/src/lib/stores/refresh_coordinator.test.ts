import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// Import a fresh instance for each test via dynamic import + module reset.
describe('RefreshCoordinator', () => {
    beforeEach(() => {
        vi.useFakeTimers();
        vi.resetModules();
        // Provide a minimal document.hidden stub (not hidden by default).
        Object.defineProperty(globalThis, 'document', {
            configurable: true,
            value: { hidden: false },
        });
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    it('register + onNavigate triggers callback after 150ms', async () => {
        const { refreshCoordinator } = await import('./refresh_coordinator.svelte');
        const cb = vi.fn().mockResolvedValue(undefined);

        refreshCoordinator.register(cb);
        refreshCoordinator.onNavigate();

        expect(cb).not.toHaveBeenCalled();

        await vi.advanceTimersByTimeAsync(150);

        expect(cb).toHaveBeenCalledTimes(1);
    });

    it('unregister before sweep means callback is not called', async () => {
        const { refreshCoordinator } = await import('./refresh_coordinator.svelte');
        const cb = vi.fn().mockResolvedValue(undefined);

        const unregister = refreshCoordinator.register(cb);
        refreshCoordinator.onNavigate();
        unregister();

        await vi.advanceTimersByTimeAsync(150);

        expect(cb).not.toHaveBeenCalled();
    });

    it('two rapid triggers produce only one sweep 150ms after the last (clear-and-reset)', async () => {
        const { refreshCoordinator } = await import('./refresh_coordinator.svelte');
        const cb = vi.fn().mockResolvedValue(undefined);

        refreshCoordinator.register(cb);

        // First trigger at t=0.
        refreshCoordinator.onNavigate();
        // Second trigger at t=100 (before the first timer fires).
        await vi.advanceTimersByTimeAsync(100);
        refreshCoordinator.onNavigate();

        // Advance to t=200 — 100ms after the second trigger but not yet 150ms.
        await vi.advanceTimersByTimeAsync(50);
        expect(cb).not.toHaveBeenCalled();

        // Now reach 150ms after the second trigger (t=250 total).
        await vi.advanceTimersByTimeAsync(100);
        expect(cb).toHaveBeenCalledTimes(1);
    });

    it('one throwing callback does not block subsequent callbacks', async () => {
        const { refreshCoordinator } = await import('./refresh_coordinator.svelte');
        const throwing = vi.fn().mockRejectedValue(new Error('boom'));
        const safe = vi.fn().mockResolvedValue(undefined);

        refreshCoordinator.register(throwing);
        refreshCoordinator.register(safe);
        refreshCoordinator.onNavigate();

        // Suppress the expected console.warn noise.
        const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined);

        await vi.advanceTimersByTimeAsync(150);
        // Flush microtasks so promise rejections are handled.
        await Promise.resolve();
        await Promise.resolve();

        expect(throwing).toHaveBeenCalledTimes(1);
        expect(safe).toHaveBeenCalledTimes(1);

        warnSpy.mockRestore();
    });

    it('onVisibilityChange when document.hidden does not trigger a sweep', async () => {
        const { refreshCoordinator } = await import('./refresh_coordinator.svelte');
        const cb = vi.fn().mockResolvedValue(undefined);

        Object.defineProperty(globalThis, 'document', {
            configurable: true,
            value: { hidden: true },
        });

        refreshCoordinator.register(cb);
        refreshCoordinator.onVisibilityChange();

        await vi.advanceTimersByTimeAsync(200);

        expect(cb).not.toHaveBeenCalled();
    });
});
