<script lang="ts">
    import BirdCountRegionImage from './BirdCountRegionImage.svelte';
    import HoverPopoutPanel from './HoverPopoutPanel.svelte';
    import { HoverPopout } from '../utils/hover-popout.svelte';

    let { src, box, label, reason }: { src: string; box: readonly number[]; label: string; reason: string } = $props();
    const uid = $props.id();
    const popout = new HoverPopout(uid, { width: 240, estimatedHeight: 310 });
    let touch = false;

    function outside(event: MouseEvent): void {
        const target = event.target;
        if (popout.openIndex !== null && target instanceof Node && !popout.root?.contains(target) &&
            !document.getElementById(popout.panelId())?.contains(target)) popout.hide(true);
    }
</script>

<svelte:window onclick={outside} />
<span bind:this={popout.root} class="relative inline-flex shrink-0" role="presentation"
    onpointerenter={(event) => popout.pointerEnter(event)} onmouseleave={() => popout.hide()}
    onfocusin={(event) => popout.focusIn(event)} onfocusout={popout.focusOut} onkeydown={popout.keydown}>
    <button type="button" bind:this={popout.triggers[0]} aria-label={label} aria-describedby={popout.describedBy()}
        class="h-11 w-11 overflow-hidden rounded-lg border border-slate-300 focus-ring dark:border-slate-600"
        onpointerdown={(event) => { touch = event.pointerType === 'touch'; }}
        onclick={(event) => { if (event.detail > 0 && touch && popout.openIndex === 0) popout.hide(true); else popout.show(); }}>
        <BirdCountRegionImage {src} {box} />
    </button>
    {#if popout.openIndex === 0}
        <HoverPopoutPanel {popout} data-bird-count-region-preview>
            <div class="aspect-square w-full"><BirdCountRegionImage {src} {box} alt={label} /></div>
            <div class="space-y-1 p-3"><p class="text-sm font-semibold">{label}</p><p class="text-xs text-slate-600 dark:text-slate-300">{reason}</p></div>
        </HoverPopoutPanel>
    {/if}
</span>
