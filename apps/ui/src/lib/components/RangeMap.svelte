<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { _ } from 'svelte-i18n';

  export let tileUrl: string;
  export let opacity: number = 0.65;
  export let zoom: number = 1;
  export let center: [number, number] = [0, 20];
  export let heightClass: string = 'h-[220px]';

  let mapElement: HTMLElement;
  let map: any;
  let L: any;
  let resizeObserver: ResizeObserver | null = null;

  onDestroy(() => {
    if (map) {
      map.remove();
      map = null;
    }
    if (resizeObserver) {
      resizeObserver.disconnect();
      resizeObserver = null;
    }
  });

  onMount(async () => {
    if (typeof window === 'undefined') return;

    const leafletModule = await import('leaflet');
    L = leafletModule.default;
    await import('leaflet/dist/leaflet.css');

    initMap();
  });

  function initMap() {
    if (!mapElement || map) return;

    map = L.map(mapElement, {
      attributionControl: false,
      zoomControl: false,
      scrollWheelZoom: false
    }).setView(center, zoom);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 6,
      minZoom: 1
    }).addTo(map);

    if (tileUrl) {
      L.tileLayer(tileUrl, {
        opacity,
        maxZoom: 6,
        minZoom: 1
      }).addTo(map);
    }

    // Ensure proper sizing inside modals and flex containers
    setTimeout(() => {
      if (map) map.invalidateSize();
    }, 0);

    if (mapElement && typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(() => {
        if (map) map.invalidateSize();
      });
      resizeObserver.observe(mapElement);
    }
  }

  function zoomIn() {
    if (map) map.zoomIn();
  }

  function zoomOut() {
    if (map) map.zoomOut();
  }
</script>

<div class={`relative w-full ${heightClass} rounded-2xl overflow-hidden border border-slate-200/60 dark:border-slate-700/60 bg-slate-100 dark:bg-slate-800`}>
  <div bind:this={mapElement} class="w-full h-full"></div>
  <div class="absolute top-3 right-3 flex flex-col gap-2">
    <button
      type="button"
      onclick={zoomIn}
      aria-label={$_('common.zoom_in')}
      class="w-8 h-8 rounded-full bg-white/90 dark:bg-slate-900/80 text-slate-700 dark:text-slate-200 shadow border border-slate-200/70 dark:border-slate-700/70 flex items-center justify-center hover:bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
    >
      +
    </button>
    <button
      type="button"
      onclick={zoomOut}
      aria-label={$_('common.zoom_out')}
      class="w-8 h-8 rounded-full bg-white/90 dark:bg-slate-900/80 text-slate-700 dark:text-slate-200 shadow border border-slate-200/70 dark:border-slate-700/70 flex items-center justify-center hover:bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
    >
      −
    </button>
  </div>
</div>
