<script lang="ts">
    import { _ } from 'svelte-i18n';

    let { visible = $bindable(false) }: { visible: boolean } = $props();
    let modalElement = $state<HTMLDivElement | undefined>(undefined);

    $effect(() => {
        if (visible && modalElement) {
            // Trap focus within modal
            const focusableElements = modalElement.querySelectorAll(
                'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
            );
            const firstElement = focusableElements[0] as HTMLElement;
            const lastElement = focusableElements[focusableElements.length - 1] as HTMLElement;

            function handleTabKey(e: KeyboardEvent) {
                if (e.key !== 'Tab') return;

                if (e.shiftKey) {
                    if (document.activeElement === firstElement) {
                        lastElement.focus();
                        e.preventDefault();
                    }
                } else {
                    if (document.activeElement === lastElement) {
                        firstElement.focus();
                        e.preventDefault();
                    }
                }
            }

            modalElement.addEventListener('keydown', handleTabKey);
            firstElement?.focus();

            return () => {
                modalElement?.removeEventListener('keydown', handleTabKey);
            };
        }
    });

    function handleKeydown(e: KeyboardEvent) {
        if (e.key === 'Escape') {
            visible = false;
        }
    }

    const shortcutGroups = [
        {
            title: $_('shortcuts.navigation', { default: 'Navigation' }),
            items: [
                { key: 'g d', description: $_('shortcuts.go_dashboard', { default: 'Go to Dashboard' }) },
                { key: 'g e', description: $_('shortcuts.go_events', { default: 'Go to Events' }) },
                { key: 'g l', description: $_('shortcuts.go_species', { default: 'Go to Leaderboard' }) },
                { key: 'g t', description: $_('shortcuts.go_settings', { default: 'Go to Settings' }) }
            ]
        },
        {
            title: $_('shortcuts.actions', { default: 'Actions' }),
            items: [
                { key: 'r', description: $_('shortcuts.refresh', { default: 'Refresh page' }) },
                { key: '?', description: $_('shortcuts.open_panel', { default: 'Open shortcuts panel' }) },
                { key: 'Escape', description: $_('shortcuts.close_modal', { default: 'Close modal' }) }
            ]
        }
    ];
</script>

{#if visible}
    <div
        class="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4"
        onclick={() => visible = false}
        onkeydown={handleKeydown}
        role="presentation"
    >
        <div
            bind:this={modalElement}
            role="dialog"
            aria-modal="true"
            aria-labelledby="shortcuts-title"
            tabindex="-1"
            class="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200/80 dark:border-slate-700/50 p-8 max-w-2xl w-full shadow-2xl"
            onclick={(e) => e.stopPropagation()}
            onkeydown={(e) => e.key === 'Escape' && (visible = false)}
        >
            <h2 id="shortcuts-title" class="text-2xl font-black text-slate-900 dark:text-white mb-6">
                {$_('shortcuts.title', { default: 'Keyboard Shortcuts' })}
            </h2>

            <div class="grid grid-cols-1 gap-4 mb-6">
                {#each shortcutGroups as group}
                    <section class="rounded-2xl border border-slate-200/80 dark:border-slate-700/70 bg-slate-50/70 dark:bg-slate-900/45 p-4">
                        <h3 class="text-[11px] font-black uppercase tracking-[0.2em] text-slate-500 dark:text-slate-300 mb-3">
                            {group.title}
                        </h3>
                        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            {#each group.items as shortcut}
                                <div class="flex items-center justify-between gap-3 rounded-xl border border-slate-200/80 dark:border-slate-700/60 bg-white/90 dark:bg-slate-800/70 px-3 py-2">
                                    <span class="text-sm text-slate-700 dark:text-slate-300">{shortcut.description}</span>
                                    <kbd class="inline-flex items-center justify-center px-2 py-1 bg-slate-100 dark:bg-slate-700 rounded-md font-mono text-xs font-bold text-slate-700 dark:text-slate-200 min-w-[64px] text-center shadow-sm border border-slate-200 dark:border-slate-600">
                                        {shortcut.key}
                                    </kbd>
                                </div>
                            {/each}
                        </div>
                    </section>
                {/each}
            </div>

            <button
                onclick={() => visible = false}
                class="w-full px-4 py-3 bg-teal-500 hover:bg-teal-600 text-white font-black text-xs uppercase tracking-widest rounded-2xl transition-all shadow-lg shadow-teal-500/20"
            >
                {$_('common.close', { default: 'Close' })}
            </button>
        </div>
    </div>
{/if}
