const NOT_TEXT_INPUTS = ['button', 'checkbox', 'radio', 'submit', 'reset', 'range', 'color', 'file'];
const TEXT_ROLES = ['textbox', 'searchbox', 'combobox', 'spinbutton'];

/**
 * Whether a key press here types into something: a field, a select, editable text, or a custom
 * control with a text role. A single-key shortcut must leave those alone.
 */
export function isTextEntryTarget(target: EventTarget | null): boolean {
    if (!(target instanceof HTMLElement)) return false;
    if (target.isContentEditable) return true;
    if (target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) return true;
    if (target instanceof HTMLInputElement) return !NOT_TEXT_INPUTS.includes(target.type);
    return TEXT_ROLES.includes(target.getAttribute('role') ?? '');
}
