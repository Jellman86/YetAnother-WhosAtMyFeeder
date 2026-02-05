<script lang="ts">
  import { onMount } from 'svelte';
  import { settingsStore } from '../stores/settings.svelte';
  import { updateSettings } from '../api';

  const DISMISSED_KEY = 'telemetry-banner-dismissed';

  let isDismissed = $state(true); // Start as dismissed, check in onMount
  let isEnabling = $state(false);

  onMount(() => {
    // Check if banner was previously dismissed
    const wasDismissed = localStorage.getItem(DISMISSED_KEY) === 'true';

    // Show banner if:
    // 1. Not previously dismissed
    // 2. Settings are loaded
    // 3. Telemetry is disabled
    if (!wasDismissed && settingsStore.settings && !settingsStore.settings.telemetry_enabled) {
      isDismissed = false;
    }
  });

  function dismiss() {
    isDismissed = true;
    localStorage.setItem(DISMISSED_KEY, 'true');
  }

  async function enableTelemetry() {
    if (!settingsStore.settings) return;

    isEnabling = true;
    try {
      await updateSettings({ telemetry_enabled: true });
      await settingsStore.load(); // Reload to get updated value
      dismiss();
    } catch (error) {
      console.error('Failed to enable telemetry:', error);
      alert('Failed to enable telemetry. Please try again from Settings.');
    } finally {
      isEnabling = false;
    }
  }

  function openDocs() {
    window.open('https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/blob/main/docs/TELEMETRY_SPEC.md', '_blank');
  }
</script>

{#if !isDismissed}
  <div class="bg-gradient-to-r from-teal-50 via-emerald-50 to-white dark:from-teal-950/30 dark:via-emerald-950/20 dark:to-slate-950/40 border-b border-teal-200/60 dark:border-teal-900/40">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3">
      <div class="flex items-start gap-3">
        <!-- Icon -->
        <div class="flex-shrink-0 mt-0.5">
          <svg class="w-5 h-5 text-teal-600 dark:text-teal-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>

        <!-- Content -->
        <div class="flex-1 min-w-0">
          <p class="text-sm text-slate-700 dark:text-slate-300">
            <span class="font-semibold">Help improve YA-WAMF!</span>
            <span class="ml-1">Enable anonymous usage stats to guide development priorities and validate that this project serves the bird enthusiast community.</span>
            <button
              onclick={openDocs}
              class="ml-1 text-teal-700 dark:text-teal-300 hover:text-emerald-700 dark:hover:text-emerald-300 underline font-medium"
            >
              Learn more
            </button>
          </p>
        </div>

        <!-- Actions -->
        <div class="flex items-center gap-2 flex-shrink-0">
          <button
            onclick={enableTelemetry}
            disabled={isEnabling}
            class="btn btn-primary px-4 py-1.5 text-sm"
          >
            {isEnabling ? 'Enabling...' : 'Enable'}
          </button>
          <button
            onclick={dismiss}
            class="btn btn-ghost px-3 py-1.5 text-sm text-slate-600 dark:text-slate-300"
            title="Dismiss"
          >
            No Thanks
          </button>
        </div>
      </div>
    </div>
  </div>
{/if}
