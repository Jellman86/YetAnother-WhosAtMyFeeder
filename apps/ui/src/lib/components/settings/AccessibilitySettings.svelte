<script lang="ts">
    import { _, locale } from 'svelte-i18n';

    // Props
    let {
        highContrast = $bindable(false),
        dyslexiaFont = $bindable(false)
    }: {
        highContrast: boolean;
        dyslexiaFont: boolean;
    } = $props();

    // OpenDyslexic font only supports Latin characters
    // Only show the option for languages that use Latin script
    const latinLanguages = ['en', 'es', 'fr', 'de'];
    const showDyslexicFont = $derived(latinLanguages.includes($locale || 'en'));

    // Apply/remove classes when toggles change
    $effect(() => {
        if (highContrast) document.documentElement.classList.add('high-contrast');
        else document.documentElement.classList.remove('high-contrast');
    });

    $effect(() => {
        if (dyslexiaFont) document.documentElement.classList.add('font-dyslexic');
        else document.documentElement.classList.remove('font-dyslexic');
    });
</script>

<section class="bg-white dark:bg-slate-800/50 rounded-3xl border border-slate-200/80 dark:border-slate-700/50 p-8 shadow-sm backdrop-blur-md">
    <div class="flex items-center gap-3 mb-8">
        <div class="w-10 h-10 rounded-2xl bg-indigo-500/10 flex items-center justify-center text-indigo-600 dark:text-indigo-400">
            <span class="text-xl">♿</span>
        </div>
        <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.accessibility.title')}</h3>
    </div>

    <div class="space-y-6">
        <!-- High Contrast -->
        <div class="p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-700/50 flex items-center justify-between">
            <div id="high-contrast-label">
                <span class="block text-sm font-bold text-slate-900 dark:text-white">{$_('settings.accessibility.high_contrast')}</span>
                <span class="block text-[10px] text-slate-500 font-medium">{$_('settings.accessibility.high_contrast_desc')}</span>
            </div>
            <button
                role="switch"
                aria-checked={highContrast}
                aria-labelledby="high-contrast-label"
                onclick={() => highContrast = !highContrast}
                onkeydown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        highContrast = !highContrast;
                    }
                }}
                class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {highContrast ? 'bg-indigo-500' : 'bg-slate-300 dark:bg-slate-600'}"
            >
                <span class="sr-only">{$_('settings.accessibility.high_contrast')}</span>
                <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {highContrast ? 'translate-x-5' : 'translate-x-0'}"></span>
            </button>
        </div>

        <!-- Dyslexia Font (only for Latin-based languages) -->
        {#if showDyslexicFont}
            <div class="p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-700/50 flex items-center justify-between">
                <div id="dyslexia-font-label">
                    <span class="block text-sm font-bold text-slate-900 dark:text-white">{$_('settings.accessibility.dyslexia_font')}</span>
                    <span class="block text-[10px] text-slate-500 font-medium">{$_('settings.accessibility.dyslexia_font_desc')}</span>
                </div>
                <button
                    role="switch"
                    aria-checked={dyslexiaFont}
                    aria-labelledby="dyslexia-font-label"
                    onclick={() => dyslexiaFont = !dyslexiaFont}
                    onkeydown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            dyslexiaFont = !dyslexiaFont;
                        }
                    }}
                    class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {dyslexiaFont ? 'bg-indigo-500' : 'bg-slate-300 dark:bg-slate-600'}"
                >
                    <span class="sr-only">{$_('settings.accessibility.dyslexia_font')}</span>
                    <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {dyslexiaFont ? 'translate-x-5' : 'translate-x-0'}"></span>
                </button>
            </div>
        {/if}
    </div>
</section>
