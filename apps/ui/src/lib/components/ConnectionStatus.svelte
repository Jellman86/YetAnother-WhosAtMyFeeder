<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { LiveFeedState } from '../utils/live-feed-state';
    import { alertsRow, audioRow, feedRow, statusSummary, type StatusRow, type StatusText, type StatusTone, type SummaryRequest } from '../utils/system-status';
    import { formatTime } from '../utils/datetime';

    let {
        birdnetEnabled = false,
        notificationsActive = null,
        feed = 'reconnecting',
        collapsed = false,
        staleSince = null,
        summary = null
    }: {
        birdnetEnabled?: boolean;
        /** Null when unread, as for a guest: the row is left out rather than guessed. */
        notificationsActive?: boolean | null;
        /** What the Frigate events row may claim: only a measured broker session makes it live. */
        feed?: LiveFeedState;
        /** The icon rail: the same rows as icons, each named by the same words. */
        collapsed?: boolean;
        /** When the owner's pushed status last arrived, set only once it is out of date. */
        staleSince?: number | null;
        /** One line instead of the list, where the sidebar has no room for the card (see statusSummary). */
        summary?: SummaryRequest | null;
    } = $props();

    const staleText = $derived(
        staleSince === null
            ? null
            : $_('status.stale_since', {
                  values: { time: formatTime(new Date(staleSince)) },
                  default: 'Status last updated {time}. Checking again.'
              })
    );

    const rows = $derived(
        [feedRow(feed), audioRow(birdnetEnabled, feed), alertsRow(notificationsActive)].filter(
            (row): row is StatusRow => row !== null
        )
    );

    const say = (text: StatusText): string => $_(text.key, { default: text.fallback });

    // The icon rail's single icon is a guest's (the owner's is the Health link), so it never counts issues.
    const summaryShown = $derived(summary ? statusSummary(rows, collapsed ? null : summary.attention) : null);
    const issuesText = $derived(
        summaryShown?.kind === 'issues'
            ? $_('status.issues_need_attention', {
                  values: { count: summaryShown.count },
                  default: '{count, plural, one {# issue needs attention} other {# issues need attention}}'
              })
            : ''
    );

    // Each tone has its own shape as well as its own colour: a filled circle is working, a
    // diamond needs a person, and a ring is off by choice or not yet known. Working is the quiet
    // case, so its dot is the smallest; a problem is the one that should catch the eye.
    const DOT: Record<StatusTone, string> = {
        ok: 'h-1.5 w-1.5 rounded-full bg-status-ok-line',
        attention: 'h-2 w-2 rotate-45 bg-status-attention-line',
        neutral: 'h-2 w-2 rounded-full border-2 border-status-neutral-line'
    };

    const ICON: Record<StatusRow['id'], string> = {
        feed: 'M5.6 18.4a9 9 0 0 1 0-12.8M18.4 5.6a9 9 0 0 1 0 12.8M8.5 15.5a5 5 0 0 1 0-7M15.5 8.5a5 5 0 0 1 0 7M12 12h.01',
        audio: 'M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3zM19 11a7 7 0 0 1-14 0M12 18v3',
        alerts: 'M15 17h5l-1.4-1.4a2 2 0 0 1-.6-1.4V11a6 6 0 1 0-12 0v3.2a2 2 0 0 1-.6 1.4L4 17h5m6 0a3 3 0 1 1-6 0m6 0H9'
    };
</script>

<!--
    A list of rows, each a small dot and the state in words. The wrapper is the one live region
    (the status role on the list itself would take its list role away). Its text changes only when
    a state changes, so a poll that finds nothing new says nothing, and each row is read whole
    ("Frigate events Not connected") rather than as a bare changed word.
