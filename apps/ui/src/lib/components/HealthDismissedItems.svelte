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
    <div class="space-y-2" data-health-dismissed>
        <button
            bind:this={toggle}
            type="button"
            class="btn btn-ghost min-h-11 px-3 py-2 text-xs"
            aria-expanded={open}
            aria-controls={listId}
            onclick={() => { open = !open; }}
            data-health-dismissed-toggle
        >
            {open
                ? $_('jobs.health_dismiss.hide_dismissed', { default: 'Hide dismissed' })
                : $_('jobs.health_dismiss.show_dismissed', { values: { count: items.length }, default: '{count, plural, one {Show # dismissed} other {Show # dismissed}}' })}
        </button>
        <div id={listId} hidden={!open} class="card-base rounded-2xl p-4">
            <p class="max-w-prose text-sm text-ink">
                {$_('jobs.health_dismiss.dismissed_note', { default: 'Hidden for everyone on this install. Live checks carry on, and an item shows again if it happens again. Clear error history removes these too.' })}
            </p>
            <ul class="mt-3 divide-y divide-line-soft" data-health-dismissed-list>
                {#each items as item, index (item.key)}
                    {@const titleId = `${listId}-item-${index}`}
                    <li class="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 py-2" data-health-dismissed-item>
                        <div class="min-w-0 flex-1 basis-48">
                            <p id={titleId} class="wrap-break-word text-sm font-semibold text-strong">{item.title}</p>
                            <p class="text-xs tabular-nums text-ink">
                                {$_('jobs.health_dismiss.last_seen', { values: { at: formatDateTime(item.lastSeenAt) }, default: 'Last happened {at}' })}
                            </p>
                        </div>
                        <button
                            type="button"
                            class="btn btn-ghost min-h-11 px-3 py-2 text-xs"
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
