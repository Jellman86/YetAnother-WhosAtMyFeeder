type Layout = 'vertical';

class LayoutStore {
    currentLayout = $state<Layout>('vertical');
    sidebarCollapsedState = $state<boolean>(false);

    constructor() {
        // Initialize from localStorage
        if (typeof localStorage !== 'undefined') {
            const stored = localStorage.getItem('layout');
            this.currentLayout = 'vertical';
            if (stored && stored !== 'vertical') {
                localStorage.setItem('layout', 'vertical');
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

    setLayout(_value: Layout) {
        // Desktop navigation is sidebar-only; keep any callers pinned to the sole supported layout.
        this.currentLayout = 'vertical';
    }

    toggleLayout() {
        // Horizontal layout has been removed; toggling no longer changes the navigation model.
        this.currentLayout = 'vertical';
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
