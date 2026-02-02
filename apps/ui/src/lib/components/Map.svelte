<script lang="ts">
  import { onMount, onDestroy } from 'svelte';

  // Props
  export let markers: { 
    lat: number; 
    lng: number; 
    title?: string; 
    popupText?: string;
    isCenter?: boolean; 
  }[] = [];
  
  // Center can be explicitly provided, or auto-calculated from markers
  export let center: [number, number] | null = null;
  export let zoom: number = 10;
  export let userLocation: [number, number] | null = null; // To show "You are here"
  export let obfuscate: boolean = false;

  let mapElement: HTMLElement;
  let map: any;
  let L: any;

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
      L = leafletModule.default;
      
      // Import CSS
      await import('leaflet/dist/leaflet.css');

      initMap();
    }
  });

  function initMap() {
    if (!mapElement || map) return;

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
        const group = new L.featureGroup(markers.map(m => L.marker([m.lat, m.lng])));
        map.fitBounds(group.getBounds().pad(0.1));
    }
  }

  function updateMarkers() {
    if (!map || !L) return;

    // Clear existing layers (except tiles)
    map.eachLayer((layer: any) => {
      if (layer instanceof L.Marker || layer instanceof L.CircleMarker || layer instanceof L.Circle) {
        map.removeLayer(layer);
      }
    });

    // Custom Icon for Birds
    const birdIcon = L.divIcon({
        className: 'custom-div-icon',
        html: `<div style="background-color: #ef4444; width: 12px; height: 12px; border-radius: 50%; border: 2px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.3);"></div>`,
        iconSize: [12, 12],
        iconAnchor: [6, 6],
        popupAnchor: [0, -6]
    });

    // Custom Icon for User (Home)
    const homeIcon = L.divIcon({
        className: 'custom-div-icon',
        html: `<div style="background-color: #3b82f6; width: 14px; height: 14px; border-radius: 50%; border: 2px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.3);"></div>`,
        iconSize: [14, 14],
        iconAnchor: [7, 7],
        popupAnchor: [0, -7]
    });

    // Draw User Location/Home Radius if available
    if (userLocation) {
        L.marker(userLocation, { icon: homeIcon })
         .bindPopup("Your Location")
         .addTo(map);
         
        // Optional: Draw a subtle circle if we knew the radius (passed via props perhaps?)
    }

    // Draw Bird Markers
    markers.forEach(m => {
        const marker = L.marker([m.lat, m.lng], { icon: birdIcon }).addTo(map);
        
        if (m.popupText) {
            marker.bindPopup(m.popupText);
        } else if (m.title) {
             marker.bindPopup(`<b>${m.title}</b>`);
        }
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
