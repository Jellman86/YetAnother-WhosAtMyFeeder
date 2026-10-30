import { lazyComponent } from '../app/lazy-component';

// Record dialogs and the video player arrive on first open, so no visitor downloads them
// (or the markdown renderer and media code inside them) before opening anything.
export const loadDetectionModal = lazyComponent(() => import('./DetectionModal.svelte'));
export const loadSpeciesDetailModal = lazyComponent(() => import('./SpeciesDetailModal.svelte'));
export const loadGardenCaptureModal = lazyComponent(() => import('./GardenCaptureModal.svelte'));
export const loadVideoPlayer = lazyComponent(() => import('./VideoPlayer.svelte'));
export const loadReviewQueueModal = lazyComponent(() => import('./ReviewQueueModal.svelte'));
