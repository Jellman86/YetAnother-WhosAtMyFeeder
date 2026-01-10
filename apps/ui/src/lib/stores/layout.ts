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
