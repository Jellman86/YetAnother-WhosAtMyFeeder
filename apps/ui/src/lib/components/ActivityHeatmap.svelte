<script lang="ts">
    import { _ } from 'svelte-i18n';
    import {
        dayTotals,
        heatmapFill,
        heatmapLegendGradient,
        hourlyTotals,
        moveGridPosition,
        peakCell,
        type GridPosition,
        type HeatmapCell
    } from '../leaderboard/heatmap';

    interface Props {
        cells: HeatmapCell[];
        maxCellCount: number;
        dark: boolean;
        dayLabel: (dayOfWeek: number) => string;
        /** The species the grid is limited to, named in the reading; null for every species. */
        subject?: string | null;
    }

    let { cells, maxCellCount, dark, dayLabel, subject = null }: Props = $props();
    const uid = $props.id();

    function cellId(row: number, hour: number): string {
        return `${uid}-r${row}-h${hour}`;
    }

    const DAY_ORDER = [1, 2, 3, 4, 5, 6, 0];
    const HOURS = Array.from({ length: 24 }, (_, hour) => hour);

    let counts = $derived(new Map(cells.map((cell) => [`${cell.day_of_week}-${cell.hour}`, Math.max(0, cell.count)] as const)));
    let hourTotals = $derived(hourlyTotals(cells));
    let weekdayTotals = $derived(dayTotals(cells));
    let busiestHourTotal = $derived(Math.max(1, ...hourTotals));
    let peak = $derived(peakCell(cells));

    let root = $state<HTMLDivElement | null>(null);
    let active = $state<GridPosition | null>(null);
    let readingByKeyboard = $state(false);
    let tooltipAt = $state<{ left: number; top: number; below: boolean } | null>(null);

    function countAt(position: GridPosition): number {
        return counts.get(`${DAY_ORDER[position.row]}-${position.hour}`) ?? 0;
    }

    function hourLabel(hour: number): string {
        return `${String(hour).padStart(2, '0')}:00`;
    }

    function isPeak(position: GridPosition): boolean {
        return Boolean(peak && peak.day_of_week === DAY_ORDER[position.row] && peak.hour === position.hour);
    }

    function slotLabel(position: GridPosition): string {
        return $_('leaderboard.heatmap_slot', {
            values: {
                day: dayLabel(DAY_ORDER[position.row]),
                start: hourLabel(position.hour),
                end: hourLabel((position.hour + 1) % 24)
            },
            default: '{day} {start} to {end}'
        });
    }

    function countLabel(count: number): string {
        if (subject) {
            return count === 1
                ? $_('leaderboard.heatmap_subject_one', { values: { subject }, default: '1 {subject} detection' })
                : $_('leaderboard.heatmap_subject_many', { values: { count: count.toLocaleString(), subject }, default: '{count} {subject} detections' });
        }
        return count === 1
            ? $_('leaderboard.heatmap_count_one', { default: '1 detection' })
            : $_('leaderboard.heatmap_count_many', { values: { count: count.toLocaleString() }, default: '{count} detections' });
    }

    // What a screen reader hears on each cell: the same sentence the tooltip shows.
    function reading(position: GridPosition): string {
        return `${slotLabel(position)}: ${countLabel(countAt(position))}${isPeak(position) ? `. ${$_('leaderboard.heatmap_busiest_slot', { default: 'Busiest slot' })}` : ''}`;
    }

    function place(position: GridPosition) {
        const cell = root?.querySelector<HTMLElement>(`[data-heatmap-row="${position.row}"][data-heatmap-hour="${position.hour}"]`);
        if (!root || !cell) return;
        const frame = root.getBoundingClientRect();
        const box = cell.getBoundingClientRect();
        const centre = box.left - frame.left + box.width / 2;
        // Near the top edge the tooltip would cover the hour bars and labels it is read against.
        const below = box.top - frame.top < 88;
        tooltipAt = {
            left: Math.min(Math.max(centre, 88), frame.width - 88),
            top: below ? box.bottom - frame.top + 8 : box.top - frame.top - 8,
            below
        };
    }

    function show(position: GridPosition) {
        active = position;
        place(position);
    }

    function hide() {
        active = null;
        tooltipAt = null;
        readingByKeyboard = false;
    }

    function positionFrom(target: EventTarget | null): GridPosition | null {
        const cell = (target as Element | null)?.closest<HTMLElement>('[data-heatmap-hour]');
        if (!cell) return null;
        return { row: Number(cell.dataset.heatmapRow), hour: Number(cell.dataset.heatmapHour) };
    }

    // A hovering pointer reads as it moves; a touch has no hover, so a tap reads a slot and a
    // second tap on it, or a tap elsewhere, puts it away.
    function onPointerMove(event: PointerEvent) {
        if (event.pointerType === 'touch') return;
        const position = positionFrom(event.target);
        if (position) {
            readingByKeyboard = false;
            show(position);
        }
    }

    function onPointerLeave(event: PointerEvent) {
        if (event.pointerType !== 'touch' && !readingByKeyboard) hide();
    }

    function onPointerUp(event: PointerEvent) {
        if (event.pointerType !== 'touch') return;
        const position = positionFrom(event.target);
        if (!position || (active && active.row === position.row && active.hour === position.hour)) hide();
        else show(position);
    }

    function onWindowPointerDown(event: PointerEvent) {
        if (active && root && !root.contains(event.target as Node)) hide();
    }

    function onFocus(event: FocusEvent) {
        if (!(event.currentTarget instanceof HTMLElement) || !event.currentTarget.matches(':focus-visible')) return;
        readingByKeyboard = true;
        const startRow = peak ? DAY_ORDER.indexOf(peak.day_of_week) : 0;
        show(active ?? { row: Math.max(0, startRow), hour: peak?.hour ?? 0 });
    }

    function onKeyDown(event: KeyboardEvent) {
        if (event.key === 'Escape') {
            if (active) {
                event.preventDefault();
                hide();
            }
            return;
        }
        const next = moveGridPosition(active ?? { row: 0, hour: 0 }, event.key, DAY_ORDER.length);
        if (!next) return;
        event.preventDefault();
        readingByKeyboard = true;
        show(next);
    }
