<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { keepGardenDomesticBird, type GardenKeepBirdResult } from '../api/garden';
    import { toastStore } from '../stores/toast.svelte';
    import { domesticBirdKind, type DomesticBirdKey, type KeptBirdCandidate } from '../utils/domestic-birds';
    import { getErrorMessage } from '../utils/error-handling';

    /**
     * A flagged species that is a domestic bird under its wild name (the bird model calls chickens
     * Red Junglefowl), with the owner's way to keep it. Shared by the Species page's checks card and
     * the Dashboard's "Needs your call", so the offer and its result read the same on both.
     */
    interface Props {
        candidates: KeptBirdCandidate[];
        /** Called after records moved to Garden, so the caller reloads without them. */
        onkept?: () => void;
        /** A narrow column stacks the sentence over the button at every width. */
        stacked?: boolean;
        size?: 'base' | 'small';
    }

    let { candidates, onkept, stacked = false, size = 'base' }: Props = $props();

    let keeping = $state<DomesticBirdKey | null>(null);
    const translate = (id: string, options: { default: string; values?: Record<string, string> }): string => $_(id, options);

    function keptMessage(kind: string, result: GardenKeepBirdResult): string {
        const parts = [
            $_('leaderboard.check.kept_bird_moved', {
                values: { count: result.moved, kind },
                default: '{count, plural, =0 {No bird records needed moving.} one {Moved # bird record to Garden.} other {Moved # bird records to Garden.}} {kind} are now in Domestic birds you keep.'
            })
        ];
        if (result.skipped > 0) {
            parts.push($_('leaderboard.check.kept_bird_skipped', {
                values: { count: result.skipped },
                default: '{count, plural, one {# record could not move and stays in bird history.} other {# records could not move and stay in bird history.}}'
            }));
        }
        if (result.remaining > 0) {
            parts.push($_('leaderboard.check.kept_bird_remaining', {
                values: { count: result.remaining },
                default: '{count, plural, one {# more record is waiting; choose the action again to move it.} other {# more records are waiting; choose the action again to move them.}}'
            }));
        }
        return parts.join(' ');
    }

    async function keep(candidate: KeptBirdCandidate): Promise<void> {
        if (keeping) return;
        keeping = candidate.bird;
        try {
            const result = await keepGardenDomesticBird(candidate.bird);
            toastStore.success(keptMessage(domesticBirdKind(candidate.bird, translate), result), 10000);
            onkept?.();
        } catch (error) {
            toastStore.error(getErrorMessage(error));
        } finally {
            keeping = null;
        }
    }
</script>

{#each candidates as candidate (candidate.bird)}
    {@const kind = domesticBirdKind(candidate.bird, translate)}
    <div
        class="flex flex-col gap-3 border-t border-line {size === 'small' ? 'pt-3' : 'pt-4'} {stacked ? '' : 'sm:flex-row sm:items-center sm:justify-between'}"
        data-spotlight-kept-bird={candidate.bird}
    >
        <p class="max-w-prose text-slate-700 dark:text-slate-200 {size === 'small' ? 'text-xs' : 'text-base'}">
            {$_('leaderboard.check.kept_bird_body', {
                values: { species: candidate.species, kind },
                default: '{species} may be a domestic bird: {kind}. If you keep them, record them as Garden animals: their bird records move to Garden, hidden from bird history, not deleted.'
            })}
        </p>
        <button
            type="button"
            class="btn btn-secondary min-h-11 shrink-0 px-4 {size === 'small' ? 'text-xs' : 'text-sm'}"
            disabled={keeping !== null}
            onclick={() => void keep(candidate)}
        >
            {keeping === candidate.bird
                ? $_('leaderboard.check.kept_bird_working', { default: 'Moving to Garden…' })
                : candidate.declared
                  ? $_('leaderboard.check.kept_bird_move', { values: { kind }, default: 'Move {kind} records to Garden' })
                  : $_('leaderboard.check.kept_bird_keep', { values: { kind }, default: 'I keep {kind}: move to Garden' })}
        </button>
    </div>
{/each}
