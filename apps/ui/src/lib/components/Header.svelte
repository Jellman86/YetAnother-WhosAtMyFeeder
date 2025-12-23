<script lang="ts">
    import { theme } from '../stores/theme';
    
    let { currentRoute, onNavigate, status } = $props<{ 
        currentRoute: string; 
        onNavigate: (path: string) => void;
        status?: import('svelte').Snippet;
    }>();

    let connected = $state(false); // This will need to be passed in or handled via a store later, simpler to pass as prop for now? 
    // Actually, App.svelte manages connection state. Let's add that as a prop.
</script>

<header class="bg-white dark:bg-gray-800 shadow-sm sticky top-0 z-10 backdrop-blur-md bg-opacity-90 dark:bg-opacity-90 transition-colors duration-200">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div class="flex items-center gap-3 cursor-pointer" onclick={() => onNavigate('/')} onkeydown={(e) => e.key === 'Enter' && onNavigate('/')} role="button" tabindex="0">
            <h1 class="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-500 to-teal-400">
                WhosAtMyFeeder
            </h1>
            <div class="flex items-center">
                 {@render status?.()}
            </div>
        </div>
        
        <div class="flex items-center gap-6">
            <nav class="hidden md:flex gap-6">
                <button 
                    class="text-sm font-medium transition-colors hover:text-blue-500 {currentRoute === '/' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-600 dark:text-gray-300'}" 
                    onclick={() => onNavigate('/')}
                >
                    Dashboard
                </button>
                <button 
                    class="text-sm font-medium transition-colors hover:text-blue-500 {currentRoute === '/events' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-600 dark:text-gray-300'}" 
                    onclick={() => onNavigate('/events')}
                >
                    Explorer
                </button>
                <button 
                    class="text-sm font-medium transition-colors hover:text-blue-500 {currentRoute === '/species' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-600 dark:text-gray-300'}" 
                    onclick={() => onNavigate('/species')}
                >
                    Leaderboard
                </button>
                <button 
                    class="text-sm font-medium transition-colors hover:text-blue-500 {currentRoute === '/settings' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-600 dark:text-gray-300'}" 
                    onclick={() => onNavigate('/settings')}
                >
                    Settings
                </button>
            </nav>

            <div class="flex items-center gap-2 border-l border-gray-200 dark:border-gray-700 pl-6">
                <button 
                    class="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400 transition-colors"
                    onclick={() => theme.set($theme === 'dark' ? 'light' : 'dark')}
                    title="Toggle Theme"
                >
                    {#if $theme === 'dark'}
                        <!-- Sun Icon -->
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                        </svg>
                    {:else}
                        <!-- Moon Icon -->
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                        </svg>
                    {/if}
                </button>
            </div>
            
            <!-- Mobile Menu Button (simplified for now) -->
             <div class="md:hidden">
                <!-- Add mobile menu logic if needed later -->
            </div>
        </div>
    </div>
</header>