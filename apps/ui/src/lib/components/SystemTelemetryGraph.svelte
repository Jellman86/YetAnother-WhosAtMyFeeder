<script lang="ts">
    interface Props {
        /** Where the live readout sits; the host card reserves that row so nothing draws over it. */
        readoutClass?: string;
    }

    let { readoutClass = 'bottom-3 left-3' }: Props = $props();

    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fetchSystemTelemetry } from '../api/system';
    import { telemetrySampleDelayMs } from '../app/public-refresh-budget';
    import { authStore } from '../stores/auth.svelte';
    import {
        appendTelemetrySample,
        telemetryPolyline,
        type TelemetryPoint
    } from './systemTelemetryGraph';

    let history = $state<TelemetryPoint[]>([]);
    /** The last sample failed (a visitor may be rate-limited): the graph keeps it, marked as not current. */
    let stale = $state(false);
    let failures = 0;
    let sampling = false;
    let inViewport = false;
    let nextSample: number | null = null;
    let container: HTMLDivElement;

    let current = $derived(history.at(-1));
    let cpuPoints = $derived(telemetryPolyline(history, 'cpu'));
    let acceleratorPoints = $derived(telemetryPolyline(history, 'accelerator'));
    let cpuArea = $derived(cpuPoints ? `0,100 ${cpuPoints} 100,100` : '');

    function displayPercent(value: number | null | undefined): string | null {
        return typeof value === 'number' ? `${Math.round(value)}%` : null;
    }

    let currentCpuPercent = $derived(displayPercent(current?.cpu));
    let currentAcceleratorPercent = $derived(displayPercent(current?.accelerator));

    function watched(): boolean {
        return inViewport && !document.hidden;
    }

    function cancelNextSample(): void {
        if (nextSample !== null) window.clearTimeout(nextSample);
        nextSample = null;
    }

    function scheduleNextSample(): void {
        cancelNextSample();
        if (!watched()) return;
        const delay = telemetrySampleDelayMs({
            guest: authStore.isGuest,
            cap: authStore.publicAccessRateLimitPerMinute,
            failures
        });
        nextSample = window.setTimeout(() => void takeSample(), delay);
    }

    async function takeSample(): Promise<void> {
        cancelNextSample();
        if (sampling || !watched()) return;
        sampling = true;
        try {
            const sample = await fetchSystemTelemetry();
            if (!watched()) return;
            history = appendTelemetrySample(history, sample);
            stale = false;
            failures = 0;
        } catch {
            failures += 1;
            stale = history.length > 0;
        } finally {
            sampling = false;
            scheduleNextSample();
        }
    }

    // Nothing is sampled while no one can see the graph, and a gap is not drawn as a continuous line.
    function pause(): void {
        cancelNextSample();
        history = [];
        stale = false;
    }

    onMount(() => {
        const observer = new IntersectionObserver(([entry]) => {
            const isVisible = entry?.isIntersecting ?? false;
            if (isVisible === inViewport) return;
            inViewport = isVisible;
            if (watched()) void takeSample();
            else pause();
        });
        observer.observe(container);

        const handleVisibility = () => {
            if (watched()) void takeSample();
            else pause();
        };
        document.addEventListener('visibilitychange', handleVisibility);
        return () => {
            observer.disconnect();
            cancelNextSample();
            document.removeEventListener('visibilitychange', handleVisibility);
        };
    });
</script>

<div
    bind:this={container}
    data-system-telemetry
    class="pointer-events-none absolute inset-0 overflow-hidden rounded-xl"
    aria-hidden="true"
>
    {#if cpuPoints}
        <svg
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
            class="absolute inset-x-0 bottom-0 h-full w-full {stale ? 'opacity-50' : ''}"
            data-telemetry-stale={stale}
        >
            <polygon
                points={cpuArea}
                fill="currentColor"
                class="text-brand-500 opacity-[0.07] dark:text-brand-400 dark:opacity-[0.09]"
            />
            <polyline
                points={cpuPoints}
                fill="none"
                stroke="currentColor"
                stroke-width="1.25"
                vector-effect="non-scaling-stroke"
                class="text-brand-500 opacity-20 dark:text-brand-400 dark:opacity-25"
            />
            {#if acceleratorPoints}
                <polyline
                    points={acceleratorPoints}
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.1"
                    vector-effect="non-scaling-stroke"
                    class="text-indigo-500 opacity-20 dark:text-indigo-400 dark:opacity-25"
                />
            {/if}
        </svg>
    {/if}

    {#if current}
        <div class="absolute {readoutClass} flex items-center gap-2 text-3xs font-semibold tabular-nums">
            {#if stale}
                <span class="text-slate-500 dark:text-slate-400">{$_('system_telemetry.last_reading', { default: 'Last reading' })}</span>
            {/if}
            {#if currentCpuPercent}
                <span class="text-brand-700/70 dark:text-brand-300/70">CPU {currentCpuPercent}</span>
            {/if}
            {#if currentAcceleratorPercent}
                <span class="text-indigo-700/70 dark:text-indigo-300/70">
                    {current.acceleratorLabel ?? ''} {currentAcceleratorPercent}
                </span>
            {/if}
        </div>
    {/if}
</div>
