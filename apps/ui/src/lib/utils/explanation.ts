/** A short explanation shared by badges and existing controls. */
export interface ExplanationOptions {
    text: string;
    /** Informational badges pin on tap; existing controls keep their own action. */
    toggle?: boolean;
}

let dismissCurrent: (() => void) | null = null;
let nextId = 0;

export function explanation(node: HTMLElement, initial: string | ExplanationOptions) {
    let options = typeof initial === 'string' ? { text: initial } : initial;
    let tip: HTMLSpanElement | null = null;
    let container: HTMLElement | null = null;
    let pinned = false;
    let closeTimer: ReturnType<typeof setTimeout> | undefined;
    const previousDescription = node.getAttribute('aria-describedby');
    const id = `badge-explanation-${++nextId}`;

    function place() {
        if (!tip) return;
        const box = node.getBoundingClientRect();
        let visible = { left: Math.max(0, box.left), right: Math.min(innerWidth, box.right), top: Math.max(0, box.top), bottom: Math.min(innerHeight, box.bottom) };
        for (let parent = node.parentElement; parent; parent = parent.parentElement) {
            const style = getComputedStyle(parent);
            const bounds = parent.getBoundingClientRect();
            if (/auto|scroll|hidden|clip/.test(style.overflowX)) {
                visible = { ...visible, left: Math.max(visible.left, bounds.left), right: Math.min(visible.right, bounds.right) };
            }
            if (/auto|scroll|hidden|clip/.test(style.overflowY)) {
                visible = { ...visible, top: Math.max(visible.top, bounds.top), bottom: Math.min(visible.bottom, bounds.bottom) };
            }
            // Top-layer panels escape the clipping of their DOM ancestors.
            if (parent.matches(':popover-open, dialog[open]')) break;
        }
        if (!box.width || !box.height || visible.right <= visible.left || visible.bottom <= visible.top) {
            hide();
            return;
        }
        const size = tip.getBoundingClientRect();
        const left = Math.max(8, Math.min(box.left + box.width / 2 - size.width / 2, innerWidth - size.width - 8));
        const below = box.bottom + 8;
        const top = below + size.height <= innerHeight - 8 ? below : Math.max(8, box.top - size.height - 8);
        Object.assign(tip.style, { left: `${left}px`, top: `${top}px` });
    }

    function clearTimer() {
        clearTimeout(closeTimer);
        closeTimer = undefined;
    }

    function hide() {
        clearTimer();
        tip?.remove();
        tip = null;
        pinned = false;
        if (previousDescription === null) node.removeAttribute('aria-describedby');
        else node.setAttribute('aria-describedby', previousDescription);
        if (dismissCurrent === hide) dismissCurrent = null;
        window.removeEventListener('keydown', escape, true);
        document.removeEventListener('pointerdown', outside, true);
        window.removeEventListener('scroll', place, true);
        window.removeEventListener('resize', place);
        container?.removeEventListener('toggle', parentClosed);
        container?.removeEventListener('close', parentClosed);
        container = null;
    }

    function parentClosed(event: Event) {
        if (event.target === container && (event.type === 'close' || (event as Event & { newState?: string }).newState === 'closed')) hide();
    }

    function escape(event: KeyboardEvent) {
        if (event.key !== 'Escape' || !tip) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        hide();
    }

    function outside(event: PointerEvent) {
        if (event.target instanceof Node && !node.contains(event.target) && !tip?.contains(event.target)) hide();
    }

    function show() {
        clearTimer();
        if (!options.text.trim()) return;
        if (tip) return;
        dismissCurrent?.();
        dismissCurrent = hide;
        tip = document.createElement('span');
        tip.id = id;
        tip.setAttribute('role', 'tooltip');
        tip.className = 'rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-normal leading-relaxed text-slate-700 shadow-lg dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200';
        Object.assign(tip.style, { position: 'fixed', margin: '0', inset: 'auto', width: 'max-content', maxWidth: 'min(280px, calc(100vw - 16px))', maxHeight: 'calc(100vh - 16px)', overflow: 'auto', zIndex: '10000', textAlign: 'left', whiteSpace: 'normal' });
        tip.textContent = options.text;
        tip.addEventListener('pointerenter', clearTimer);
        tip.addEventListener('pointerleave', leave);
        // A manual native popover escapes card clipping and remains inside an enclosing
        // capture popover's DOM, so tapping its explanation does not close that panel.
        tip.setAttribute('popover', 'manual');
        container = node.closest<HTMLElement>('[popover], dialog');
        (container ?? document.body).append(tip);
        tip.showPopover?.();
        node.setAttribute('aria-describedby', [previousDescription, id].filter(Boolean).join(' '));
        place();
        if (!tip) return;
        window.addEventListener('keydown', escape, true);
        document.addEventListener('pointerdown', outside, true);
        window.addEventListener('scroll', place, true);
        window.addEventListener('resize', place);
        container?.addEventListener('toggle', parentClosed);
        container?.addEventListener('close', parentClosed);
    }

    function enter(event: PointerEvent) {
        if (event.pointerType !== 'touch') show();
    }

    function leave() {
        clearTimer();
        if (pinned || node.matches(':focus-visible')) return;
        // The pointer can cross the small gap and hover the explanation itself.
        closeTimer = setTimeout(hide, 120);
    }

    function click(event: MouseEvent) {
        if (!options.toggle) return;
        event.preventDefault();
        event.stopPropagation();
        if (pinned) hide();
        else { show(); pinned = true; }
    }

    node.addEventListener('pointerenter', enter);
    node.addEventListener('pointerleave', leave);
    node.addEventListener('focus', show);
    node.addEventListener('blur', hide);
    node.addEventListener('click', click);
    return {
        update(next: string | ExplanationOptions) {
            options = typeof next === 'string' ? { text: next } : next;
            if (tip) {
                if (!options.text.trim()) hide();
                else { tip.textContent = options.text; place(); }
            }
        },
        destroy() {
            hide();
            node.removeEventListener('pointerenter', enter);
            node.removeEventListener('pointerleave', leave);
            node.removeEventListener('focus', show);
            node.removeEventListener('blur', hide);
            node.removeEventListener('click', click);
        }
    };
}
