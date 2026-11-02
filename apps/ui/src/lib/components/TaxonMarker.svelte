<svelte:options namespace="svg" />

<script lang="ts">
    import type { NodeMarker } from '../taxonomy/tree-model';

    /**
     * One node of the family tree, drawn at the origin: a ringed dot for this bird, a solid dot on
     * its path, a green dot for a group seen here, an open dot otherwise, and a plus inside any
     * group that has more to open. The tree, the fan, the outline and the legend all draw this one.
     * `unit` is the size of one rem in the drawing's units, so the marker follows the type scale.
     */
    interface Props {
        marker: NodeMarker;
        unit: number;
    }

    let { marker, unit }: Props = $props();

    const radius = $derived((marker.closed ? 0.4375 : marker.tone === 'more' ? 0.1875 : 0.3125) * unit);
    const fill = $derived(
        {
            current: 'fill-surface',
            path: 'fill-slate-700 dark:fill-slate-200',
            seen: 'fill-emerald-600 dark:fill-emerald-400',
            plain: 'fill-surface',
            more: 'fill-surface'
        }[marker.tone]
    );
    const outline = $derived(
        marker.tone === 'path' || marker.tone === 'current'
            ? 'stroke-slate-700 dark:stroke-slate-200'
            : marker.tone === 'seen'
              ? 'stroke-emerald-600 dark:stroke-emerald-400'
              : 'stroke-slate-400 dark:stroke-slate-500'
    );
    // The plus sits on the fill, so it takes the opposite ink.
    const plus = $derived(
        marker.tone === 'plain' || marker.tone === 'current' ? 'stroke-slate-600 dark:stroke-slate-300' : 'stroke-surface'
    );
</script>

{#if marker.tone === 'current'}
    <circle r={0.5 * unit} class="fill-surface stroke-slate-900 dark:stroke-white" stroke-width={0.09375 * unit} />
    <circle r={0.25 * unit} class="fill-slate-900 dark:fill-white" />
{:else}
    <circle
        r={radius}
        class="{fill} {outline}"
        stroke-width={0.078125 * unit}
        stroke-dasharray={marker.tone === 'more' ? `${0.09375 * unit} ${0.09375 * unit}` : undefined}
    />
    {#if marker.closed}
        <path
            d="M{-0.21875 * unit},0H{0.21875 * unit}M0,{-0.21875 * unit}V{0.21875 * unit}"
            class={plus}
            stroke-width={0.078125 * unit}
            stroke-linecap="round"
        />
    {/if}
{/if}
