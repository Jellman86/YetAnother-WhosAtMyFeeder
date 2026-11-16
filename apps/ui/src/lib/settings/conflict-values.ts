type Translate = (key: string, options?: { default?: string }) => string;

const MAX_LENGTH = 40;

/**
 * A setting's value as the save bar shows it beside a conflict, so the owner can see both values
 * before keeping one. Secrets never reach a draft, so none can be shown here.
 */
export function conflictValueText(value: unknown, translate: Translate): string {
    if (value === true) return translate('settings.save_bar.value_on', { default: 'On' });
    if (value === false) return translate('settings.save_bar.value_off', { default: 'Off' });
    if (value === null || value === undefined || value === '' || (Array.isArray(value) && value.length === 0)) {
        return translate('settings.save_bar.value_not_set', { default: 'Not set' });
    }
    let text: string;
    if (typeof value === 'number' || typeof value === 'string') {
        text = String(value);
    } else if (Array.isArray(value) && value.every((entry) => typeof entry === 'string' || typeof entry === 'number')) {
        text = value.join(', ');
    } else {
        return translate('settings.save_bar.value_other', { default: 'A different value' });
    }
    return text.length > MAX_LENGTH ? `${text.slice(0, MAX_LENGTH - 1)}…` : text;
}
