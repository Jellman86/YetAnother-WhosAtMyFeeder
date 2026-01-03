<script lang="ts">
    import type { Detection } from '../api';
    import { getThumbnailUrl } from '../api';

    interface Props {
        detection: Detection;
        onclick?: () => void;
        onReclassify?: (detection: Detection) => void;
        onRetag?: (detection: Detection) => void;
    }

    let { detection, onclick, onReclassify, onRetag }: Props = $props();

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

    // Content
    let subName = $derived.by(() => {
        if (!detection.scientific_name && !detection.common_name) return null;
        
        const other = detection.display_name === detection.common_name 
            ? detection.scientific_name 
            : detection.common_name;
            
        return (other && other !== detection.display_name) ? other : null;
    });
</script>

<div
    role="button"
    tabindex="0"
    bind:this={cardElement}
    onclick={onclick}
    onkeydown={(e) => (e.key === 'Enter' || e.key === ' ') && onclick?.()}
    class="group relative bg-white dark:bg-slate-800 rounded-2xl
           shadow-sm dark:shadow-md
           hover:shadow-[0_12px_40px_-8px_rgba(20,184,166,0.2)]
           dark:hover:shadow-[0_12px_40px_-8px_rgba(20,184,166,0.15)]
           border border-slate-200/80 dark:border-slate-700/50
           hover:border-teal-400/50 dark:hover:border-teal-500/40
           overflow-hidden transition-all duration-300 ease-out
           hover:-translate-y-1
           text-left w-full cursor-pointer
           focus:outline-none focus:ring-2 focus:ring-teal-500/50 focus:ring-offset-2 dark:focus:ring-offset-slate-900
           {detection.is_hidden ? 'opacity-60 hover:opacity-90 border-amber-300 dark:border-amber-700' : ''}"
