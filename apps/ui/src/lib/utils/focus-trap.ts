/**
 * Utility to trap focus inside an element (e.g., a modal)
 * for better keyboard accessibility.
 */
export function trapFocus(element: HTMLElement): () => void {
    function getFocusableElements() {
        return Array.from(element.querySelectorAll<HTMLElement>(
            'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])'
        )).filter((candidate) =>
            candidate.getAttribute('aria-hidden') !== 'true'
            && candidate.getClientRects().length > 0
        );
    }

    // Initial focus
    setTimeout(() => {
        const [firstElement] = getFocusableElements();
        const initialFocus = element.querySelector('[autofocus]') as HTMLElement || firstElement;
        initialFocus?.focus();
    }, 50);

    function handleTab(e: KeyboardEvent) {
        if (e.key !== 'Tab') return;

        // Dialog content can arrive after the shell mounts, so resolve this list on
        // every keypress rather than trapping focus against a stale loading state.
        const focusableElements = getFocusableElements();
        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];
        if (!firstElement || !lastElement) return;

        if (e.shiftKey) {
            if (document.activeElement === firstElement) {
                lastElement?.focus();
                e.preventDefault();
            }
        } else {
            if (document.activeElement === lastElement) {
                firstElement?.focus();
                e.preventDefault();
            }
        }
    }

    element.addEventListener('keydown', handleTab);
    return () => element.removeEventListener('keydown', handleTab);
}
