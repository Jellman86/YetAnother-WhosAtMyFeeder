<script lang="ts">
    import { onMount } from 'svelte';
    import { _, json } from 'svelte-i18n';
    import { fetchVersion, type VersionInfo } from '../api';

    const appVersion = typeof __APP_VERSION__ === 'string' ? __APP_VERSION__ : 'unknown';
    const appVersionBase = appVersion.includes('+') ? appVersion.split('+')[0] : appVersion;

    let version = $state(appVersionBase);
    let versionInfo = $state<VersionInfo>({
        version: appVersion,
        base_version: appVersionBase,
        git_hash: __GIT_HASH__,
        branch: typeof __APP_BRANCH__ === 'string' ? __APP_BRANCH__ : 'unknown'
    });

    $effect(() => {
        (async () => {
            try {
                const info = await fetchVersion();
                versionInfo = info;
                // Show clean version - hide "+unknown" suffix if git hash isn't available
                version = info.git_hash === "unknown" ? info.base_version : info.version;
            } catch (e) {
                console.error('Failed to fetch version info', e);
            }
        })();
    });

    // Get bird facts from i18n using json() for array values - fallback to empty array if missing
    const birdFacts = $derived(($json('footer.bird_facts') || []) as string[]);

    let currentFactIndex = $state(0);
    let isTransitioning = $state(false);
    let prefersReducedMotion = $state(false);
    let transitionTimeout: ReturnType<typeof setTimeout> | undefined;
    const currentFact = $derived(
        birdFacts.length > 0 ? (birdFacts[currentFactIndex % birdFacts.length] ?? '') : ''
    );
    const year = $derived(new Date().getFullYear());

    function advanceFact(): void {
        if (birdFacts.length === 0) return;
        if (birdFacts.length === 1) {
            currentFactIndex = 0;
            return;
        }

        if (prefersReducedMotion) {
            currentFactIndex = (currentFactIndex + 1) % birdFacts.length;
            return;
        }

        isTransitioning = true;
        transitionTimeout = setTimeout(() => {
            currentFactIndex = birdFacts.length > 0 ? (currentFactIndex + 1) % birdFacts.length : 0;
            isTransitioning = false;
            transitionTimeout = undefined;
        }, 300);
    }

    onMount(() => {
        const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
        const updateMotionPreference = () => {
            prefersReducedMotion = motionQuery.matches;
            if (prefersReducedMotion && transitionTimeout !== undefined) {
                clearTimeout(transitionTimeout);
                transitionTimeout = undefined;
                isTransitioning = false;
            }
        };
        updateMotionPreference();
        motionQuery.addEventListener('change', updateMotionPreference);

        // Randomize starting fact
        if (birdFacts.length > 0) {
            currentFactIndex = Math.floor(Math.random() * birdFacts.length);
        }

        const interval = setInterval(advanceFact, 8000);

        return () => {
            clearInterval(interval);
            if (transitionTimeout !== undefined) clearTimeout(transitionTimeout);
            motionQuery.removeEventListener('change', updateMotionPreference);
        };
    });
</script>

<footer class="bg-white/50 dark:bg-slate-900/50 border-t border-slate-200/80 dark:border-slate-700/50 mt-auto backdrop-blur-sm">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <div class="flex flex-col md:flex-row justify-between items-center gap-4 text-sm text-slate-600 dark:text-slate-400">
            <div class="flex flex-col sm:flex-row items-center gap-2 sm:gap-4">
                <span class="font-medium text-slate-700 dark:text-slate-300">
                    Yet Another WhosAtMyFeeder
                </span>
                <span class="hidden sm:inline text-slate-400 dark:text-slate-500">|</span>
                <a
                    href="https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/blob/dev/CHANGELOG.md"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="hover:text-brand-600 dark:hover:text-brand-400 transition-colors"
                    title={versionInfo.git_hash !== "unknown" ? `Git: ${versionInfo.git_hash}` : $_('about.view_changelog', { default: 'View changelog' })}
                >
                    v{version}
                </a>
            </div>

            <div class="flex items-center gap-4">
                <a
                    href="https://github.com/Jellman86/YetAnother-WhosAtMyFeeder"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="hover:text-slate-900 dark:hover:text-white transition-colors flex items-center gap-1.5"
                >
                    <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                        <path fill-rule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" clip-rule="evenodd" />
                    </svg>
                    {$_('common.github', { default: 'GitHub' })}
                </a>
                <span class="text-slate-400 dark:text-slate-500">|</span>
                <span>{$_('common.mit_license', { default: 'MIT License' })}</span>
            </div>

            <div class="text-center md:text-right">
                <span>&copy; {year} Jellman86</span>
            </div>
        </div>

        <!-- Bird Facts Ticker -->
        <div class="mt-4 pt-4 border-t border-slate-200/60 dark:border-slate-700/40">
            <!-- Facts vary from four words to two lines. Without a reserved height the whole
                 footer jumps every time the ticker turns over. -->
            <div class="flex min-h-28 flex-col items-center justify-center gap-1 text-xs text-slate-600 sm:min-h-10 sm:flex-row sm:gap-2 dark:text-slate-400">
                <span class="text-amber-700 dark:text-amber-300 flex-shrink-0">{$_('footer.did_you_know', { default: 'Did you know?' })}</span>
                <span
                    class="text-center motion-safe:transition-opacity motion-safe:duration-300"
                    class:opacity-0={isTransitioning}
                    class:opacity-100={!isTransitioning}
                >
                    {currentFact}
                </span>
            </div>
        </div>

        <div class="mt-3 text-center text-xs text-slate-500 dark:text-slate-500">
            {$_('footer.built_with_ai', { default: 'Built with AI assistance, and a lot of trial and error' })}
        </div>
    </div>
</footer>
