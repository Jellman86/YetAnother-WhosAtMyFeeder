<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { withAuthParams } from '../api/core';
    import type { ShowcaseRow } from '../leaderboard/showcase';

    /**
     * Species the rankings flag as probably misidentified: only the camera backs them and nobody has
     * reported them nearby. They are counted in the wall's share bar but never shown on the wall,
     * and are named here with this feeder's own crop of each. An owner checks them in the check
     * sheet, starting from the one they pick; a visitor opens the species, as before.
     */
    interface Props {
        /** Only the flagged rows. */
        checks: ShowcaseRow[];
        countLabel: (count: number) => string;
        nearbyRadiusKm?: number | null;
        onopen: (key: string) => void;
        /** Present for an owner: opens the check sheet at this species. */
        oncheck?: (key: string) => void;
    }

    let { checks, countLabel, nearbyRadiusKm = null, onopen, oncheck }: Props = $props();

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
    <section class="panel flex flex-col gap-5 lg:flex-row lg:items-center" aria-labelledby="spotlight-checks-title" data-spotlight-checks>
        <div class="min-w-0 lg:w-96 lg:shrink-0">
            <p class="flex items-center gap-2 text-sm font-bold uppercase tracking-widest text-amber-700 dark:text-amber-300">
                <span class="h-2 w-2 rounded-full bg-amber-500" aria-hidden="true"></span>{$_('leaderboard.spotlight_needs_check', { default: 'Needs a check' })}
            </p>
            <h3 id="spotlight-checks-title" class="mt-1 font-display text-2xl font-bold text-slate-900 dark:text-white">
                {$_('leaderboard.check.entry_title', { values: { count: checks.length }, default: '{count} species may be misnamed' })}
            </h3>
            <p class="mt-1 text-base text-slate-600 dark:text-slate-300">
                {nearbyRadiusKm
                    ? $_('leaderboard.check.entry_body', { values: { radius: nearbyRadiusKm }, default: 'Each rests on the camera alone, and no birder has reported it within {radius} km.' })
                    : $_('leaderboard.check.entry_body_plain', { default: 'Each rests on the camera alone.' })}
                {#if oncheck}{' '}{$_('leaderboard.check.entry_action', { default: 'See what was photographed and say what it was.' })}{/if}
            </p>
        </div>
        <ul class="flex min-w-0 flex-1 gap-3 overflow-x-auto pb-1 [scrollbar-width:thin]">
            {#each checks as row (row.key)}
                {@const thumb = pictureFor(row)}
                <li class="shrink-0">
                    <button
                        type="button"
                        class="group block w-28 text-left focus-visible:outline-none"
                        aria-label={oncheck
                            ? $_('leaderboard.check.open_one', { values: { species: row.displayName }, default: 'Check {species}' })
                            : `${$_('leaderboard.spotlight_review', { default: 'Review' })} ${row.displayName}`}
                        onclick={() => (oncheck ? oncheck(row.key) : onopen(row.key))}
                    >
                        {#if thumb}
                            <img src={thumb.url} alt="" loading="lazy" decoding="async" class="h-28 w-28 rounded-2xl object-cover ring-1 ring-line transition group-hover:ring-2 group-hover:ring-amber-400 group-focus-visible:ring-4 group-focus-visible:ring-brand-400" onerror={() => markFailed(thumb.raw)} />
                        {:else}
                            <span class="block h-28 w-28 rounded-2xl bg-surface-raised ring-1 ring-line" aria-hidden="true"></span>
                        {/if}
                        <span class="mt-2 block text-sm font-semibold leading-snug text-slate-900 dark:text-white">{row.displayName}</span>
                        <span class="block text-sm tabular-nums text-slate-500 dark:text-slate-400">{row.count.toLocaleString()} {countLabel(row.count)}</span>
                    </button>
                </li>
            {/each}
        </ul>
        {#if oncheck}
            <button type="button" class="btn btn-primary min-h-12 shrink-0 px-5 text-base" onclick={() => oncheck(checks[0].key)} data-spotlight-checks-start>
                {$_('leaderboard.check.start', { values: { count: checks.length }, default: 'Check {count} species' })}
            </button>
        {/if}
    </section>
{/if}
