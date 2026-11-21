type ShortcutHandler = () => void;
type ShortcutMap = Map<string, ShortcutHandler>;

let sequenceBuffer = '';
let sequenceTimeout: number | null = null;
const SEQUENCE_TIMEOUT_MS = 1000;

export function initKeyboardShortcuts(handlers: Record<string, ShortcutHandler>) {
    const shortcuts: ShortcutMap = new Map(Object.entries(handlers));

    function handleKeydown(e: KeyboardEvent) {
        // Ignore if typing in input/textarea/contenteditable
        const target = e.target as HTMLElement;
        if (target.matches('input, textarea, select, [contenteditable="true"]')) {
            return;
        }

        const key = e.key;

        // "?" is matched as the key the keyboard reports, below. "/" with Shift is not "?": German,
        // Spanish, Italian, Portuguese and French keyboards type "/" that way, and a page's search takes it.

        // Handle Escape key
        if (key === 'Escape') {
            // Leave native popover dismissal and focus return to the browser.
            if (document.querySelector('[popover]:popover-open')) return;
            e.preventDefault();
            shortcuts.get('Escape')?.();
            return;
        }

        // Single key shortcuts (like 'r' for refresh)
        if (shortcuts.has(key)) {
            e.preventDefault();
            shortcuts.get(key)?.();
            return;
        }

        // Sequence shortcuts (e.g., "g d" for go to dashboard)
        if (sequenceTimeout) {
            clearTimeout(sequenceTimeout);
        }

        sequenceBuffer += key;

        if (shortcuts.has(sequenceBuffer)) {
            e.preventDefault();
            shortcuts.get(sequenceBuffer)?.();
            sequenceBuffer = '';
        } else {
            // Clear buffer after timeout
            sequenceTimeout = window.setTimeout(() => {
                sequenceBuffer = '';
            }, SEQUENCE_TIMEOUT_MS);
        }
    }

    window.addEventListener('keydown', handleKeydown);

    // Return cleanup function
    return () => {
        window.removeEventListener('keydown', handleKeydown);
        if (sequenceTimeout) {
            clearTimeout(sequenceTimeout);
        }
    };
}
