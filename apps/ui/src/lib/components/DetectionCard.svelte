<script lang="ts">
    import type { Detection } from '../api';
    import { getThumbnailUrl } from '../api';
    import { detectionsStore } from '../stores/detections.svelte';
    import { settingsStore } from '../stores/settings';
    import ReclassificationOverlay from './ReclassificationOverlay.svelte';

    interface Props {
        detection: Detection;
        onclick?: () => void;
        onReclassify?: (detection: Detection) => void;
        onRetag?: (detection: Detection) => void;
        hideProgress?: boolean;
    }

    let { detection, onclick, onReclassify, onRetag, hideProgress = false }: Props = $props();

    // Check if this detection is being reclassified
    let reclassifyProgress = $derived(!hideProgress ? detectionsStore.getReclassificationProgress(detection.frigate_event) : null);

    let imageError = $state(false);
    let imageLoaded = $state(false);
    let cardElement = $state<HTMLElement | null>(null);
    let isVisible = $state(false);

    function handleReclassifyClick(event: MouseEvent) {
        event.stopPropagation();
        onReclassify?.(detection);
    }

    function handleRetagClick(event: MouseEvent) {
        event.stopPropagation();
        onRetag?.(detection);
    }

    // Lazy load with intersection observer
    $effect(() => {
        if (!cardElement) return;
        const observer = new IntersectionObserver(
            (entries) => {
                if (entries[0].isIntersecting) {
                    isVisible = true;
                    observer.disconnect();
                }
            },
            { rootMargin: '100px' }
        );
        observer.observe(cardElement);
        return () => observer.disconnect();
    });

    function formatTime(dateString: string): string {
        try {
            const date = new Date(dateString);
            return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } catch {
            return '';
        }
    }

    function formatDate(dateString: string): string {
        try {
            const date = new Date(dateString);
            const today = new Date();
            const yesterday = new Date(today);
            yesterday.setDate(yesterday.getDate() - 1);
            if (date.toDateString() === today.toDateString()) {
                return 'Today';
            } else if (date.toDateString() === yesterday.toDateString()) {
                return 'Yesterday';
            }
            return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
        } catch {
            return '';
        }
    }

    function getConfidenceColor(score: number): string {
        if (score >= 0.9) return 'text-emerald-500';
        if (score >= 0.7) return 'text-amber-500';
        return 'text-red-500';
    }

    function getConfidenceBg(score: number): string {
        if (score >= 0.9) return 'border-emerald-500/30';
        if (score >= 0.7) return 'border-amber-500/30';
        return 'border-red-500/30';
    }

    // Dynamic Naming Logic
    let naming = $derived.by(() => {
        const settings = $settingsStore;
        const showCommon = settings?.display_common_names ?? true;
        const preferSci = settings?.scientific_name_primary ?? false;

        let primary: string;
        let secondary: string | null = null;

        if (!showCommon) {
            primary = (detection.scientific_name || detection.display_name) as string;
            secondary = null;
        } else if (preferSci) {
            primary = (detection.scientific_name || detection.display_name) as string;
            secondary = (detection.common_name || null) as string | null;
        } else {
            primary = (detection.common_name || detection.display_name) as string;
            secondary = (detection.scientific_name || null) as string | null;
        }

        return {
            primary,
            secondary: (secondary && secondary !== primary) ? secondary : null
        };
    });

    let primaryName = $derived(naming.primary);
    let subName = $derived(naming.secondary);

    let isVerified = $derived(detection.audio_confirmed && detection.score > 0.7);
</script>

<div
    role="button"
    tabindex="0"
    bind:this={cardElement}
    onclick={onclick}
    onkeydown={(e) => (e.key === 'Enter' || e.key === ' ') && onclick?.()}
    class="group relative bg-white dark:bg-slate-800 rounded-3xl
           shadow-sm hover:shadow-card-hover dark:hover:shadow-card-dark-hover
           border border-slate-200/80 dark:border-slate-700/50
           hover:border-teal-500/30 dark:hover:border-teal-500/20
           overflow-hidden transition-all duration-500 ease-out
           hover:-translate-y-1.5 flex flex-col h-full
           text-left w-full cursor-pointer
           focus:outline-none focus:ring-2 focus:ring-teal-500/50
           {detection.is_hidden ? 'opacity-60 grayscale-[0.5]' : ''}
           {isVerified ? 'ring-2 ring-emerald-500/20 dark:ring-emerald-500/10' : ''}"