-->
{#if summaryShown}
    <!-- The one line has no live region of its own: the sidebar puts it round the line, so the line can
         sit inside the owner's Health link and still be that link's words. -->
    {#if summaryShown.kind === 'issues'}
        <!-- The same words and mark as the card's Health link, so the two always read alike. -->
        <span class="flex min-w-0 items-center gap-2 font-semibold text-status-attention">
            <span class="h-2 w-2 shrink-0 rotate-45 bg-status-attention-line" aria-hidden="true"></span>
            <span class="min-w-0" data-summary-issues>{issuesText}</span>
        </span>
    {:else if collapsed}
        {@const row = summaryShown.row}
        <span
            class="relative grid h-11 w-11 place-items-center rounded-lg text-ink"
            title={`${say(row.label)}: ${say(row.state)}`}
            data-summary-row={row.id}
            data-status-tone={row.tone}
        >
            <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d={ICON[row.id]} />
            </svg>
            <span class="absolute right-0.5 top-0.5 {DOT[row.tone]}" aria-hidden="true"></span>
            <span class="sr-only">{say(row.label)}: {say(row.state)}</span>
        </span>
    {:else}
        {@const row = summaryShown.row}
        <!-- One row of the list's own kind: its dot, its label and its state in words. An out-of-date
             reading is muted and says how old it is, as the list does under its rows. -->
        <span class="flex gap-x-2" title={staleText ?? say(row.detail)} data-summary-row={row.id} data-status-tone={row.tone}>
            <span class="flex h-4 w-3 shrink-0 items-center justify-center" aria-hidden="true">
                <span class={DOT[row.tone]}></span>
            </span>
            <span class="flex min-w-0 flex-wrap items-baseline gap-x-2">
                <span class="text-muted">{say(row.label)}</span>{' '}<span class={staleText ? 'text-muted' : row.tone === 'attention' ? 'font-semibold text-status-attention' : 'text-ink'}>{say(row.state)}</span>
                {#if staleText}<span class="sr-only">{staleText}</span>{/if}
            </span>
        </span>
    {/if}
{:else}
<div role="status">
    {#if collapsed}
        <ul class="flex flex-col items-center gap-1" data-status-list data-status-collapsed>
            {#each rows as row (row.id)}
                <li
                    class="relative grid h-9 w-9 place-items-center rounded-lg text-ink"
                    title={`${say(row.label)}: ${say(row.state)}`}
                    aria-atomic="true"
                    data-status-row={row.id}
                    data-status-tone={row.tone}
                    data-status-feed={row.id === 'feed' ? feed : undefined}
                >
                    <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                        <path d={ICON[row.id]} />
                    </svg>
                    <span class="absolute right-0.5 top-0.5 {DOT[row.tone]}" aria-hidden="true" data-status-dot></span>
                    <span class="sr-only">{say(row.label)}: {say(row.state)}</span>
                </li>
            {/each}
        </ul>
    {:else}
        <ul class="space-y-1" data-status-list>
            {#each rows as row (row.id)}
                <li
                    class="grid grid-cols-[auto_minmax(0,1fr)] gap-x-2"
                    title={say(row.detail)}
                    aria-atomic="true"
                    data-status-row={row.id}
                    data-status-tone={row.tone}
                    data-status-feed={row.id === 'feed' ? feed : undefined}
                >
                    <span class="flex h-4 w-3 items-center justify-center" aria-hidden="true">
                        <span class="{DOT[row.tone]}" data-status-dot></span>
                    </span>
                    <!-- A state too long for the row drops under its label instead of being cut, and starts
                         where the label starts: alone on its line, justify-between puts it at the start, not
                         right-aligned under nothing. Beside its label it still takes the right edge. -->
                    <span class="flex min-w-0 flex-wrap items-baseline justify-between gap-x-2 text-xs leading-4">
                        <span class="text-muted" data-status-label>{say(row.label)}</span>
                        <!-- One weight for the rows: a state that is fine is plain ink, and only one that
                             needs a person is set apart, in its tone and a heavier weight. -->
                        <span
                            class="{row.tone === 'attention' ? 'font-semibold text-status-attention' : 'text-ink'}"
                            data-status-state
                        >{say(row.state)}</span>
                    </span>
                </li>
            {/each}
        </ul>
        {#if staleText}
            <!-- The rows above are from an older reading; say how old rather than let them pass for current. -->
            <p class="mt-1.5 text-xs leading-4 text-muted" data-status-stale>{staleText}</p>
        {/if}
    {/if}
</div>
{/if}
