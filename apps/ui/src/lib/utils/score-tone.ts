/**
 * The one colour language for a classification score (layout-patterns.md §6).
 *
 * Under 60% is amber, because a score that low is work for a person; under 85% is
 * the brand colour, normal emphasis; from 85% it is green, confirmed. On a page they are
 * the status tones attention, info and ok (app.css), resolved for every mode; a fill is the
 * tone's 3:1 edge colour. Over a photograph the fixed light steps are used instead.
 */
export type ScoreBand = 'low' | 'mid' | 'high';

/**
 * Bands the whole percentage a person reads, so the figure and its colour never
 * disagree: 0.596 prints as 60% and so takes the 60% colour.
 */
export function scoreBand(score: number | null | undefined): ScoreBand {
    const percent = typeof score === 'number' && Number.isFinite(score) ? Math.round(score * 100) : 0;
    if (percent < 60) return 'low';
    if (percent < 85) return 'mid';
    return 'high';
}

/** A score printed on a light or dark page surface. */
export const SCORE_TEXT: Readonly<Record<ScoreBand, string>> = {
    low: 'text-status-attention',
    mid: 'text-status-info',
    high: 'text-status-ok'
};

/** A score printed over a photograph or another always-dark surface. */
export const SCORE_TEXT_ON_MEDIA: Readonly<Record<ScoreBand, string>> = {
    low: 'text-attention-300',
    mid: 'text-brand-300',
    high: 'text-success-300'
};

/** The dot beside a score and the fill of its bar. */
export const SCORE_FILL: Readonly<Record<ScoreBand, string>> = {
    low: 'bg-status-attention-line',
    mid: 'bg-status-info-line',
    high: 'bg-status-ok-line'
};
