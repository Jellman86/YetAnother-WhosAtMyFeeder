/**
 * The five status tones of the design system (app.css, "Status tones"). Each class list is
 * written out whole so Tailwind finds it in the source.
 *
 *   ok         confirmed, passed, healthy, connected
 *   attention  this needs a person (amber, and for nothing else)
 *   fail       failed or broken
 *   info       running, in flight, normal emphasis
 *   neutral    off by choice, idle, not measured, unknown
 */
export type Tone = 'ok' | 'attention' | 'fail' | 'info' | 'neutral';

/** The tone's ink: its words, its icon, a dot. */
export const TONE_INK: Readonly<Record<Tone, string>> = {
    ok: 'text-status-ok',
    attention: 'text-status-attention',
    fail: 'text-status-fail',
    info: 'text-status-info',
    neutral: 'text-status-neutral'
};

/** A chip: the tone's soft ground, its 3:1 edge and its ink. */
export const TONE_CHIP: Readonly<Record<Tone, string>> = {
    ok: 'border-status-ok-line bg-status-ok-soft text-status-ok',
    attention: 'border-status-attention-line bg-status-attention-soft text-status-attention',
    fail: 'border-status-fail-line bg-status-fail-soft text-status-fail',
    info: 'border-status-info-line bg-status-info-soft text-status-info',
    neutral: 'border-status-neutral-line bg-status-neutral-soft text-status-neutral'
};

/** A small mark (a dot or a bar) in the tone's 3:1 edge colour, beside words that carry the meaning. */
export const TONE_MARK: Readonly<Record<Tone, string>> = {
    ok: 'bg-status-ok-line',
    attention: 'bg-status-attention-line',
    fail: 'bg-status-fail-line',
    info: 'bg-status-info-line',
    neutral: 'bg-status-neutral-line'
};
