/**
 * Accessibility chosen on this device. The owner's saved choices are the default for everyone who
 * opens the install, guests included; a choice made here changes this device at once and outlasts
 * signing out, until it is set back to the default.
 *
 * index.html's boot script reads the same entry before the first paint, so a device that chose high
 * contrast never shows the light page first; `accessibility-device.test.ts` holds the two together.
 */
const ACCESSIBILITY_CHOICES = ['highContrast', 'dyslexiaFont', 'reducedMotion', 'liveAnnouncements'] as const;
export type AccessibilityChoice = (typeof ACCESSIBILITY_CHOICES)[number];
export type DeviceChoices = Partial<Record<AccessibilityChoice, boolean>>;

const STORAGE_KEY = 'accessibility_device';

/** The choices stored on this device; anything unreadable is no choice, never a guess. */
export function parseDeviceChoices(raw: string | null): DeviceChoices {
    if (!raw) return {};
    try {
        const parsed: unknown = JSON.parse(raw);
        if (!parsed || typeof parsed !== 'object') return {};
        const choices: DeviceChoices = {};
        for (const key of ACCESSIBILITY_CHOICES) {
            const value = (parsed as Record<string, unknown>)[key];
            if (typeof value === 'boolean') choices[key] = value;
        }
        return choices;
    } catch {
        return {};
    }
}

/**
 * What applies: this device's own choice, else a preview of the default being edited, else the
 * saved default. Editing a default never hides a choice this device made for itself.
 */
export function effectiveChoice(device: boolean | undefined, preview: boolean | null, defaultValue: boolean): boolean {
    return device ?? preview ?? defaultValue;
}

/** Browser storage, or null where there is none or the browser refuses it: blocked site data throws on access. */
function storage(): Storage | null {
    try {
        return typeof globalThis.localStorage === 'undefined' ? null : globalThis.localStorage;
    } catch {
        return null;
    }
}

function readStored(): DeviceChoices {
    try {
        return parseDeviceChoices(storage()?.getItem(STORAGE_KEY) ?? null);
    } catch {
        return {};
    }
}

class AccessibilityDevice {
    choices = $state<DeviceChoices>(readStored());

    constructor() {
        // Another tab of this browser may change the choice; this one follows it.
        if (typeof window !== 'undefined') {
            window.addEventListener('storage', (event) => {
                if (event.key === STORAGE_KEY || event.key === null) this.choices = readStored();
            });
        }
    }

    /** This device's own choice, or undefined while it follows the default. */
    get(key: AccessibilityChoice): boolean | undefined {
        return this.choices[key];
    }

    /** Sets this device's choice; null goes back to following the default. */
    set(key: AccessibilityChoice, value: boolean | null): void {
        const next = { ...this.choices };
        if (value === null) delete next[key];
        else next[key] = value;
        this.choices = next;
        try {
            const store = storage();
            if (!store) return;
            if (Object.keys(next).length === 0) store.removeItem(STORAGE_KEY);
            else store.setItem(STORAGE_KEY, JSON.stringify(next));
        } catch {
            // Storage refused (a private window): the choice holds for this visit only.
        }
    }
}

export const accessibilityDevice = new AccessibilityDevice();
