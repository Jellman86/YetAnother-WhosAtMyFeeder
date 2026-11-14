<script lang="ts">
    import ConnectionStatus from '../src/lib/components/ConnectionStatus.svelte';
    import DayBar from '../src/lib/components/DayBar.svelte';
    import type { ServiceConnections } from '../src/lib/api/diagnostics';
    import { liveFeedState } from '../src/lib/utils/live-feed-state';

    // stream=0|1, mqtt=<state>|none, frigate=<state>: the page stream and the measured connections.
    const params = new URLSearchParams(location.search);
    if (params.get('theme') === 'dark') document.documentElement.classList.add('dark');
    const mqtt = params.get('mqtt') ?? 'none';
    const connections: ServiceConnections | null = mqtt === 'none'
        ? null
        : {
            mqtt: { state: mqtt as ServiceConnections['mqtt']['state'], server: 'mqtt.invalid', port: 1883 },
            frigate: { state: (params.get('frigate') ?? 'reachable') as ServiceConnections['frigate']['state'], url: 'http://frigate.invalid:5000', availability: 'unknown' },
            generated_at: '2026-11-13T18:00:00Z'
        };
    const feed = liveFeedState(params.get('stream') !== '0', connections);
</script>

<main class="space-y-6 bg-surface p-4" style="max-width: 1100px;">
    <div class="w-56 rounded-xl border border-line-soft p-3" data-fixture-sidebar>
        <ConnectionStatus birdnetEnabled={true} notificationsActive={false} {feed} />
    </div>
    <DayBar
        visitCount={4}
        countedBirds={null}
        countedCaptures={null}
        speciesCount={2}
        unresolvedCount={0}
        audioCalls={null}
        audioConfirmations={null}
        slots={{ countedBirds: false, audio: false }}
        {feed}
    />
</main>
