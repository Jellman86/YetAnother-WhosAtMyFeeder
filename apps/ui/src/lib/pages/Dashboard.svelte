<script lang="ts">
    import DetectionCard from '../components/DetectionCard.svelte';
    import SpeciesDetailModal from '../components/SpeciesDetailModal.svelte';
    import type { Detection } from '../api';
    import { getThumbnailUrl, deleteDetection } from '../api';

    let { detections, ondelete } = $props<{ detections: Detection[], ondelete?: (eventId: string) => void }>();

    let selectedEvent = $state<Detection | null>(null);
    let selectedSpecies = $state<string | null>(null);
    let deleting = $state(false);

    async function handleDelete() {
        if (!selectedEvent) return;
        if (!confirm(`Delete this ${selectedEvent.display_name} detection?`)) return;

        deleting = true;
        try {
            await deleteDetection(selectedEvent.frigate_event);
            const eventId = selectedEvent.frigate_event;
            selectedEvent = null;
            ondelete?.(eventId);
        } catch (e) {
            console.error('Failed to delete detection', e);
            alert('Failed to delete detection');
        } finally {
            deleting = false;
        }
    }
</script>

<div class="mb-8">
    <h2 class="text-2xl font-bold mb-4 text-gray-900 dark:text-white">Live Detections</h2>
</div>

<div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
    {#each detections as detection (detection.frigate_event || detection.id)}
        <DetectionCard {detection} onclick={() => selectedEvent = detection} />
    {/each}

    {#if detections.length === 0}
        <div class="col-span-full text-center py-16 text-slate-500 dark:text-slate-400 bg-white/80 dark:bg-slate-800/50 rounded-2xl shadow-card dark:shadow-card-dark border border-slate-200/80 dark:border-slate-700/50 backdrop-blur-sm">
            <div class="flex flex-col items-center justify-center">
                <div class="w-16 h-16 mb-4 rounded-full bg-slate-100 dark:bg-slate-700/50 flex items-center justify-center">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8 text-slate-400 dark:text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                </div>
                <p class="text-lg font-semibold text-slate-700 dark:text-slate-300">No detections yet</p>
                <p class="text-sm mt-1">Waiting for birds to visit...</p>
            </div>
        </div>
    {/if}
</div>

<!-- Event Detail Modal -->
{#if selectedEvent}
    <div
        class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
        onclick={() => selectedEvent = null}
        role="dialog"
        aria-modal="true"
    >
        <div
            class="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-lg w-full overflow-hidden
                   border border-slate-200 dark:border-slate-700"
            onclick={(e) => e.stopPropagation()}
            role="document"
        >
            <!-- Image -->
            <div class="relative aspect-video bg-slate-100 dark:bg-slate-700">
                <img
                    src={getThumbnailUrl(selectedEvent.frigate_event)}
                    alt={selectedEvent.display_name}
                    class="w-full h-full object-cover"
                />
                <button
                    onclick={() => selectedEvent = null}
                    class="absolute top-3 right-3 w-8 h-8 rounded-full bg-black/50 text-white
                           flex items-center justify-center hover:bg-black/70 transition-colors"
                >
                    ✕
                </button>
            </div>

            <div class="p-6">
                <h3 class="text-2xl font-bold text-slate-900 dark:text-white mb-2">
                    {selectedEvent.display_name}
                </h3>

                <div class="grid grid-cols-2 gap-4 text-sm">
                    <div>
                        <span class="text-slate-500 dark:text-slate-400">Confidence</span>
                        <p class="font-semibold text-slate-900 dark:text-white">
                            {(selectedEvent.score * 100).toFixed(1)}%
                        </p>
                    </div>
                    <div>
                        <span class="text-slate-500 dark:text-slate-400">Camera</span>
                        <p class="font-semibold text-slate-900 dark:text-white">
                            {selectedEvent.camera_name}
                        </p>
                    </div>
                    <div>
                        <span class="text-slate-500 dark:text-slate-400">Date</span>
                        <p class="font-semibold text-slate-900 dark:text-white">
                            {new Date(selectedEvent.detection_time).toLocaleDateString()}
                        </p>
                    </div>
                    <div>
                        <span class="text-slate-500 dark:text-slate-400">Time</span>
                        <p class="font-semibold text-slate-900 dark:text-white">
                            {new Date(selectedEvent.detection_time).toLocaleTimeString()}
                        </p>
                    </div>
                </div>

                <div class="mt-4 flex gap-2">
                    <button
                        onclick={() => {
                            selectedSpecies = selectedEvent?.display_name ?? null;
                            selectedEvent = null;
                        }}
                        class="flex-1 px-4 py-2 text-sm font-medium text-teal-600 dark:text-teal-400
                               bg-teal-50 dark:bg-teal-900/20 rounded-lg
                               hover:bg-teal-100 dark:hover:bg-teal-900/40 transition-colors"
                    >
                        View Species Details
                    </button>
                    <button
                        onclick={handleDelete}
                        disabled={deleting}
                        class="px-4 py-2 text-sm font-medium text-red-600 dark:text-red-400
                               bg-red-50 dark:bg-red-900/20 rounded-lg
                               hover:bg-red-100 dark:hover:bg-red-900/40 transition-colors
                               disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        {deleting ? 'Deleting...' : 'Delete'}
                    </button>
                </div>
            </div>
        </div>
    </div>
{/if}

<!-- Species Detail Modal -->
{#if selectedSpecies}
    <SpeciesDetailModal
        speciesName={selectedSpecies}
        onclose={() => selectedSpecies = null}
    />
{/if}
