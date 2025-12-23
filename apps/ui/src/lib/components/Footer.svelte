<script lang="ts">
    const version = "2.0.0";
    const year = new Date().getFullYear();
</script>

<footer class="bg-white/50 dark:bg-slate-900/50 border-t border-slate-200/80 dark:border-slate-700/50 mt-auto backdrop-blur-sm">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <div class="flex flex-col md:flex-row justify-between items-center gap-4 text-sm text-slate-600 dark:text-slate-400">
            <div class="flex flex-col sm:flex-row items-center gap-2 sm:gap-4">
                <span class="font-medium text-slate-700 dark:text-slate-300">
                    Yet Another WhosAtMyFeeder
                </span>
                <span class="hidden sm:inline text-slate-400 dark:text-slate-500">|</span>
                <span>v{version}</span>
            </div>

            <div class="flex items-center gap-4">
                <a
                    href="https://github.com/Jellman86/YetAnother-WhatAtMyFeeder"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="hover:text-slate-900 dark:hover:text-white transition-colors flex items-center gap-1.5"
                >
                    <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                        <path fill-rule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" clip-rule="evenodd" />
                    </svg>
                    GitHub
                </a>
                <span class="text-slate-400 dark:text-slate-500">|</span>
                <span>MIT License</span>
            </div>

            <div class="text-center md:text-right">
                <span>&copy; {year} Jellman86</span>
            </div>
        </div>

        <div class="mt-4 pt-4 border-t border-slate-200/60 dark:border-slate-700/40 text-center text-xs text-slate-500 dark:text-slate-500">
            Built with AI assistance for the love of bird watching
        </div>
    </div>
</footer>
