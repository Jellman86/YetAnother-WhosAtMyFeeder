import { writable } from 'svelte/store';

export type Layout = 'horizontal' | 'vertical';

function createLayoutStore() {
    const stored = (typeof localStorage !== 'undefined'
        ? localStorage.getItem('layout') as Layout | null
        : null) || 'horizontal';

    const { subscribe, set } = writable<Layout>(stored);

    return {
        subscribe,
        set: (value: Layout) => {
            if (typeof localStorage !== 'undefined') {
                localStorage.setItem('layout', value);
            }
            set(value);
        },
        toggle: () => {
            const newLayout: Layout = stored === 'horizontal' ? 'vertical' : 'horizontal';
            if (typeof localStorage !== 'undefined') {
                localStorage.setItem('layout', newLayout);
            }
            set(newLayout);
        },
    };
}

export const layout = createLayoutStore();

// Sidebar collapsed state
function createSidebarStore() {
    const storedCollapsed = typeof localStorage !== 'undefined'
        ? localStorage.getItem('sidebarCollapsed') === 'true'
        : false;

    const { subscribe, set, update } = writable<boolean>(storedCollapsed);

    return {
        subscribe,
        set: (value: boolean) => {
            if (typeof localStorage !== 'undefined') {
                localStorage.setItem('sidebarCollapsed', String(value));
            }
            set(value);
        },
        toggle: () => {
            update(current => {
                const newValue = !current;
                if (typeof localStorage !== 'undefined') {
                    localStorage.setItem('sidebarCollapsed', String(newValue));
                }
                return newValue;
            });
        },
    };
}

export const sidebarCollapsed = createSidebarStore();
