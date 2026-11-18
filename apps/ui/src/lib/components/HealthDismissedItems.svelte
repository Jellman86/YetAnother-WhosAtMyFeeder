<script lang="ts" module>
    export interface DismissedHealthItem {
        key: string;
        title: string;
        /** When it last happened, in ms. */
        lastSeenAt: number;
        /** The backend entries Restore shows again. */
        entryIds: string[];
    }
</script>

<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { formatDateTime } from '../utils/datetime';

    /**
     * The footer of a Health history card: what the owner dismissed from that card, behind a
     * Show/Hide toggle, each with Restore. It sits inside the card it belongs to, under a divider.
     */
    interface Props {
        items: DismissedHealthItem[];
        /** The key of the item being restored, so only its button waits. */
        restoring: string | null;
        onrestore: (item: DismissedHealthItem) => void;
    }

    let { items, restoring, onrestore }: Props = $props();

    let open = $state(false);
    let toggle = $state<HTMLButtonElement | null>(null);
    const listId = $props.id();

    /** Where focus goes after a dismissal, so a keyboard user is not dropped to the top of the page. */
    export function focusToggle(): void {
        toggle?.focus();
    }
</script>

{#if items.length > 0}
    <div class="mt-4 border-t border-line-soft pt-3" data-health-dismissed>
        <div class="flex flex-wrap items-center justify-between gap-2">
            <h3 class="eyebrow">{$_('jobs.health_dismiss.dismissed_heading', { default: 'Dismissed' })}</h3>
            <button
                bind:this={toggle}
                type="button"
                class="btn btn-secondary min-h-11 px-3 py-2 text-xs"
                aria-expanded={open}
                aria-controls={listId}
                onclick={() => { open = !open; }}
                data-health-dismissed-toggle
            >
                {open
                    ? $_('jobs.health_dismiss.hide_dismissed', { default: 'Hide dismissed' })
                    : $_('jobs.health_dismiss.show_dismissed', { values: { count: items.length }, default: '{count, plural, one {Show # dismissed} other {Show # dismissed}}' })}
            </button>
        </div>
        <div id={listId} hidden={!open}>
            <p class="mt-2 max-w-prose text-sm text-ink">
                {$_('jobs.health_dismiss.dismissed_note', { default: 'Hidden for everyone on this install. Live checks carry on, and an item shows again if it happens again. Clear error history removes these too.' })}
            </p>
            <ul class="mt-2 divide-y divide-line-soft" data-health-dismissed-list>
                {#each items as item, index (item.key)}
                    {@const titleId = `${listId}-item-${index}`}
                    <li class="flex flex-wrap items-start justify-between gap-x-3 gap-y-1 py-2" data-health-dismissed-item>
                        <div class="min-w-0 flex-1 basis-48">
                            <p id={titleId} class="wrap-break-word text-sm font-semibold text-strong">{item.title}</p>
                            <p class="text-xs tabular-nums text-ink">
                                {$_('jobs.health_dismiss.last_seen', { values: { at: formatDateTime(item.lastSeenAt) }, default: 'Last happened {at}' })}
                            </p>
                        </div>
                        <button
                            type="button"
                            class="btn btn-secondary min-h-11 shrink-0 px-3 py-2 text-xs"
                            aria-describedby={titleId}
                            disabled={restoring !== null}
                            onclick={() => onrestore(item)}
                            data-health-restore
                        >
                            {restoring === item.key
                                ? $_('jobs.health_dismiss.restoring', { default: 'Restoring…' })
                                : $_('jobs.health_dismiss.restore', { default: 'Restore' })}
                        </button>
                    </li>
                {/each}
            </ul>
        </div>
    </div>
{/if}
