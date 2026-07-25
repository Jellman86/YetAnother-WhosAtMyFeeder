<script lang="ts">
    import { onMount } from 'svelte';
    import { fetchSystemTelemetry } from '../api/system';
    import {
        appendTelemetrySample,
        telemetryPolyline,
        type TelemetryPoint
    } from './systemTelemetryGraph';

    const SAMPLE_INTERVAL_MS = 2_500;

    let history = $state<TelemetryPoint[]>([]);
    let sampling = false;
    let inViewport = false;
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

    async function takeSample(): Promise<void> {
        if (sampling || document.hidden || !inViewport) return;
        sampling = true;
        try {
            const sample = await fetchSystemTelemetry();
            if (!inViewport || document.hidden) return;
            history = appendTelemetrySample(history, sample);
        } catch {
            // Telemetry is decorative; never leave stale values looking live.
            history = [];
        } finally {
            sampling = false;
        }
    }

    onMount(() => {
        const observer = new IntersectionObserver(([entry]) => {
            const isVisible = entry?.isIntersecting ?? false;
            if (isVisible === inViewport) return;
            inViewport = isVisible;
            if (inViewport && !document.hidden) {
                void takeSample();
            } else {
                history = [];
            }
        });
        observer.observe(container);

        const interval = window.setInterval(() => void takeSample(), SAMPLE_INTERVAL_MS);
        const handleVisibility = () => {
            if (document.hidden) {
                history = [];
            } else if (inViewport) {
                void takeSample();
            }
        };
        document.addEventListener('visibilitychange', handleVisibility);
        return () => {
            observer.disconnect();
            window.clearInterval(interval);
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
            class="absolute inset-x-0 bottom-0 h-full w-full"
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
        <div class="absolute right-3 top-2 flex items-center gap-2 text-[0.5625rem] font-semibold tabular-nums">
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
