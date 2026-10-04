<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { withAuthParams } from '../api/core';
    import type { ShowcaseRow } from '../leaderboard/showcase';

    /**
     * Species the rankings flag as probably misidentified: only the camera backs them and nobody has
     * reported them nearby. They are counted in the wall's share bar but never shown on the wall,
     * and are named here so they can be checked, each opening its record.
     */
    interface Props {
        /** Only the flagged rows. */
        checks: ShowcaseRow[];
        countLabel: (count: number) => string;
        nearbyRadiusKm?: number | null;
        onopen: (key: string) => void;
    }

    let { checks, countLabel, nearbyRadiusKm = null, onopen }: Props = $props();

    // A photograph that fails to load falls back to the next honest source, never to a hole.
    let failed = $state<Set<string>>(new Set());
    function markFailed(url: string): void {
        failed = new Set([...failed, url]);
    }
    type Picture = { url: string; raw: string } | null;
    function pictureFor(row: ShowcaseRow): Picture {
        if (row.photo && !failed.has(row.photo)) return { url: withAuthParams(row.photo), raw: row.photo };
        if (row.reference && !failed.has(row.reference)) return { url: row.reference, raw: row.reference };
        return null;
    }
</script>

{#if checks.length > 0}
    <div class="flex flex-wrap items-center gap-3 border-t border-slate-200 pt-4 dark:border-slate-700" data-spotlight-checks>
        <div class="flex w-full flex-col gap-1 sm:w-52">
            <span class="inline-flex items-center gap-1.5 self-start rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-900 dark:bg-amber-950/70 dark:text-amber-300">
                <span class="h-1.5 w-1.5 rounded-full bg-amber-500" aria-hidden="true"></span>{$_('leaderboard.spotlight_needs_check', { default: 'Needs a check' })}
            </span>
            {#if nearbyRadiusKm}
                <span class="text-xs text-slate-500 dark:text-slate-400">{$_('leaderboard.unlikely_reason', { values: { radius: nearbyRadiusKm }, default: 'Not reported within {radius} km' })}</span>
            {/if}
        </div>
        {#each checks as row (row.key)}
            {@const thumb = pictureFor(row)}
            <button
                type="button"
                class="flex min-h-11 items-center gap-3 rounded-xl border border-slate-200 bg-white py-1.5 pl-1.5 pr-3 text-left transition-colors hover:border-amber-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-amber-600"
                aria-label={`${$_('leaderboard.spotlight_review', { default: 'Review' })} ${row.displayName}`}
                onclick={() => onopen(row.key)}
            >
                {#if thumb}
                    <img src={thumb.url} alt="" loading="lazy" decoding="async" class="h-9 w-9 rounded-lg object-cover" onerror={() => markFailed(thumb.raw)} />
                {:else}
                    <span class="h-9 w-9 rounded-lg bg-slate-200 dark:bg-slate-800" aria-hidden="true"></span>
                {/if}
                <span class="flex flex-col">
                    <span class="text-sm font-semibold text-slate-900 dark:text-white">{row.displayName}</span>
                    <span class="text-xs tabular-nums text-slate-500 dark:text-slate-400">{row.count.toLocaleString()} {countLabel(row.count)}</span>
                </span>
                <span class="ml-1 text-xs font-semibold text-amber-700 dark:text-amber-300">{$_('leaderboard.spotlight_review', { default: 'Review' })}</span>
            </button>
        {/each}
    </div>
{/if}
