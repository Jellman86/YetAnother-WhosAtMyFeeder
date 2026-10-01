const activeTraps: { element: HTMLElement }[] = [];

/**
 * Utility to trap focus inside an element (e.g., a modal)
 * for better keyboard accessibility.
 */
export function trapFocus(element: HTMLElement): () => void {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const trap = { element };
    activeTraps.push(trap);
    let released = false;
    function getFocusableElements() {
        return Array.from(element.querySelectorAll<HTMLElement>(
            'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])'
        )).filter((candidate) =>
            candidate.getAttribute('aria-hidden') !== 'true'
            && !candidate.matches(':disabled')
            && !candidate.closest('[inert], [aria-hidden="true"]')
            && getComputedStyle(candidate).visibility !== 'hidden'
            && candidate.getClientRects().length > 0
        );
    }

    // Initial focus
    const initialFocusTimer = setTimeout(() => {
        if (released || !element.isConnected || activeTraps.at(-1) !== trap) return;
        if (element.contains(document.activeElement)) return;
        const focusable = getFocusableElements();
        const initialFocus = focusable.find(candidate => candidate.hasAttribute('autofocus')) ?? focusable[0] ?? element;
        initialFocus.focus();
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
    return () => {
        if (released) return;
        released = true;
        clearTimeout(initialFocusTimer);
        element.removeEventListener('keydown', handleTab);
        const wasActive = activeTraps.at(-1) === trap;
        activeTraps.splice(activeTraps.indexOf(trap), 1);
        if (!wasActive) return;

        const focused = document.activeElement;
        // A closed record must not override focus deliberately moved to another
        // control or dialog while it was open.
        if (focused instanceof HTMLElement && focused !== document.body && focused.isConnected && !element.contains(focused)) return;

        if (opener?.isConnected && opener !== document.body && !opener.matches(':disabled')
            && !opener.closest('[inert]') && opener.getClientRects().length > 0
            && getComputedStyle(opener).visibility !== 'hidden') {
            opener.focus();
            return;
        }
        const fallback = activeTraps.at(-1)?.element ?? document.querySelector<HTMLElement>('main');
        if (!fallback?.isConnected) return;
        const originalTabIndex = fallback.getAttribute('tabindex');
        if (originalTabIndex === null) fallback.setAttribute('tabindex', '-1');
        fallback.focus();
        if (originalTabIndex === null) fallback.removeAttribute('tabindex');
    };
}
