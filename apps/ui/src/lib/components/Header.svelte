<script lang="ts">
    import { theme, isDark } from '../stores/theme';

    let { currentRoute, onNavigate, status } = $props<{
        currentRoute: string;
        onNavigate: (path: string) => void;
        status?: import('svelte').Snippet;
    }>();

    let mobileMenuOpen = $state(false);

    const navItems = [
        { path: '/', label: 'Dashboard', icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6' },
        { path: '/events', label: 'Explorer', icon: 'M4 6h16M4 10h16M4 14h16M4 18h16' },
        { path: '/species', label: 'Leaderboard', icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z' },
        { path: '/settings', label: 'Settings', icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z' },
        { path: '/about', label: 'About', icon: 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z' },
    ];

    function handleNavClick(path: string) {
        onNavigate(path);
        mobileMenuOpen = false;
    }
</script>

<header class="bg-white/90 dark:bg-slate-900/90 shadow-sm sticky top-0 z-50 backdrop-blur-xl border-b border-slate-200/80 dark:border-slate-700/50 transition-all duration-300 before:absolute before:inset-x-0 before:top-0 before:h-0.5 before:bg-gradient-to-r before:from-brand-500/50 before:via-teal-400/50 before:to-brand-500/50">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="h-16 flex items-center justify-between">
            <!-- Logo -->
            <button
                class="flex items-center gap-3 focus-ring rounded-lg p-1 -m-1"
                onclick={() => handleNavClick('/')}
            >
                <div class="w-9 h-9 rounded-xl bg-gradient-to-br from-brand-500 to-teal-400 flex items-center justify-center shadow-glow">
                    <span class="text-white text-lg">🐦</span>
                </div>
                <div class="flex flex-col">
                    <h1 class="text-lg font-bold text-gradient leading-tight hidden sm:block">
                        Yet Another
                    </h1>
                    <span class="text-sm font-semibold text-slate-600 dark:text-slate-300 hidden sm:block">
                        WhosAtMyFeeder
                    </span>
                    <span class="text-base font-bold text-gradient sm:hidden">YA-WAMF</span>
                </div>
                <div class="flex items-center ml-2">
                    {@render status?.()}
                </div>
            </button>

            <!-- Desktop Navigation -->
            <nav class="hidden md:flex items-center gap-1">
                {#each navItems as item}
                    <button
                        class="px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 focus-ring
                               {currentRoute === item.path
                                   ? 'bg-brand-50 dark:bg-brand-900/30 text-brand-700 dark:text-brand-300'
                                   : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-white'}"
                        onclick={() => handleNavClick(item.path)}
                    >
                        {item.label}
                    </button>
                {/each}
            </nav>

            <!-- Right side controls -->
            <div class="flex items-center gap-2">
                <!-- Theme toggle -->
                <button
                    class="p-2.5 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 dark:text-slate-400
                           transition-all duration-200 focus-ring"
                    onclick={() => theme.toggle()}
                    title={$isDark ? 'Switch to light mode' : 'Switch to dark mode'}
                >
                    {#if $isDark}
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                        </svg>
                    {:else}
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                        </svg>
                    {/if}
                </button>

                <!-- Mobile menu button -->
                <button
                    class="md:hidden p-2.5 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 dark:text-slate-400
                           transition-all duration-200 focus-ring"
                    onclick={() => mobileMenuOpen = !mobileMenuOpen}
                    aria-expanded={mobileMenuOpen}
                    aria-label="Toggle menu"
                >
                    {#if mobileMenuOpen}
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    {:else}
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M4 12h16M4 18h16" />
                        </svg>
                    {/if}
                </button>
            </div>
        </div>
    </div>

    <!-- Mobile Navigation Menu -->
    {#if mobileMenuOpen}
        <div class="md:hidden border-t border-slate-200/80 dark:border-slate-700/50 bg-white/95 dark:bg-slate-900/95 backdrop-blur-xl">
            <nav class="px-4 py-3 space-y-1">
                {#each navItems as item}
                    <button
                        class="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-left font-medium transition-all duration-200
                               {currentRoute === item.path
                                   ? 'bg-brand-50 dark:bg-brand-900/30 text-brand-700 dark:text-brand-300'
                                   : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'}"
                        onclick={() => handleNavClick(item.path)}
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                            <path stroke-linecap="round" stroke-linejoin="round" d={item.icon} />
                        </svg>
                        {item.label}
                    </button>
                {/each}
            </nav>
        </div>
    {/if}
</header>
