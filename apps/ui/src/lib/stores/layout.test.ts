import { beforeEach, describe, expect, it, vi } from 'vitest';

describe('layoutStore', () => {
    beforeEach(() => {
        vi.resetModules();
        const backing = new Map<string, string>();
        Object.defineProperty(globalThis, 'localStorage', {
            configurable: true,
            value: {
                getItem: (key: string) => backing.get(key) ?? null,
                setItem: (key: string, value: string) => {
                    backing.set(key, String(value));
                },
                removeItem: (key: string) => {
                    backing.delete(key);
                },
                clear: () => {
                    backing.clear();
                },
            },
        });
    });

    it('migrates legacy horizontal layout preferences to vertical', async () => {
        localStorage.setItem('layout', 'horizontal');

        const { layoutStore } = await import('./layout.svelte');

        expect(layoutStore.layout).toBe('vertical');
    });

    it('ignores attempts to switch away from the vertical layout', async () => {
        const { layoutStore } = await import('./layout.svelte');

        layoutStore.setLayout('horizontal' as never);
        expect(layoutStore.layout).toBe('vertical');

        layoutStore.toggleLayout();
        expect(layoutStore.layout).toBe('vertical');
    });
});
