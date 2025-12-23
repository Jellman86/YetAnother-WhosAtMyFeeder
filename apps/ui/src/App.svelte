<script lang="ts">
  import { onMount } from 'svelte';
  import Header from './lib/components/Header.svelte';
  import Dashboard from './lib/pages/Dashboard.svelte';
  import Events from './lib/pages/Events.svelte';
  import Species from './lib/pages/Species.svelte';
  import Settings from './lib/pages/Settings.svelte';
  import { fetchEvents, type Detection } from './lib/api';
  import { theme } from './lib/stores/theme';

  // Router state
  let currentRoute = $state('/');

  function navigate(path: string) {
      currentRoute = path;
      window.history.pushState(null, '', path);
  }

  // Handle back button
  onMount(() => {
      const handlePopState = () => {
          currentRoute = window.location.pathname;
      };
      window.addEventListener('popstate', handlePopState);
      
      // Initialize theme
      theme.init();

      return () => window.removeEventListener('popstate', handlePopState);
  });
  
  // Dashboard Logic
  let detections: Detection[] = $state([]);
  let connected = $state(false);

  async function loadInitial() {
      try {
          detections = await fetchEvents();
      } catch (e) {
          console.error(e);
      }
  }

  function connectSSE() {
      const evtSource = new EventSource('/api/sse');
      
      evtSource.onopen = () => {
          connected = true;
          console.log("SSE Connected");
      };

      evtSource.onmessage = (event) => {
          try {
             const payload = JSON.parse(event.data);
             if (payload.type === 'detection') {
                 const newDet = {
                     frigate_event: payload.data.frigate_event,
                     display_name: payload.data.display_name,
                     score: payload.data.score,
                     detection_time: payload.data.timestamp,
                     camera_name: payload.data.camera
                 };
                 detections = [newDet, ...detections];
             }
          } catch (e) {
              console.error("SSE Error", e);
          }
      };

      evtSource.onerror = (err) => {
          console.error("SSE Connection Error", err);
          connected = false;
          evtSource.close();
          setTimeout(connectSSE, 5000);
      };
  }

  onMount(() => {
      const path = window.location.pathname;
      currentRoute = path === '' ? '/' : path;
      loadInitial();
      connectSSE();
  });
</script>

<div class="min-h-screen bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white font-sans transition-colors duration-200">
  <Header {currentRoute} onNavigate={navigate}>
      {#snippet status()}
          {#if connected}
              <span class="w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)] animate-pulse" title="Live"></span>
          {:else}
              <span class="w-2.5 h-2.5 rounded-full bg-red-500" title="Disconnected"></span>
          {/if}
      {/snippet}
  </Header>

  <!-- Main Content -->
  <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {#if currentRoute === '/' || currentRoute === ''}
          <Dashboard {detections} />
      {:else if currentRoute === '/events'}
          <Events />
      {:else if currentRoute === '/species'}
          <Species />
      {:else if currentRoute === '/settings'}
           <Settings />
      {/if}
  </main>
</div>