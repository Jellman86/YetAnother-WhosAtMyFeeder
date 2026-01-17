export type Layout = 'horizontal' | 'vertical';

class LayoutStore {
    currentLayout = $state<Layout>('vertical');
    sidebarCollapsedState = $state<boolean>(false);

    constructor() {
        // Initialize from localStorage
        if (typeof localStorage !== 'undefined') {
            const stored = localStorage.getItem('layout') as Layout | null;
            if (stored) {
                this.currentLayout = stored;
            }

            const storedCollapsed = localStorage.getItem('sidebarCollapsed') === 'true';
            this.sidebarCollapsedState = storedCollapsed;
        }

        // Use $effect.root() to create effect context outside components
        $effect.root(() => {
            // Sync to localStorage on changes
            if (typeof localStorage !== 'undefined') {
                $effect(() => {
                    localStorage.setItem('layout', this.currentLayout);
                });

                $effect(() => {
                    localStorage.setItem('sidebarCollapsed', String(this.sidebarCollapsedState));
                });
            }
        });
    }

    get layout(): Layout {
        return this.currentLayout;
    }

    get sidebarCollapsed(): boolean {
        return this.sidebarCollapsedState;
    }

    setLayout(value: Layout) {
        this.currentLayout = value;
    }

    toggleLayout() {
        this.currentLayout = this.currentLayout === 'horizontal' ? 'vertical' : 'horizontal';
    }

    setSidebarCollapsed(value: boolean) {
        this.sidebarCollapsedState = value;
    }

    toggleSidebar() {
        this.sidebarCollapsedState = !this.sidebarCollapsedState;
    }
}

// Singleton instance
export const layoutStore = new LayoutStore();

// For backward compatibility with existing code
export const layout = {
    subscribe: (fn: (value: Layout) => void) => {
        return $effect.root(() => {
            $effect(() => {
                fn(layoutStore.layout);
            });
            return () => {};
        });
    },
    set: (value: Layout) => layoutStore.setLayout(value),
    toggle: () => layoutStore.toggleLayout()
};

export const sidebarCollapsed = {
    subscribe: (fn: (value: boolean) => void) => {
        return $effect.root(() => {
            $effect(() => {
                fn(layoutStore.sidebarCollapsed);
            });
            return () => {};
        });
    },
    set: (value: boolean) => layoutStore.setSidebarCollapsed(value),
    toggle: () => layoutStore.toggleSidebar()
};
