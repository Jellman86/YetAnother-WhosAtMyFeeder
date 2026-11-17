<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { components } from '../api/generated/openapi';
    import { dailyTotalsNote } from '../leaderboard/daily-totals';
    import { formatCalendarDay } from '../utils/datetime';

    /**
     * Says, under a chart, which of its days are counted from sealed daily totals because cleanup has
     * removed their captures (#949). It names the first day read from stored captures, and says so
     * when some totals were counted after older captures had already gone. Nothing when the chart
     * counted stored captures only.
     */
    type Props = {
        coverage: components['schemas']['DailyTotalsCoverage'] | null | undefined;
        /** A further sentence for this chart, such as what cannot come from a daily total. */
        extra?: string;
    };

    let { coverage, extra }: Props = $props();

    const note = $derived(dailyTotalsNote(coverage));
    const sentences = $derived.by((): string[] => {
        if (!note) return [];
        const lines = [
            $_('common.daily_totals_note', {
                values: { date: formatCalendarDay(note.firstStoredDay) },
                default: 'Counts before {date} come from daily totals; photos and clips from those days are no longer stored.'
            })
        ];
        if (note.partialBefore === note.firstStoredDay) {
            lines.push($_('common.daily_totals_partial_all', {
                default: 'Those totals were counted after some older captures had already been removed, so they can be lower than what visited.'
            }));
        } else if (note.partialBefore) {
            lines.push($_('common.daily_totals_partial', {
                values: { date: formatCalendarDay(note.partialBefore) },
                default: 'Totals before {date} were counted after some older captures had already been removed, so they can be lower than what visited.'
            }));
        }
        if (extra) lines.push(extra);
        return lines;
    });
</script>

{#if note}
    <p class="mt-3 max-w-prose text-xs leading-snug text-muted" data-daily-totals-note>{sentences.join(' ')}</p>
{/if}
