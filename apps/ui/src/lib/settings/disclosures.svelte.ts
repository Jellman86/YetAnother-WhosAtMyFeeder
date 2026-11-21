import { getContext, setContext } from 'svelte';

const DISCLOSURES = Symbol('settings-disclosures');

/**
 * Which of Settings' closable sections are open, held by the Settings page for the visit. It
 * outlives a tab being left and reopened, and lets the page open the sections that hold a refused
 * field. A section nobody has opened or closed yet is undefined and follows its own default.
 */
export class SettingsDisclosures {
    private open = $state<Record<string, boolean>>({});
    // Per section: the problem it is showing (null when none), and the last one the owner closed.
    private attention: Record<string, { current: string | null; dismissed: string | null }> = {};

    isOpen(id: string): boolean | undefined {
        return this.open[id];
    }

    setOpen(id: string, open: boolean): void {
        this.open[id] = open;
        const attention = this.attention[id];
        // Closing a section that shows a problem dismisses that problem, and only that one.
        if (!open && attention?.current) attention.dismissed = attention.current;
    }

    /**
     * Tells these sections which problem the owner must act on is inside them now (null for none),
     * on every read of it. A problem they have not shown opens them, unless the owner closed them
     * on that same problem; they stay open after it clears, so a report being read never jumps shut.
     */
    attend(ids: readonly string[], problem: string | null): void {
        for (const id of ids) {
            const attention = (this.attention[id] ??= { current: null, dismissed: null });
            if (problem !== null && problem !== attention.current && problem !== attention.dismissed) {
                this.open[id] = true;
            }
            attention.current = problem;
        }
    }

    /** Opens every section given, outermost first. */
    reveal(ids: readonly string[]): void {
        for (const id of ids) this.open[id] = true;
    }
}

export function provideSettingsDisclosures(disclosures: SettingsDisclosures): void {
    setContext(DISCLOSURES, disclosures);
}

function settingsDisclosures(): SettingsDisclosures | undefined {
    return getContext<SettingsDisclosures | undefined>(DISCLOSURES);
}

/**
 * One closable section's open state, the one implementation every Settings disclosure uses. With
 * an id inside the Settings page, the page holds it; otherwise the section holds its own.
 */
export class Disclosure {
    private own = $state<boolean | undefined>(undefined);

    constructor(
        private readonly shared: SettingsDisclosures | undefined,
        private readonly props: () => { id?: string; openByDefault?: boolean }
    ) {}

    get open(): boolean {
        const { id, openByDefault = false } = this.props();
        const remembered = id && this.shared ? this.shared.isOpen(id) : this.own;
        return remembered ?? openByDefault;
    }

    set open(next: boolean) {
        const { id } = this.props();
        if (id && this.shared) this.shared.setOpen(id, next);
        else this.own = next;
    }

    toggle(): void {
        this.open = !this.open;
    }
}

/** Call while a component initialises; `props` is read reactively. */
export function useDisclosure(props: () => { id?: string; openByDefault?: boolean }): Disclosure {
    return new Disclosure(settingsDisclosures(), props);
}
