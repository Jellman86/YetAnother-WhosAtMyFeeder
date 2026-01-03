<script lang="ts">
  import { onMount } from 'svelte';
  import Header from './lib/components/Header.svelte';
  import Footer from './lib/components/Footer.svelte';
  import Dashboard from './lib/pages/Dashboard.svelte';
  import Events from './lib/pages/Events.svelte';
  import Species from './lib/pages/Species.svelte';
  import Settings from './lib/pages/Settings.svelte';
  import { fetchEvents, fetchEventsCount, type Detection } from './lib/api';
  import { theme } from './lib/stores/theme';
  import { settingsStore } from './lib/stores/settings';
  import { detectionsStore } from './lib/stores/detections.svelte.ts';

  // Router state
  let currentRoute = $state('/');

  function navigate(path: string) {
      currentRoute = path;
      window.history.pushState(null, '', path);
  }

  // Handle back button and initial load
  onMount(() => {
      const handlePopState = () => {
          currentRoute = window.location.pathname;
      };
      window.addEventListener('popstate', handlePopState);

      const path = window.location.pathname;
      currentRoute = path === '' ? '/' : path;

      // Initialize theme and settings
      theme.init();
      settingsStore.load();
      detectionsStore.loadInitial();
      connectSSE();

      return () => {
          window.removeEventListener('popstate', handlePopState);
      };
  });

  function connectSSE() {
      const evtSource = new EventSource('/api/sse');

      evtSource.onmessage = (event) => {
          try {
             const payload = JSON.parse(event.data);

             if (payload.type === 'connected') {
                 detectionsStore.setConnected(true);
                 console.log("SSE Connected:", payload.message);
             } else if (payload.type === 'detection') {
                 const newDet: Detection = {
                     frigate_event: payload.data.frigate_event,
                     display_name: payload.data.display_name,
                     score: payload.data.score,
                     detection_time: payload.data.timestamp,
                     camera_name: payload.data.camera,
                     frigate_score: payload.data.frigate_score,
                     sub_label: payload.data.sub_label,
                     audio_confirmed: payload.data.audio_confirmed,
                     audio_species: payload.data.audio_species,
                     audio_score: payload.data.audio_score,
                     temperature: payload.data.temperature,
                     weather_condition: payload.data.weather_condition,
                     scientific_name: payload.data.scientific_name,
                     common_name: payload.data.common_name,
                     taxa_id: payload.data.taxa_id
                 };
                 detectionsStore.addDetection(newDet);
             } else if (payload.type === 'detection_updated') {
                 const updatedDet: Detection = {
                     frigate_event: payload.data.frigate_event,
                     display_name: payload.data.display_name,
                     score: payload.data.score,
                     detection_time: payload.data.timestamp,
                     camera_name: payload.data.camera,
                     frigate_score: payload.data.frigate_score,
                     sub_label: payload.data.sub_label,
                     is_hidden: payload.data.is_hidden,
                     audio_confirmed: payload.data.audio_confirmed,
                     audio_species: payload.data.audio_species,
                     audio_score: payload.data.audio_score,
                     temperature: payload.data.temperature,
                     weather_condition: payload.data.weather_condition,
                     scientific_name: payload.data.scientific_name,
                     common_name: payload.data.common_name,
                     taxa_id: payload.data.taxa_id
                 };
                 detectionsStore.updateDetection(updatedDet);
             } else if (payload.type === 'detection_deleted') {
                 detectionsStore.removeDetection(payload.data.frigate_event, payload.data.timestamp);
             }
          } catch (e) {
              console.error("SSE Parse Error", e);
          }
      };

      evtSource.onerror = (err) => {
          console.error("SSE Connection Error", err);
          detectionsStore.setConnected(false);
          evtSource.close();
          // Reconnect with exponential backoff (max 30s)
          setTimeout(connectSSE, 5000);
      };
  }
</script>

<div class="min-h-screen flex flex-col bg-surface-light dark:bg-surface-dark text-slate-900 dark:text-white font-sans transition-colors duration-300">
  <Header {currentRoute} onNavigate={navigate}>
      {#snippet status()}
          <div class="flex items-center gap-4">
              {#if $settingsStore?.audio_topic}
                  <div class="flex items-center gap-1.5 px-2 py-1 rounded-full bg-teal-500/10 border border-teal-500/20" title="Audio Analysis Active">
                      <span class="relative flex h-2 w-2">
                          <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-teal-400 opacity-75"></span>
                          <span class="relative inline-flex rounded-full h-2 w-2 bg-teal-500"></span>
                      </span>
                      <span class="text-[10px] font-bold text-teal-600 dark:text-teal-400 uppercase tracking-tight">Listening</span>
                  </div>
              {/if}

              <div class="flex items-center gap-2">
                  {#if detectionsStore.connected}
                      <span class="relative flex h-2.5 w-2.5">
                          <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                          <span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.8)]"></span>
                      </span>
                      <span class="text-[10px] font-bold text-emerald-600 dark:text-emerald-400 uppercase tracking-tight">Live</span>
                  {:else}
                      <span class="w-2.5 h-2.5 rounded-full bg-red-500"></span>
                      <span class="text-[10px] font-bold text-red-600 uppercase tracking-tight">Offline</span>
                  {/if}
              </div>
          </div>
      {/snippet}
  </Header>

  <!-- Main Content -->
  <main class="flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full">
      {#if currentRoute === '/' || currentRoute === ''}
          <Dashboard
              detections={detectionsStore.detections}
              totalDetectionsToday={detectionsStore.totalToday}
              ondelete={(id) => detectionsStore.removeDetection(id)}
              onhide={(id) => detectionsStore.removeDetection(id)}
              onnavigate={navigate}
          />
      {:else if currentRoute.startsWith('/events')}
          <Events />
      {:else if currentRoute.startsWith('/species')}
          <Species />
      {:else if currentRoute.startsWith('/settings')}
           <Settings />
      {/if}
  </main>

  <Footer />
</div>