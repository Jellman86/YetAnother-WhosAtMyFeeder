<script lang="ts">
    import { authStore } from '../stores/auth.svelte';
    import { _ } from 'svelte-i18n';
    
    let username = $state('');
    let password = $state('');
    let error = $state('');
    let isLoading = $state(false);

    async function handleSubmit(e: Event) {
        e.preventDefault();
        if (!username.trim() || !password) return;

        isLoading = true;
        error = '';
        
        try {
            await authStore.login(username.trim(), password);
        } catch (err) {
            error = err instanceof Error ? err.message : 'Login failed';
            isLoading = false;
        }
    }

    function handleGuest() {
        // Just reloading usually triggers the guest flow if public access is enabled
        // or we can navigate to dashboard?
        // Actually, if we are in <Login />, it means requiresLogin is true.
        // requiresLogin = authRequired && !publicAccess && !authenticated.
        // So if publicAccessEnabled is true, we shouldn't be here?
        // Wait, requiresLogin in App.svelte logic:
        // requiresLogin = authStore.authRequired && !authStore.publicAccessEnabled && !authStore.isAuthenticated ...
        // So if publicAccessEnabled is TRUE, requiresLogin is FALSE.
        // Thus, <Login /> is NOT shown.
        // So the "Continue as Guest" button is redundant/impossible here unless logic changes.
        // I'll skip it to avoid confusion.
        window.location.reload();
    }
</script>

<div class="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 px-4 transition-colors duration-300">
    <div class="w-full max-w-sm space-y-8">
        <!-- Card -->
        <div class="bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl p-8 rounded-3xl shadow-2xl border border-white/20 dark:border-slate-800 ring-1 ring-slate-900/5">
            
            <!-- Header -->
            <div class="text-center mb-8">
                <div class="mx-auto w-20 h-20 bg-gradient-to-tr from-teal-400 to-emerald-500 rounded-2xl shadow-lg flex items-center justify-center mb-6 transform rotate-3">
                    <img src="/pwa-192x192.png" alt="Logo" class="w-16 h-16 object-contain drop-shadow-md -rotate-3" />
                </div>
                <h2 class="text-2xl font-black text-slate-900 dark:text-white tracking-tight">
                    {$_('auth.welcome_back')}
                </h2>
                <p class="mt-2 text-sm font-medium text-slate-500 dark:text-slate-400">
                    {$_('auth.signin_desc')}
                </p>
            </div>
            
            <form class="space-y-5" onsubmit={handleSubmit}>
                <div class="space-y-4">
                    <div>
                        <label for="username" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-1.5 ml-1">{$_('auth.username')}</label>
                        <input
                            id="username"
                            name="username"
                            type="text"
                            required
                            bind:value={username}
                            class="block w-full px-4 py-3.5 rounded-2xl border-0 bg-slate-100 dark:bg-slate-800/50 text-slate-900 dark:text-white font-bold text-sm shadow-inner ring-1 ring-slate-200 dark:ring-slate-700 focus:ring-2 focus:ring-teal-500 outline-none transition-all placeholder:text-slate-400 dark:placeholder:text-slate-600"
                            placeholder={$_('auth.username_placeholder')}
                        />
                    </div>
                    <div>
                        <label for="password" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-1.5 ml-1">{$_('auth.password')}</label>
                        <input
                            id="password"
                            name="password"
                            type="password"
                            required
                            bind:value={password}
                            class="block w-full px-4 py-3.5 rounded-2xl border-0 bg-slate-100 dark:bg-slate-800/50 text-slate-900 dark:text-white font-bold text-sm shadow-inner ring-1 ring-slate-200 dark:ring-slate-700 focus:ring-2 focus:ring-teal-500 outline-none transition-all placeholder:text-slate-400 dark:placeholder:text-slate-600"
                            placeholder="••••••••"
                        />
                    </div>
                </div>

                {#if error}
                    <div class="p-3 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-100 dark:border-red-900/30 text-red-600 dark:text-red-400 text-xs font-bold text-center animate-in fade-in slide-in-from-top-1">
                        {error}
                    </div>
                {/if}

                <button
                    type="submit"
                    disabled={isLoading}
                    class="w-full flex items-center justify-center py-3.5 px-4 rounded-2xl text-sm font-black text-white bg-gradient-to-r from-teal-500 to-emerald-600 hover:from-teal-400 hover:to-emerald-500 shadow-lg shadow-teal-500/20 active:scale-[0.98] transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    {#if isLoading}
                        <div class="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin mr-2"></div>
                        {$_('auth.verifying')}
                    {:else}
                        {$_('auth.signin_button')}
                    {/if}
                </button>

                {#if authStore.publicAccessEnabled}
                    <button
                        type="button"
                        onclick={() => authStore.cancelLogin()}
                        class="w-full flex items-center justify-center py-3.5 px-4 rounded-2xl text-sm font-bold text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-all"
                    >
                        {$_('auth.continue_guest')}
                    </button>
                {/if}
            </form>
        </div>
        
        <p class="text-center text-[10px] font-bold text-slate-400 dark:text-slate-600 uppercase tracking-widest">
            {$_('auth.secure_access')}
        </p>
    </div>
</div>
