import { getContext, setContext } from 'svelte';

const SUBHEADING_LEVEL = Symbol('settings-subheading-level');

type SubheadingLevel = 3 | 4 | 5 | 6;

/** Called by whatever owns a group's heading, so a subheading inside it lands one level below. */
export function provideSubheadingLevel(level: () => SubheadingLevel): void {
    setContext(SUBHEADING_LEVEL, level);
}

/** The level a subheading takes here: 4 under a group, deeper under More options. */
export function subheadingLevel(): SubheadingLevel {
    return getContext<(() => SubheadingLevel) | undefined>(SUBHEADING_LEVEL)?.() ?? 4;
}
