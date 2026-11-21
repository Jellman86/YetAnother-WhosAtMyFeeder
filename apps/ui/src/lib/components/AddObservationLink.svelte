<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { ADD_OBSERVATION_ICON, ADD_OBSERVATION_PATH, isPlainClick } from '../app/add-observation';
    import { pointerMayPrefetch } from '../app/route-prefetch';
    import { toAppPath } from '../app/url-base';

    /**
     * The way to Add observation: a real link, so it can open in a new tab, handled in place on a
     * plain click so unsaved work elsewhere is asked about first. `icon` is the header's square
     * control beside Refresh and the camera; `labelled` is a kit button with its name written out.
     * The phone menu's place is the sidebar's own row, drawn from the same address and icon.
     */
    type Props = {
        variant: 'icon' | 'labelled';
        current?: boolean;
        onNavigate?: (path: string) => void;
        onPrefetch?: (path: string) => void;
    };

    let { variant, current = false, onNavigate, onPrefetch }: Props = $props();

    const label = $derived($_('nav.add_observation', { default: 'Add observation' }));

    function open(event: MouseEvent): void {
        if (!onNavigate || !isPlainClick(event)) return;
        event.preventDefault();
        onNavigate(ADD_OBSERVATION_PATH);
    }
</script>

<a
    href={toAppPath(ADD_OBSERVATION_PATH)}
    class={variant === 'icon'
        ? `grid min-h-11 min-w-11 place-items-center rounded-xl transition-colors duration-200 focus-ring ${current ? 'bg-accent-soft text-accent-ink' : 'text-muted hover:bg-surface-raised hover:text-strong'}`
        : 'btn btn-secondary min-h-11 px-3 py-2 text-xs'}
    title={variant === 'icon' ? label : undefined}
    aria-label={variant === 'icon' ? label : undefined}
    aria-current={current ? 'page' : undefined}
    data-add-observation={variant}
    onclick={open}
    onpointerenter={(event) => { if (onPrefetch && pointerMayPrefetch(event.pointerType)) onPrefetch(ADD_OBSERVATION_PATH); }}
    onfocus={() => onPrefetch?.(ADD_OBSERVATION_PATH)}
>
    <svg xmlns="http://www.w3.org/2000/svg" class={variant === 'icon' ? 'h-5 w-5' : 'h-4 w-4'} fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" d={ADD_OBSERVATION_ICON} />
    </svg>
    {#if variant === 'labelled'}
        <span>{label}</span>
    {/if}
</a>
