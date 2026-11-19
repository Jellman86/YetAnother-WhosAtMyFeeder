<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fetchSystemTelemetry } from '../api/system';
    import { telemetrySampleDelayMs } from '../app/public-refresh-budget';
    import { authStore } from '../stores/auth.svelte';
    import { systemStatusStore, telemetrySampleFrom } from '../stores/system_status.svelte';
    import { appendTelemetrySample, loadMeters, type TelemetryPoint } from './systemLoadMeters';

    let history = $state<TelemetryPoint[]>([]);
    /** The last sample failed (a visitor may be rate-limited): the graph keeps it, marked as not current. */
    let stale = $state(false);
    let failures = 0;
    let sampling = false;
    let lastPushedAt: number | null = null;
    let inViewport = false;
    let nextSample: number | null = null;
    let container: HTMLDivElement;

    const meters = $derived(loadMeters(history.at(-1), $_('system_telemetry.cpu', { default: 'CPU' })));

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
    The load as meters, one row each for the CPU and the accelerator: its name, a bar that fills, and
    the figure. Each bar wears its series' colour on the Health chart, and the figure says the value,
    so nothing rests on the colour. A tall bar is the warning; the card adds no colour of its own, since
    a busy host is not a fault. Rows sit in the card's own flow, never behind the status rows, and the
    block keeps a row's height before the first reading, so nothing below it moves when one arrives.
-->
<div bind:this={container} data-system-telemetry class="mt-3 min-h-4 overflow-y-clip text-xs leading-4">
    {#if meters.length > 0}
        <!-- One grid, so every bar starts and ends on the same lines whatever the names are. The figures are
             clipped vertically with the block: the faces' font boxes are taller than the line, and Chromium
             counted that overhang (about 1.5px) as something to scroll to. -->
        <dl
            class="load-meters grid items-center gap-x-2 gap-y-1.5 tabular-nums"
            data-telemetry-readout
            data-telemetry-stale={stale}
        >
            {#each meters as meter (meter.id)}
                <div class="contents" data-telemetry-meter={meter.id}>
                    <dt class="text-muted">{meter.label}</dt>
                    <dd class="col-span-2 grid grid-cols-subgrid items-center">
                        <span class="block h-1.5 overflow-hidden rounded-full bg-track {stale ? 'opacity-50' : ''}" aria-hidden="true">
                            <span class="block h-full rounded-full {meter.fill}" style="width: {meter.percent}%"></span>
                        </span>
                        <span class="text-right text-ink">{meter.shown}</span>
                    </dd>
                </div>
            {/each}
        </dl>
        {#if stale}
            <!-- A failed sample keeps the last figures, said to be old rather than passed off as current. -->
            <p class="mt-1 text-muted" data-telemetry-last-reading>{$_('system_telemetry.last_reading', { default: 'Last reading' })}</p>
        {/if}
    {/if}
</div>

<style>
    /* Name, bar, figure: the names take what the longest needs, and the bar takes the rest. */
    .load-meters {
        grid-template-columns: auto minmax(0, 1fr) auto;
    }
</style>
