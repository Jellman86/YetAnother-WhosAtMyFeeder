import { getContext, setContext } from 'svelte';

const DISCLOSURES = Symbol('settings-disclosures');

/**
 * Which of Settings' closable sections are open, held by the Settings page for the visit. It
 * outlives a tab being left and reopened, and lets the page open the sections that hold a refused
 * field. A section nobody has opened or closed yet is undefined and follows its own default.
 */
export class SettingsDisclosures {
    private open = $state<Record<string, boolean>>({});

    isOpen(id: string): boolean | undefined {
        return this.open[id];
    }

    setOpen(id: string, open: boolean): void {
        this.open[id] = open;
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
