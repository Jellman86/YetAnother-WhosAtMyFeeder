/**
 * Utility to trap focus inside an element (e.g., a modal)
 * for better keyboard accessibility.
 */
export function trapFocus(element: HTMLElement): () => void {
    const focusableElements = element.querySelectorAll(
        'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])'
    );
    const firstElement = focusableElements[0] as HTMLElement;
    const lastElement = focusableElements[focusableElements.length - 1] as HTMLElement;

    // Initial focus
    setTimeout(() => {
        const initialFocus = element.querySelector('[autofocus]') as HTMLElement || firstElement;
        initialFocus?.focus();
    }, 50);

    function handleTab(e: KeyboardEvent) {
        if (e.key !== 'Tab') return;

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
