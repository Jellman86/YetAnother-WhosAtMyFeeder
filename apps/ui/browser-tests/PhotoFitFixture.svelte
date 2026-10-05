<script lang="ts">
    import DetectionCard from '../src/lib/components/DetectionCard.svelte';
    import type { Detection } from '../src/lib/api';

    // One real detection card per photograph the spec supplies, named by capture id. ?ids=a,b,c
    const ids = (new URLSearchParams(location.search).get('ids') ?? 'tall,square,scene').split(',');

    function capture(id: string): Detection {
        return {
            frigate_event: id,
            display_name: 'Downy Woodpecker',
            common_name: 'Downy Woodpecker',
            camera_name: 'bird_cam_1',
            detection_time: '2026-10-05T08:45:00Z',
            score: 0.9
        };
    }
</script>

<div class="grid max-w-5xl grid-cols-2 gap-4 p-4 sm:grid-cols-3">
    {#each ids as id (id)}
        <div data-photo-case={id}><DetectionCard detection={capture(id)} /></div>
    {/each}
</div>
