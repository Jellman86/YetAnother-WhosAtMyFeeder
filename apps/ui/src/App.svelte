<script lang="ts">
  import { onMount } from 'svelte';
  import Header from './lib/components/Header.svelte';
  import Footer from './lib/components/Footer.svelte';
  import Dashboard from './lib/pages/Dashboard.svelte';
  import Events from './lib/pages/Events.svelte';
  import Species from './lib/pages/Species.svelte';
  import Settings from './lib/pages/Settings.svelte';
  import { fetchEvents, type Detection } from './lib/api';
  import { theme } from './lib/stores/theme';

  // Maximum detections to keep in memory for Dashboard
  const MAX_DASHBOARD_DETECTIONS = 24;

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
  let totalDetectionsToday = $state(0);

  async function loadInitial() {
      try {
          // Load recent detections for dashboard
          detections = await fetchEvents({ limit: MAX_DASHBOARD_DETECTIONS });

          // Get today's count for stats
          const today = new Date().toISOString().split('T')[0];
          const todayEvents = await fetchEvents({ limit: 1000, startDate: today, endDate: today });
          totalDetectionsToday = todayEvents.length;
      } catch (e) {
          console.error(e);
      }
  }

  function connectSSE() {
      const evtSource = new EventSource('/api/sse');

      evtSource.onmessage = (event) => {
          try {
             const payload = JSON.parse(event.data);

             if (payload.type === 'connected') {
                 connected = true;
                 console.log("SSE Connected:", payload.message);
             } else if (payload.type === 'detection') {
                 const newDet = {
                     frigate_event: payload.data.frigate_event,
                     display_name: payload.data.display_name,
                     score: payload.data.score,
                     detection_time: payload.data.timestamp,
                     camera_name: payload.data.camera
                 };
                 // Add new detection and cap the array to prevent memory leak
                 detections = [newDet, ...detections].slice(0, MAX_DASHBOARD_DETECTIONS);
                 totalDetectionsToday++;
             }
          } catch (e) {
              console.error("SSE Parse Error", e);
          }
      };

      evtSource.onerror = (err) => {
          console.error("SSE Connection Error", err);
          connected = false;
          evtSource.close();
          // Reconnect with exponential backoff (max 30s)
          setTimeout(connectSSE, 5000);
      };
  }

  onMount(() => {
      const path = window.location.pathname;
      currentRoute = path === '' ? '/' : path;
      loadInitial();
      connectSSE();
  });

  function handleDeleteDetection(eventId: string) {
      detections = detections.filter(d => d.frigate_event !== eventId);
      if (totalDetectionsToday > 0) totalDetectionsToday--;
  }
</script>

<div class="min-h-screen flex flex-col bg-surface-light dark:bg-surface-dark text-slate-900 dark:text-white font-sans transition-colors duration-300">
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
  <main class="flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full">
      {#if currentRoute === '/' || currentRoute === ''}
          <Dashboard
              {detections}
              {totalDetectionsToday}
              ondelete={handleDeleteDetection}
              onnavigate={navigate}
          />
      {:else if currentRoute === '/events'}
          <Events />
      {:else if currentRoute === '/species'}
          <Species />
      {:else if currentRoute === '/settings'}
           <Settings />
      {/if}
  </main>

  <Footer />
</div>