>
    <!-- Image Container -->
    <div class="relative aspect-[4/3] bg-slate-100 dark:bg-slate-700 overflow-hidden">
        {#if !imageError && isVisible}
            <!-- Skeleton while loading -->
            {#if !imageLoaded}
                <div class="absolute inset-0 bg-slate-200 dark:bg-slate-700 animate-pulse"></div>
            {/if}
            <img
                src={getThumbnailUrl(detection.frigate_event)}
                alt={detection.display_name}
                loading="lazy"
                class="w-full h-full object-cover transition-transform duration-500 ease-out
                       group-hover:scale-105
                       {imageLoaded ? 'opacity-100' : 'opacity-0'}"
                onload={() => imageLoaded = true}
                onerror={() => imageError = true}
            />
            <!-- Gradient overlay on hover -->
            <div class="absolute inset-0 bg-gradient-to-br from-teal-500/10 via-transparent to-emerald-500/10
                        opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none"></div>
        {:else if imageError}
            <div class="absolute inset-0 flex items-center justify-center text-4xl bg-slate-50 dark:bg-slate-700">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-12 h-12 text-slate-300 dark:text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
            </div>
        {:else}
            <!-- Placeholder before visible -->
            <div class="absolute inset-0 bg-slate-100 dark:bg-slate-700"></div>
        {/if}

        <!-- Confidence Badge -->
        <div class="absolute top-2 right-2 flex flex-col items-end gap-1">
            <div class="relative">
                {#if detection.score >= 0.9}
                    <div class="absolute inset-0 rounded-full bg-emerald-500/50 animate-ping"></div>
                {/if}
                <div class="relative flex items-center gap-1.5 px-2.5 py-1.5 rounded-full
                            bg-slate-900 text-white text-xs font-bold shadow-lg">
                    <span class="w-2 h-2 rounded-full {getConfidenceColor(detection.score)}"></span>
                    {(detection.score * 100).toFixed(0)}%
                </div>
            </div>
            {#if detection.frigate_score}
                <div class="flex items-center gap-1 px-2 py-1 rounded-full
                            bg-slate-800 text-white/80 text-[10px] font-medium"
                     title="Frigate Detection Confidence">
                    F: {(detection.frigate_score * 100).toFixed(0)}%
                </div>
            {/if}
        </div>

        <!-- Hidden Badge -->
        {#if detection.is_hidden}
            <div class="absolute top-2 left-2 flex items-center gap-1 px-2 py-1 rounded-full
                        bg-amber-500 text-white text-xs font-medium">
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                          d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                </svg>
                Hidden
            </div>
        {/if}

        <!-- Camera Badge -->
        <div class="absolute bottom-2 left-2 flex gap-1">
            <div class="px-2 py-1 rounded-full bg-slate-900/90 text-white text-xs flex items-center gap-1">
                📷 {detection.camera_name}
            </div>
            
            {#if detection.audio_confirmed}
                <div class="px-2 py-1 rounded-full bg-teal-600 text-white text-xs flex items-center gap-1"
                     title="Audio: {detection.audio_species || detection.display_name}{detection.audio_score ? ` (${(detection.audio_score * 100).toFixed(0)}%)` : ''}">
                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                              d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                    </svg>
                    {#if detection.audio_species && detection.audio_species !== detection.display_name}
                        <span class="truncate max-w-[60px]">{detection.audio_species}</span>
                    {:else if detection.audio_score}
                        {(detection.audio_score * 100).toFixed(0)}%
                    {/if}
                </div>
            {/if}
        </div>

        <!-- Action Buttons Overlay (bottom-right) -->
        {#if onReclassify || onRetag}
            <div class="absolute bottom-2 right-2 flex gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                {#if onReclassify}
                    <button
                        type="button"
                        onclick={handleReclassifyClick}
                        class="w-8 h-8 rounded-full bg-slate-900 text-white
                               hover:bg-teal-500 transition-colors duration-150
                               flex items-center justify-center shadow-lg"
                        title="Re-run bird classifier"
                    >
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                        </svg>
                    </button>
                {/if}
                {#if onRetag}
                    <button
                        type="button"
                        onclick={handleRetagClick}
                        class="w-8 h-8 rounded-full bg-slate-900 text-white
                               hover:bg-amber-500 transition-colors duration-150
                               flex items-center justify-center shadow-lg"
                        title="Manual retag"
                    >
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                  d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
                        </svg>
                    </button>
                {/if}
            </div>
        {/if}
    </div>

    <!-- Content -->
    <div class="p-4">
        <h3 class="text-lg font-semibold text-slate-900 dark:text-white truncate"
            title={detection.display_name}>
            {detection.display_name}
        </h3>
        
        {#if subName}
            <p class="text-xs italic text-slate-500 dark:text-slate-400 mt-0.5 truncate" title={subName}>
                {subName}
            </p>
        {/if}
        
        {#if detection.sub_label && detection.sub_label !== detection.display_name && detection.sub_label !== subName}
            <p class="text-[10px] font-medium text-teal-600 dark:text-teal-400 mt-1 truncate" title="Frigate sub-label: {detection.sub_label}">
                Frigate: {detection.sub_label}
            </p>
        {:else if detection.sub_label && !subName}
            <p class="text-[10px] text-slate-400 dark:text-slate-500 mt-1 italic">
                Confirmed by Frigate
            </p>
        {:else if !subName}
            <div class="h-4"></div> <!-- Spacer to keep layout consistent -->
        {/if}

        <div class="flex items-center justify-between text-sm text-slate-500 dark:text-slate-400 mt-3">
            <div class="flex flex-col">
                <span>{formatDate(detection.detection_time)}</span>
                <span class="text-[10px] opacity-70">{formatTime(detection.detection_time)}</span>
            </div>
            
            {#if detection.temperature !== undefined && detection.temperature !== null}
                <div class="flex flex-col items-end">
                    <span class="font-medium text-slate-700 dark:text-slate-300">{detection.temperature.toFixed(1)}°C</span>
                    {#if detection.weather_condition}
                        <span class="text-[10px] opacity-70 truncate max-w-[80px]">{detection.weather_condition}</span>
                    {/if}
                </div>
            {/if}
        </div>
    </div>
</div>