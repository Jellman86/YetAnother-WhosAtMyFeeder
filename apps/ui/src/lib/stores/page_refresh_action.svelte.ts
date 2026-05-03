type PageRefreshCallback = () => Promise<void> | void;

type RegisteredAction = {
    id: symbol;
    callback: PageRefreshCallback;
};

class PageRefreshAction {
    private actions = $state<RegisteredAction[]>([]);
    refreshing = $state(false);

    get available() {
        return this.actions.length > 0;
    }

    register(callback: PageRefreshCallback): () => void {
        const action = { id: Symbol('page-refresh-action'), callback };
        this.actions = [...this.actions, action];
        return () => {
            this.actions = this.actions.filter((candidate) => candidate.id !== action.id);
        };
    }

    async run(): Promise<void> {
        const action = this.actions.at(-1);
        if (!action || this.refreshing) return;

        this.refreshing = true;
        try {
            await action.callback();
        } finally {
            this.refreshing = false;
        }
    }
}

export const pageRefreshAction = new PageRefreshAction();
