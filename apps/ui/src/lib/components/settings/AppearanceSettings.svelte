<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { Theme } from '../../stores/theme';
    import type { Layout } from '../../stores/layout';

    // Props
    let {
        currentTheme,
        currentLayout,
        currentLocale,
        setTheme,
        setLayout,
        setLanguage
    }: {
        currentTheme: Theme;
        currentLayout: Layout;
        currentLocale: string;
        setTheme: (theme: Theme) => void;
        setLayout: (layout: Layout) => void;
        setLanguage: (lang: string) => void;
    } = $props();
</script>

<section class="card-base rounded-3xl p-8 backdrop-blur-md">
    <div class="flex items-center gap-3 mb-8">
        <div class="w-10 h-10 rounded-2xl bg-pink-500/10 flex items-center justify-center text-pink-600 dark:text-pink-400">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01" /></svg>
        </div>
        <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('theme.title')}</h3>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
        <!-- Theme -->
        <div>
            <h4 class="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-4">{$_('theme.title')}</h4>
            <div class="grid grid-cols-3 gap-2">
                {#each [
                    { value: 'light', label: $_('theme.light'), icon: '☀️' },
                    { value: 'dark', label: $_('theme.dark'), icon: '🌙' },
                    { value: 'system', label: $_('theme.system'), icon: '💻' }
                ] as opt}
                    <button
                        onclick={() => setTheme(opt.value as Theme)}
                        aria-label="{$_('theme.select', { default: 'Select {theme} theme', theme: opt.label })}"
                        class="flex flex-col items-center gap-2 p-4 rounded-2xl border-2 transition-all
                            {currentTheme === opt.value
                                ? 'bg-teal-500 border-teal-500 text-white shadow-lg shadow-teal-500/20'
                                : 'bg-white dark:bg-slate-900/50 border-slate-100 dark:border-slate-700/50 text-slate-500 hover:border-teal-500/30'}"
                    >
                        <span class="text-2xl" aria-hidden="true">{opt.icon}</span>
                        <span class="text-[10px] font-black uppercase tracking-widest">{opt.label}</span>
                    </button>
                {/each}
            </div>
        </div>

        <!-- Language -->
        <div>
            <label for="language-select" class="block text-[10px] font-black uppercase tracking-widest text-slate-400 mb-4">{$_('settings.language_selector')}</label>
            <div class="grid grid-cols-1 gap-2">
                <select
                    id="language-select"
                    value={currentLocale}
                    onchange={(e) => setLanguage(e.currentTarget.value)}
                    aria-label="{$_('settings.language_selector')}"
                    class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none transition-all"
                >
                    <option value="en">English</option>
                    <option value="es">Español</option>
                    <option value="fr">Français</option>
                    <option value="de">Deutsch</option>
                    <option value="ja">日本語</option>
                    <option value="zh">中文</option>
                    <option value="ru">Русский</option>
                    <option value="pt">Português</option>
                    <option value="it">Italiano</option>
                </select>
                <p class="text-[9px] text-slate-400 font-bold italic mt-1">{$_('settings.language_desc')}</p>
            </div>
        </div>
    </div>

    <div class="pt-8 mt-8 border-t border-slate-100 dark:border-slate-700/50">
        <div class="flex items-center gap-3 mb-6">
            <div class="w-8 h-8 rounded-xl bg-purple-500/10 flex items-center justify-center text-purple-600 dark:text-purple-400">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" /></svg>
            </div>
            <h4 class="text-lg font-black text-slate-900 dark:text-white tracking-tight">{$_('theme.layout')}</h4>
        </div>

        <div class="grid grid-cols-2 gap-4">
            {#each [
                { value: 'horizontal', label: $_('theme.horizontal'), icon: '⬌', desc: $_('theme.horizontal_desc') },
                { value: 'vertical', label: $_('theme.vertical'), icon: '⇕', desc: $_('theme.vertical_desc') }
            ] as opt}
                <button
                    onclick={() => setLayout(opt.value as Layout)}
                    aria-label="{$_('theme.select_layout', { default: 'Select {layout} layout', layout: opt.label })}"
                    class="flex flex-col items-start gap-2 p-5 rounded-2xl border-2 transition-all text-left
                        {currentLayout === opt.value
                            ? 'bg-purple-500 border-purple-500 text-white shadow-xl shadow-purple-500/20'
                            : 'bg-white dark:bg-slate-900/50 border-slate-100 dark:border-slate-700/50 text-slate-500 hover:border-purple-500/30'}"
                >
                    <span class="text-2xl" aria-hidden="true">{opt.icon}</span>
                    <div>
                        <div class="text-sm font-black uppercase tracking-widest {currentLayout === opt.value ? 'text-white' : 'text-slate-900 dark:text-white'}">{opt.label}</div>
                        <div class="text-xs font-medium mt-1 {currentLayout === opt.value ? 'text-white/80' : 'text-slate-400'}">{opt.desc}</div>
                    </div>
                </button>
            {/each}
        </div>
    </div>
</section>
