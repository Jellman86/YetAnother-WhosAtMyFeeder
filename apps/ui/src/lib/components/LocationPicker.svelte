<script lang="ts">
    import { onDestroy, onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import type { LeafletMouseEvent, Map as LeafletMap, Marker } from 'leaflet';

    type LeafletApi = typeof import('leaflet');

    interface Props {
        latitude: number | null;
        longitude: number | null;
        center?: [number, number];
        onchange: (latitude: number, longitude: number) => void;
    }

    let { latitude, longitude, center = [20, 0], onchange }: Props = $props();
    let mapElement = $state<HTMLElement | null>(null);
    let map: LeafletMap | null = null;
    let marker: Marker | null = null;
    let leaflet: LeafletApi | null = null;

    const hasLocation = $derived(latitude != null && longitude != null);
    const coordinateAnnouncement = $derived(
        hasLocation
            ? $_('manual_observation.location.selected', {
                values: { latitude: latitude?.toFixed(5), longitude: longitude?.toFixed(5) },
                default: 'Pin selected at {latitude}, {longitude}'
            })
            : $_('manual_observation.location.unselected', { default: 'No sighting location selected' })
    );

    function pinIcon(api: LeafletApi) {
        return api.divIcon({
            className: 'manual-observation-pin',
            html: '<span aria-hidden="true"></span>',
            iconSize: [44, 44],
            iconAnchor: [22, 42]
        });
    }

    function chooseLocation(nextLatitude: number, nextLongitude: number): void {
        onchange(Number(nextLatitude.toFixed(7)), Number(nextLongitude.toFixed(7)));
    }

    function syncMarker(): void {
        if (!map || !leaflet) return;
        if (!hasLocation || latitude == null || longitude == null) {
            if (marker) map.removeLayer(marker);
            marker = null;
            return;
        }
        if (!marker) {
            marker = leaflet.marker([latitude, longitude], {
                icon: pinIcon(leaflet),
                draggable: true,
                title: $_('manual_observation.location.pin_label', { default: 'Sighting location pin; drag to adjust' }),
                alt: $_('manual_observation.location.pin_label', { default: 'Sighting location pin; drag to adjust' })
            }).addTo(map);
            marker.on('dragend', () => {
                const position = marker?.getLatLng();
                if (position) chooseLocation(position.lat, position.lng);
            });
        } else {
            marker.setLatLng([latitude, longitude]);
        }
    }

    $effect(() => {
        latitude;
        longitude;
        syncMarker();
    });

    onMount(async () => {
        const module = await import('leaflet');
        leaflet = module.default as unknown as LeafletApi;
        await import('leaflet/dist/leaflet.css');
        if (!mapElement || !leaflet) return;
        const initialCenter: [number, number] = hasLocation && latitude != null && longitude != null
            ? [latitude, longitude]
            : center;
        map = leaflet.map(mapElement, { scrollWheelZoom: false }).setView(initialCenter, hasLocation ? 14 : 3);
        leaflet.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            maxZoom: 19
        }).addTo(map);
        map.on('click', (event: LeafletMouseEvent) => chooseLocation(event.latlng.lat, event.latlng.lng));
        syncMarker();
    });

    onDestroy(() => {
        map?.remove();
        map = null;
        marker = null;
    });
</script>

<div class="overflow-hidden rounded-2xl border border-slate-200 bg-slate-100 dark:border-slate-700 dark:bg-slate-800">
    <div bind:this={mapElement} class="h-64 w-full" aria-label={$_('manual_observation.location.map_label', { default: 'Map for placing the sighting pin' })}></div>
</div>
<p class="mt-2 text-xs leading-5 text-slate-500 dark:text-slate-400">
    {$_('manual_observation.location.map_help', { default: 'Click or tap the map to place the pin. Drag it to make a precise adjustment.' })}
</p>
<p class="sr-only" aria-live="polite">{coordinateAnnouncement}</p>

<style>
    :global(.manual-observation-pin) {
        background: transparent;
        border: 0;
    }

    :global(.manual-observation-pin span) {
        display: block;
        width: 34px;
        height: 34px;
        margin-left: 5px;
        border: 3px solid white;
        border-radius: 50% 50% 50% 0;
        background: rgb(13 148 136);
        box-shadow: 0 6px 14px rgb(15 23 42 / 35%);
        transform: rotate(-45deg);
    }

    :global(.leaflet-control-zoom a) {
        width: 44px !important;
        height: 44px !important;
        line-height: 44px !important;
    }
</style>
