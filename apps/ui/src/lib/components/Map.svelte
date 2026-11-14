<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { _ } from 'svelte-i18n';
  import { markerName, markerPopup, type MapMarker } from '../utils/map-popup';
  import type { Layer, Map as LeafletMap } from 'leaflet';

  type LeafletApi = typeof import('leaflet');

  // Props
  export let markers: MapMarker[] = [];
  
  // Center can be explicitly provided, or auto-calculated from markers
  export let center: [number, number] | null = null;
  export let zoom: number = 10;
  export let userLocation: [number, number] | null = null; // To show "You are here"
  export let obfuscate: boolean = false;

  let mapElement: HTMLElement;
  let map: LeafletMap | null = null;
  let L: LeafletApi | null = null;

  // Track map instance to destroy
  onDestroy(() => {
    if (map) {
      map.remove();
      map = null;
    }
  });

  // Re-render markers when props change
  $: if (map && L && markers) {
    updateMarkers();
  }

  onMount(async () => {
    if (typeof window !== 'undefined') {
      // Dynamic import to avoid SSR issues (though this is SPA, it's good practice)
      const leafletModule = await import('leaflet');
      L = leafletModule.default as unknown as LeafletApi;
      
      // Import CSS
      await import('leaflet/dist/leaflet.css');

      initMap();
    }
  });

  function initMap() {
    if (!mapElement || map) return;
    if (!L) return;

    // Default center logic
    let initialCenter = center;
    let initialZoom = zoom;

    if (!initialCenter) {
        if (userLocation) {
            initialCenter = userLocation;
        } else if (markers.length > 0) {
            if (obfuscate) {
                // Privacy Mode: Center on a RANDOM marker (bird) instead of the geometric center
                // This prevents "zoom to center" from revealing the user's home location
                const randomMarker = markers[Math.floor(Math.random() * markers.length)];
                initialCenter = [randomMarker.lat, randomMarker.lng];
                initialZoom = 12; // Start closer in
            } else {
                initialCenter = [markers[0].lat, markers[0].lng];
            }
        } else {
            initialCenter = [0, 0];
        }
    }

    map = L.map(mapElement, {
        attributionControl: false // Cleaner look, add manually if needed or stick to bottom-right
    }).setView(initialCenter, initialZoom);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19
    }).addTo(map);

    updateMarkers();
    
    // Auto-fit bounds logic (only if we didn't force a center or obfuscate)
    if (markers.length > 0 && !center && !userLocation && !obfuscate) {
        const group = L.featureGroup(markers.map(m => L!.marker([m.lat, m.lng])));
        map.fitBounds(group.getBounds().pad(0.1));
    }
  }

  function updateMarkers() {
    if (!map || !L) return;
    const mapInstance = map;
    const leaflet = L;

    // Clear existing layers (except tiles)
    mapInstance.eachLayer((layer: Layer) => {
      if (
        layer instanceof leaflet.Marker ||
        layer instanceof leaflet.CircleMarker ||
        layer instanceof leaflet.Circle
      ) {
        mapInstance.removeLayer(layer);
      }
    });

    // Each pin is a small dot centred in a 24px target, so it can be hit with a finger or a
    // shaky pointer without the dot itself growing over the map.
    const pinIcon = (colour: string, dot: number) => leaflet.divIcon({
        className: 'custom-div-icon',
        html: `<div style="display: grid; place-items: center; width: 24px; height: 24px;"><div style="background-color: ${colour}; width: ${dot}px; height: ${dot}px; border-radius: 50%; border: 2px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.3);"></div></div>`,
        iconSize: [24, 24],
        iconAnchor: [12, 12],
        popupAnchor: [0, -8]
    });
    const birdIcon = pinIcon('#ef4444', 12);

    const homeIcon = pinIcon('#3b82f6', 14);

    // Draw User Location/Home Radius if available
    if (userLocation) {
        // A pin is a keyboard-reachable button, so each one carries a name.
        const yourLocation = $_('common.map_your_location', { default: 'Your location' });
        leaflet.marker(userLocation, { icon: homeIcon, title: yourLocation })
         .bindPopup(yourLocation)
         .addTo(mapInstance);
         
        // Optional: Draw a subtle circle if we knew the radius (passed via props perhaps?)
    }

    // Draw Bird Markers
    markers.forEach(m => {
        const marker = leaflet.marker([m.lat, m.lng], {
            icon: birdIcon,
            title: markerName(m, $_('common.map_sighting', { default: 'Sighting location' }))
        }).addTo(mapInstance);
        
        const content = markerPopup(m);
        if (content) marker.bindPopup(content);
    });
  }
</script>

<div class="relative w-full h-full min-h-[200px] bg-slate-100 rounded-md overflow-hidden border border-slate-200 dark:border-slate-700 dark:bg-slate-800">
    <div bind:this={mapElement} class="w-full h-full z-0"></div>
</div>

<style>
    /* Leaflet CSS overrides if needed */
    :global(.leaflet-popup-content-wrapper) {
        border-radius: 0.5rem;
        font-family: inherit;
    }
    :global(.leaflet-popup-content) {
        margin: 0.8rem 1rem;
        line-height: 1.4;
    }
</style>
