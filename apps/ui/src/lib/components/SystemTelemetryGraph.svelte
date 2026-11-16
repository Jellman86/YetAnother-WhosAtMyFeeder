<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fetchSystemTelemetry } from '../api/system';
    import { telemetrySampleDelayMs } from '../app/public-refresh-budget';
    import { authStore } from '../stores/auth.svelte';
    import { systemStatusStore, telemetrySampleFrom } from '../stores/system_status.svelte';
    import Separator from './Separator.svelte';
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
    let lastPushedAt: number | null = null;
    let inViewport = false;
    let nextSample: number | null = null;
    let container: HTMLDivElement;

    let current = $derived(history.at(-1));
    let cpuPoints = $derived(telemetryPolyline(history, 'cpu'));

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

    /**
     * An owner's samples arrive with the pushed status, so the line costs no requests. A visitor
     * never receives the status and samples the endpoint as before.
     */
    function pushedSamples(): boolean {
        return authStore.showSettings;
    }

    function takePushedSample(): void {
        const telemetry = systemStatusStore.snapshot?.telemetry;
        if (!telemetry || !watched() || telemetry.sampled_at === lastPushedAt) return;
        lastPushedAt = telemetry.sampled_at;
        history = appendTelemetrySample(history, telemetrySampleFrom(telemetry));
        stale = false;
    }

    async function takeSample(): Promise<void> {
        cancelNextSample();
        if (pushedSamples()) {
            takePushedSample();
            return;
        }
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
        lastPushedAt = null;
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
        const stopFollowingStatus = systemStatusStore.subscribe(() => {
            if (pushedSamples()) takePushedSample();
        });
        return () => {
            stopFollowingStatus();
            observer.disconnect();
            cancelNextSample();
            document.removeEventListener('visibilitychange', handleVisibility);
        };
    });
</script>

<!--
    One muted line in the card's own flow: the readings as plain text, with a small trace of
    recent CPU load beside them. It is not a link and never sits behind the status rows. The row
    keeps its height before the first reading, so nothing below it moves when one arrives.
-->
<div
    bind:this={container}
    data-system-telemetry
    class="mt-2 flex min-h-4 items-center justify-between gap-2 text-xs leading-4 text-slate-600 dark:text-slate-400"
>
    {#if current}
        <p class="min-w-0 tabular-nums" data-telemetry-readout data-telemetry-stale={stale}>
            {#if stale}
                <span>{$_('system_telemetry.last_reading', { default: 'Last reading' })}:</span>
            {/if}
            {#if currentCpuPercent}
                <span class="whitespace-nowrap">CPU {currentCpuPercent}</span>
            {/if}
            {#if currentCpuPercent && currentAcceleratorPercent}
                <Separator />
            {/if}
            {#if currentAcceleratorPercent}
                <span class="whitespace-nowrap">{current.acceleratorLabel ?? ''} {currentAcceleratorPercent}</span>
            {/if}
        </p>
        {#if cpuPoints}
            <svg
                viewBox="0 0 100 100"
                preserveAspectRatio="none"
                class="h-4 w-12 shrink-0 {stale ? 'opacity-50' : ''}"
                aria-hidden="true"
                data-telemetry-trace
            >
                <polyline
                    points={cpuPoints}
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.5"
                    vector-effect="non-scaling-stroke"
                />
            </svg>
        {/if}
    {/if}
</div>
