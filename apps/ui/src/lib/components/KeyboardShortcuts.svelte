<script lang="ts">
    import { _ } from 'svelte-i18n';
    import DialogCloseButton from './DialogCloseButton.svelte';

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
                { key: 'g e', description: $_('shortcuts.go_events', { default: 'Go to Explorer' }) },
                { key: 'g l', description: $_('shortcuts.go_species', { default: 'Go to Leaderboard' }) },
                { key: 'g j', description: $_('shortcuts.go_notifications', { default: 'Go to Notifications' }) },
                { key: 'g t', description: $_('shortcuts.go_settings', { default: 'Go to Settings' }) }
            ]
        },
        {
            // The Explorer's day strip; said here rather than on the page, where it was permanent clutter.
            title: $_('nav.explorer', { default: 'Explorer' }),
            items: [
                { key: '[', description: $_('shortcuts.previous_day', { default: 'Previous day' }) },
                { key: ']', description: $_('shortcuts.next_day', { default: 'Next day' }) },
                { key: '0', description: $_('shortcuts.all_days', { default: 'Show every day' }) }
            ]
        },
        {
            title: $_('shortcuts.actions', { default: 'Actions' }),
            items: [
                { key: 'r', description: $_('shortcuts.refresh', { default: 'Refresh page' }) },
                { key: '/', description: $_('shortcuts.search', { default: 'Search this page (Explorer and Settings)' }) },
                { key: '?', description: $_('shortcuts.open_panel', { default: 'Open shortcuts panel' }) },
                { key: 'Escape', description: $_('shortcuts.close_modal', { default: 'Close the dialog' }) }
            ]
        }
    ];
</script>

{#if visible}
    <div
        class="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-4"
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
            class="bg-surface rounded-2xl border border-line p-6 sm:p-8 max-w-2xl w-full max-h-[calc(100dvh-2rem)] overflow-y-auto shadow-2xl"
            onclick={(e) => e.stopPropagation()}
            onkeydown={(e) => e.key === 'Escape' && (visible = false)}
        >
            <div class="mb-6 flex items-start justify-between gap-4">
                <h2 id="shortcuts-title" class="text-2xl font-bold text-slate-900 dark:text-white">
                    {$_('shortcuts.title', { default: 'Keyboard shortcuts' })}
                </h2>
                <DialogCloseButton onclick={() => visible = false} />
            </div>

            <div class="grid grid-cols-1 gap-6">
                {#each shortcutGroups as group}
                    <section>
                        <h3 class="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-200">
                            {group.title}
                        </h3>
                        <ul class="divide-y divide-line-soft border-y border-line-soft">
                            {#each group.items as shortcut}
                                <li class="flex items-center justify-between gap-3 py-2">
                                    <span class="text-sm text-slate-700 dark:text-slate-300">{shortcut.description}</span>
                                    <kbd class="inline-flex min-w-16 items-center justify-center rounded-md border border-line bg-surface-raised px-2 py-1 text-center font-mono text-xs font-bold text-slate-700 dark:text-slate-200">
                                        {shortcut.key}
                                    </kbd>
                                </li>
                            {/each}
                        </ul>
                    </section>
                {/each}
            </div>
        </div>
    </div>
{/if}