</script>

<svelte:window onpointerdown={onWindowPointerDown} onresize={() => active && place(active)} />

<div class="relative" bind:this={root} data-activity-heatmap>
    <div
        class="grid gap-1 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-offset-slate-950"
        style="grid-template-columns: 2.25rem repeat(24, minmax(0, 1fr)) 2.5rem; grid-template-rows: 2.5rem 1.25rem repeat(7, 1.5rem);"
        role="grid"
        tabindex="0"
        aria-label={`${$_('leaderboard.heatmap_grid_label', { default: 'Activity by weekday and hour. Use the arrow keys to read a slot.' })}${subject ? ` ${subject}.` : ''}`}
        aria-activedescendant={active ? cellId(active.row, active.hour) : undefined}
        onpointermove={onPointerMove}
        onpointerleave={onPointerLeave}
        onpointerup={onPointerUp}
        onfocus={onFocus}
        onblur={hide}
        onkeydown={onKeyDown}
        data-leaderboard-heatmap-grid
    >
        <span aria-hidden="true"></span>
        {#each HOURS as hour}
            <span class="flex items-end" aria-hidden="true">
                <span
                    class="block w-full rounded-t-sm {active?.hour === hour ? 'bg-brand-500' : 'bg-slate-300 dark:bg-slate-600'}"
                    style="height: {Math.round((hourTotals[hour] / busiestHourTotal) * 100)}%"
                    data-heatmap-hour-bar={hour}
                ></span>
            </span>
        {/each}
        <span aria-hidden="true"></span>

        <span aria-hidden="true"></span>
        {#each HOURS as hour}
            <span
                class="self-end whitespace-nowrap text-center text-xs tabular-nums {active?.hour === hour ? 'font-semibold text-slate-900 dark:text-white' : 'text-slate-500 dark:text-slate-400'} {hour % 6 === 0 || active?.hour === hour ? '' : hour % 3 === 0 ? 'invisible sm:visible' : 'invisible'}"
                aria-hidden="true"
            >{String(hour).padStart(2, '0')}</span>
        {/each}
        <span class="self-end text-right text-xs text-slate-500 dark:text-slate-400" aria-hidden="true">{$_('leaderboard.heatmap_total_short', { default: 'Total' })}</span>

        {#each DAY_ORDER as dayOfWeek, row}
            <div class="contents" role="row" aria-label={dayLabel(dayOfWeek)}>
            <span
                class="self-center text-xs {active?.row === row ? 'font-bold text-slate-900 dark:text-white' : 'font-semibold text-slate-500 dark:text-slate-400'}"
                aria-hidden="true"
            >{dayLabel(dayOfWeek)}</span>
            {#each HOURS as hour}
                {@const count = counts.get(`${dayOfWeek}-${hour}`) ?? 0}
                {@const current = active?.row === row && active?.hour === hour}
                <span
                    class="rounded-sm {current ? 'ring-2 ring-brand-500 ring-offset-1 ring-offset-white dark:ring-brand-300 dark:ring-offset-slate-950' : isPeak({ row, hour }) ? 'ring-2 ring-slate-900 ring-offset-1 ring-offset-white dark:ring-white dark:ring-offset-slate-950' : ''}"
                    style="background-color: {heatmapFill(count, maxCellCount, dark)}"
                    id={cellId(row, hour)}
                    role="gridcell"
                    aria-label={reading({ row, hour })}
                    data-heatmap-row={row}
                    data-heatmap-hour={hour}
                ></span>
            {/each}
            <span class="self-center text-right text-xs tabular-nums text-slate-500 dark:text-slate-400" aria-hidden="true">{weekdayTotals[dayOfWeek].toLocaleString()}</span>
            </div>
        {/each}
    </div>

    {#if active && tooltipAt}
        <div
            class="pointer-events-none absolute z-20 w-44 -translate-x-1/2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-lg dark:border-slate-700 dark:bg-slate-900 {tooltipAt.below ? '' : '-translate-y-full'}"
            style="left: {tooltipAt.left}px; top: {tooltipAt.top}px"
            aria-hidden="true"
            data-heatmap-tooltip
        >
            <p class="font-semibold text-slate-900 dark:text-white">{slotLabel(active)}</p>
            <p class="mt-0.5 tabular-nums text-slate-600 dark:text-slate-300">{countLabel(countAt(active))}</p>
            {#if isPeak(active)}
                <p class="mt-0.5 font-semibold text-slate-900 dark:text-white">{$_('leaderboard.heatmap_busiest_slot', { default: 'Busiest slot' })}</p>
            {/if}
        </div>
    {/if}

    <div class="mt-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 text-xs text-slate-500 dark:text-slate-400">
        <span class="inline-flex items-center gap-2 tabular-nums">
            0
            <span class="inline-block h-2 w-24 rounded-full" style="background-image: {heatmapLegendGradient(dark)}"></span>
            {maxCellCount.toLocaleString()}
            <span>{$_('leaderboard.heatmap_per_hour', { default: 'detections in one hour slot' })}</span>
        </span>
        {#if peak}
            <span class="inline-flex items-center gap-1.5">
                <span class="inline-block h-2.5 w-2.5 rounded-sm ring-2 ring-slate-900 dark:ring-white" aria-hidden="true"></span>
                {$_('leaderboard.heatmap_peak', { values: { day: dayLabel(peak.day_of_week), time: hourLabel(peak.hour), count: peak.count.toLocaleString() }, default: 'Busiest: {day} {time}, {count}' })}
            </span>
        {/if}
    </div>

</div>
