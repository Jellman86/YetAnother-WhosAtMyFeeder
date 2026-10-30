/**
 * The one colour language for a classification score (layout-patterns.md §6).
 *
 * Under 60% is amber, because a score that low is work for a person; under 85% is
 * the brand colour, normal emphasis; from 85% it is green, confirmed. The scales are
 * `attention-*`, `brand-*` and `success-*`. Never the theme `accent-*`: that is a
 * brand colour, emerald in the classic theme and amber in bluetit, so it made the
 * same score a different colour in each view and theme.
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
    low: 'text-attention-800 dark:text-attention-300',
    mid: 'text-brand-700 dark:text-brand-300',
    high: 'text-success-700 dark:text-success-300'
};

/** A score printed over a photograph or another always-dark surface. */
export const SCORE_TEXT_ON_MEDIA: Readonly<Record<ScoreBand, string>> = {
    low: 'text-attention-300',
    mid: 'text-brand-300',
    high: 'text-success-300'
};

/** The dot beside a score and the fill of its bar. */
export const SCORE_FILL: Readonly<Record<ScoreBand, string>> = {
    low: 'bg-attention-500',
    mid: 'bg-brand-500',
    high: 'bg-success-500'
};
