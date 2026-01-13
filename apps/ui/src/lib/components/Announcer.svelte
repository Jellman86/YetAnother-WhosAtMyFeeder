<script module lang="ts">
    import { writable } from 'svelte/store';

    export type AnnouncerMessage = {
        text: string;
        politeness: 'polite' | 'assertive';
    };

    const createAnnouncerStore = () => {
        const { subscribe, set } = writable<AnnouncerMessage | null>(null);

        return {
            subscribe,
            announce: (text: string, politeness: 'polite' | 'assertive' = 'polite') => {
                // Clear first to re-trigger if same text
                set(null);
                setTimeout(() => {
                    set({ text, politeness });
                }, 50);
            }
        };
    };

    export const announcer = createAnnouncerStore();
</script>

<script lang="ts">
    let message = $state<AnnouncerMessage | null>(null);

    announcer.subscribe(value => {
        message = value;
    });
</script>

<div class="sr-only" aria-live={message?.politeness || 'polite'} aria-atomic="true">
    {#if message}
        {message.text}
    {/if}
</div>