>
    <!-- Reclassification Overlay -->
    {#if reclassifyProgress}
        <ReclassificationOverlay progress={reclassifyProgress} />
    {/if}

    <!-- Image Section -->
    <div class="relative aspect-[4/3] overflow-hidden">
        {#if !imageError && isVisible}
            {#if !imageLoaded}
                <div class="absolute inset-0 bg-slate-100 dark:bg-slate-800 animate-shimmer bg-[length:200%_100%] bg-gradient-to-r from-transparent via-slate-200/10 to-transparent"></div>
            {/if}
            <img
                src={getThumbnailUrl(detection.frigate_event)}
                alt={primaryName}
                loading="lazy"
                class="w-full h-full object-cover transition-transform duration-700 ease-out
                       group-hover:scale-110 group-hover:rotate-1
                       {imageLoaded ? 'opacity-100' : 'opacity-0'}"
                onload={() => imageLoaded = true}
                onerror={() => imageError = true}
            />
            <div class="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-black/20 opacity-60"></div>
            <div class="absolute inset-0 bg-teal-500/5 opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
        {:else}
            <div class="absolute inset-0 flex items-center justify-center bg-slate-100 dark:bg-slate-800">
                <svg class="w-12 h-12 text-slate-300 dark:text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
            </div>
        {/if}
        <div class="absolute top-3 left-3 right-3 flex justify-between items-start">
            <div class="flex flex-col gap-1.5">
                {#if isVerified}
                    <div class="flex items-center gap-1 px-2.5 py-1 rounded-full bg-emerald-500 text-white text-[10px] font-black uppercase tracking-wider shadow-lg shadow-emerald-500/40 animate-fade-in">
                        <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M6.267 3.455a3.066 3.066 0 001.745-.723 3.066 3.066 0 013.976 0 3.066 3.066 0 001.745.723 3.066 3.066 0 012.812 2.812c.051.64.304 1.24.723 1.745a3.066 3.066 0 010 3.976 3.066 3.066 0 00-.723 1.745 3.066 3.066 0 01-2.812 2.812 3.066 3.066 0 00-1.745.723 3.066 3.066 0 01-3.976 0 3.066 3.066 0 00-1.745-.723 3.066 3.066 0 01-2.812-2.812 3.066 3.066 0 00-.723-1.745 3.066 3.066 0 010-3.976 3.066 3.066 0 00.723-1.745 3.066 3.066 0 012.812-2.812zm7.44 5.252a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
                        </svg>
                        Verified
                    </div>
                {/if}
                {#if detection.is_hidden}
                    <div class="px-2 py-1 rounded-full bg-amber-500 text-white text-[10px] font-bold uppercase tracking-wider shadow-lg">
                        Hidden
                    </div>
                {/if}
            </div>
            <div class="flex flex-col items-end gap-1.5">
                <div class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-2xl bg-white/95 dark:bg-slate-900/95 shadow-xl backdrop-blur-md border {getConfidenceBg(detection.score)}">
                    <span class="w-2 h-2 rounded-full {detection.score >= 0.9 ? 'bg-emerald-500 animate-pulse' : detection.score >= 0.7 ? 'bg-amber-500' : 'bg-red-500'}"></span>
                    <span class="text-xs font-black {getConfidenceColor(detection.score)} leading-none">{(detection.score * 100).toFixed(0)}%</span>
                </div>
                {#if detection.frigate_score !== undefined && detection.frigate_score !== null}
                    <div class="px-2 py-1 rounded-lg bg-black/40 text-white/90 text-[9px] font-bold backdrop-blur-sm tracking-tight border border-white/5">
                        FRIGATE: {(detection.frigate_score * 100).toFixed(0)}%
                    </div>
                {/if}
            </div>
        </div>
        <div class="absolute bottom-3 left-3 flex items-center gap-2">
            <div class="px-2.5 py-1.5 rounded-xl bg-black/40 text-white text-[10px] font-bold backdrop-blur-md border border-white/10 flex items-center gap-1.5">
                <svg class="w-3 h-3 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                {formatTime(detection.detection_time)}
            </div>
        </div>
        {#if onReclassify || onRetag}
            <div class="absolute bottom-3 right-3 flex gap-2 opacity-0 group-hover:opacity-100 transition-all duration-300 translate-y-2 group-hover:translate-y-0">
                {#if onReclassify}
                    <button
                        onclick={handleReclassifyClick}
                        class="w-9 h-9 rounded-xl bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200
                               hover:bg-teal-500 hover:text-white transition-all duration-200
                               flex items-center justify-center shadow-2xl border border-slate-200/50 dark:border-slate-700/50"
                        title="Deep Reclassify"
                    >
                        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                        </svg>
                    </button>
                {/if}
                {#if onRetag}
                    <button
                        onclick={handleRetagClick}
                        class="w-9 h-9 rounded-xl bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200
                               hover:bg-amber-500 hover:text-white transition-all duration-200
                               flex items-center justify-center shadow-2xl border border-slate-200/50 dark:border-slate-700/50"
                        title="Manual Tag"
                    >
                        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
                        </svg>
                    </button>
                {/if}
            </div>
        {/if}
    </div>
    <div class="p-5 flex-1 flex flex-col gap-4">
        <div>
            <div class="flex items-center justify-between gap-2">
                <h3 class="text-xl font-black text-slate-900 dark:text-white truncate tracking-tight leading-tight" title={primaryName}>
                    {primaryName}
                </h3>
            </div>
            {#if subName}
                <p class="text-xs italic text-slate-500 dark:text-slate-400 font-medium mt-0.5 truncate opacity-80">
                    {subName}
                </p>
            {/if}
        </div>
        {#if (detection.audio_species || detection.audio_confirmed) && (detection.audio_score !== undefined && detection.audio_score !== null)}
            <div class="p-3 rounded-2xl bg-teal-500/5 dark:bg-teal-500/10 border border-teal-500/10 dark:border-teal-500/20 flex items-center gap-3 group/audio">
                <div class="w-8 h-8 rounded-xl bg-teal-500/20 flex items-center justify-center flex-shrink-0">
                    <svg class="w-4 h-4 text-teal-600 dark:text-teal-400 {detection.audio_confirmed ? 'animate-pulse-slow' : ''}" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                    </svg>
                </div>
                <div class="min-w-0">
                    <p class="text-[10px] font-black uppercase tracking-widest text-teal-600/70 dark:text-teal-400/70 mb-0.5">Audio Match</p>
                    <p class="text-xs font-bold text-slate-700 dark:text-slate-200 truncate">
                        {detection.audio_species || 'BirdNET Confirmed'}
                        {#if detection.audio_score}
                            <span class="ml-1 opacity-60">({(detection.audio_score * 100).toFixed(0)}%)</span>
                        {/if}
                    </p>
                </div>
            </div>
        {/if}
        <div class="mt-auto grid grid-cols-2 gap-2">
            <div class="flex items-center gap-2 px-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-900/40 border border-slate-200/50 dark:border-slate-700/50">
                <svg class="w-3.5 h-3.5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
                <span class="text-[10px] font-bold text-slate-600 dark:text-slate-400 whitespace-nowrap">
                    {formatDate(detection.detection_time)}
                </span>
            </div>
            {#if detection.temperature !== undefined && detection.temperature !== null}
                <div class="flex items-center gap-2 px-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-900/40 border border-slate-200/50 dark:border-slate-700/50">
                    <svg class="w-3.5 h-3.5 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                    </svg>
                    <span class="text-[10px] font-black text-slate-700 dark:text-slate-300">
                        {detection.temperature?.toFixed(1)}°C
                    </span>
                </div>
            {/if}
            <div class="col-span-2 flex items-center gap-2 px-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-900/40 border border-slate-200/50 dark:border-slate-700/50 overflow-hidden">
                <svg class="w-3.5 h-3.5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                </svg>
                <span class="text-[10px] font-bold text-slate-500 dark:text-slate-400 truncate">
                    {detection.camera_name}
                </span>
                {#if detection.sub_label && detection.sub_label !== detection.display_name && detection.sub_label !== subName}
                    <div class="ml-auto flex items-center gap-1">
                        <div class="w-1 h-1 rounded-full bg-teal-500"></div>
                        <span class="text-[9px] font-black text-teal-600 uppercase tracking-tighter">Frigate Verified</span>
                    </div>
                {/if}
            </div>
        </div>
    </div>
</div>