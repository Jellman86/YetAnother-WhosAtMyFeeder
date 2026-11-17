<script lang="ts">
    import { onDestroy, onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { analyzeDetection, fetchDetectionConversation, sendDetectionConversationMessage, type ConversationTurn, type Detection } from '../../api';
    import { authStore } from '../../stores/auth.svelte';
    import { detectionsStore } from '../../stores/detections.svelte';
    import { getErrorMessage } from '../../utils/error-handling';
    import MarkdownText from '../MarkdownText.svelte';

    /**
     * The record's AI note and the conversation about it. The note is the record's own
     * `ai_analysis`, so a species change that clears it clears it here too; only a failed request,
     * or a regeneration in flight, stands in for it. The parent remounts it for each identification
     * (`recordClassificationKey`), and an answer that arrives for one it no longer shows is dropped,
     * so neither a failure nor a late note outlives a change of species.
     */
    type Props = { detection: Detection; llmReady: boolean; readOnly: boolean };

    let { detection, llmReady, readOnly }: Props = $props();

    let analysing = $state(false);
    /** What shows instead of the stored note: nothing while it regenerates, or why it failed. */
    let standIn = $state<{ text: string | null } | null>(null);
    let turns = $state<ConversationTurn[]>([]);
    let input = $state('');
    let loading = $state(false);
    let sending = $state(false);
    let error = $state<string | null>(null);

    // The parent remounts this panel when the identification changes, so once it is retired an
    // answer still on its way belongs to an identification no longer on screen.
    let retired = false;
    onDestroy(() => { retired = true; });
    const stillShown = (): boolean => !retired;

    const analysis = $derived(llmReady ? (standIn ? standIn.text : (detection.ai_analysis ?? null)) : null);

    async function loadConversation(): Promise<void> {
        if (!analysis || !authStore.canViewAiConversation) return;
        loading = true;
        error = null;
        try {
            const loaded = await fetchDetectionConversation(detection.frigate_event);
            if (stillShown()) turns = loaded;
        } catch (e) {
            if (stillShown()) error = getErrorMessage(e) || $_('detection.ai.conversation_error');
        } finally {
            loading = false;
        }
    }

    async function send(): Promise<void> {
        const message = input.trim();
        if (!message || sending) return;
        sending = true;
        error = null;
        try {
            const answered = await sendDetectionConversationMessage(detection.frigate_event, message);
            if (!stillShown()) return;
            turns = answered;
            input = '';
        } catch (e) {
            if (stillShown()) error = getErrorMessage(e) || $_('detection.ai.conversation_error');
        } finally {
            sending = false;
        }
    }

    async function analyse(force = false): Promise<void> {
        if (readOnly || !llmReady) return;
        analysing = true;
        if (force) {
            // A new note starts a new conversation, so the old thread goes with the old note.
            standIn = { text: null };
            turns = [];
            input = '';
            error = null;
            loading = false;
            sending = false;
        }
        try {
            const result = await analyzeDetection(detection.frigate_event, force);
            // Written for the identification it was asked about, never for the one that replaced it.
            if (!stillShown()) return;
            detection.ai_analysis = result.analysis;
            detection.ai_analysis_timestamp = result.analysis_timestamp;
            standIn = null;
            detectionsStore.updateDetection({ ...detection, ai_analysis: result.analysis, ai_analysis_timestamp: result.analysis_timestamp });
            await loadConversation();
        } catch (e) {
            if (!stillShown()) return;
            standIn = { text: $_('detection.ai.error', { values: { message: getErrorMessage(e) || 'Analysis failed' } }) };
        } finally {
            analysing = false;
        }
    }

    onMount(() => {
        void loadConversation();
    });
</script>

{#if analysis}
    <div class="space-y-3" data-record-ai-analysis>
        <div class="ai-panel ai-surface">
            <div class="ai-panel__label">{$_('detection.ai.insight')}</div>
            <div class="ai-panel__content ai-markdown ai-markdown-surface">
                <MarkdownText text={analysis} />
            </div>
        </div>
        {#if authStore.canModify}
            <button
                type="button"
                onclick={() => analyse(true)}
                disabled={analysing}
                class="btn btn-secondary min-h-11 w-full px-4 text-sm"
                title={$_('detection.ai.regenerate_warning', { default: 'Regenerate analysis (clears AI conversation history for this detection)' })}
            >
                <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                {analysing ? $_('detection.ai.regenerating') : $_('detection.ai.regenerate')}
            </button>
            {#if turns.length > 0}
                <p class="text-xs text-muted">
                    {$_('detection.ai.regenerate_clears_chat_note', { default: 'Note: Regenerating clears the AI conversation history for this detection.' })}
                </p>
            {/if}
        {/if}
    </div>
{:else if llmReady && analysing}
    <p class="flex min-h-11 w-full items-center justify-center gap-3 rounded-xl bg-surface-raised px-4 text-sm font-semibold text-muted" role="status">
        <span class="h-4 w-4 animate-spin rounded-full border-2 border-accent-line border-t-transparent motion-reduce:animate-none" aria-hidden="true"></span>
        {$_('detection.ai.analyzing')}
    </p>
{:else if llmReady && authStore.canModify && !readOnly}
    <button type="button" onclick={() => analyse()} class="btn btn-secondary min-h-11 w-full px-4 text-sm">
        <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
        {$_('detection.ai.ask')}
    </button>
{/if}

{#if analysis && authStore.canViewAiConversation}
    <section class="space-y-3" aria-labelledby="record-ai-conversation-title" data-record-ai-conversation>
        <h3 id="record-ai-conversation-title" class="text-xs font-semibold text-strong">{$_('detection.ai.conversation_title')}</h3>
        <div class="ai-thread">
            {#if loading}
                <p class="flex min-h-11 items-center justify-center gap-3 rounded-xl bg-surface-raised px-4 text-sm font-semibold text-muted" role="status">
                    <span class="h-4 w-4 animate-spin rounded-full border-2 border-accent-line border-t-transparent motion-reduce:animate-none" aria-hidden="true"></span>
                    {$_('detection.ai.conversation_loading')}
                </p>
            {:else if error}
                <p class="text-xs font-semibold text-status-fail" role="alert">{error}</p>
            {:else if turns.length === 0}
                <p class="text-xs text-muted">{$_('detection.ai.conversation_empty')}</p>
            {:else}
                <div class="space-y-2">
                    {#each turns as turn, index (index)}
                        <div class="ai-bubble {turn.role === 'assistant' ? 'ai-bubble--assistant ai-surface' : 'ai-bubble--user'}">
                            <div class="ai-bubble__role">{turn.role === 'assistant' ? $_('detection.ai.assistant') : $_('detection.ai.user')}</div>
                            {#if turn.role === 'assistant'}
                                <div class="ai-bubble__content ai-markdown ai-markdown-surface"><MarkdownText text={turn.content} /></div>
                            {:else}
                                <div class="ai-bubble__content">{turn.content}</div>
                            {/if}
                        </div>
                    {/each}
                </div>
            {/if}

            {#if authStore.canModify}
                <div class="space-y-2">
                    <label for="record-ai-message" class="sr-only">{$_('detection.ai.conversation_placeholder')}</label>
                    <textarea id="record-ai-message" rows="2" bind:value={input} placeholder={$_('detection.ai.conversation_placeholder')} class="input-base text-xs"></textarea>
                    <button type="button" onclick={send} disabled={!input.trim() || sending} class="btn btn-primary min-h-11 w-full px-4 text-xs">
                        {sending ? $_('detection.ai.sending') : $_('detection.ai.send')}
                    </button>
                </div>
            {/if}
        </div>
    </section>
{/if}

<style>
    .ai-surface {
        position: relative;
        overflow: hidden;
        padding: 1.25rem;
        border-radius: 1.25rem;
        background: rgb(var(--brand-500) / 0.08);
        border: 1px solid rgb(var(--brand-500) / 0.22);
        color: rgb(var(--ai-ink));
        box-shadow: none;
    }

    .ai-surface::before {
        content: '';
        position: absolute;
        inset: 0;
        pointer-events: none;
        border-radius: inherit;
        background: none;
    }

    .ai-surface > * {
        position: relative;
        z-index: 1;
    }

    :global(.dark) .ai-surface,
    :global([data-theme='dark']) .ai-surface {
        /* Softer dark surface: keep the teal identity, reduce the "hard slab" look. */
        background: rgb(var(--brand-700) / 0.20);
        border-color: rgb(var(--brand-400) / 0.35);
        box-shadow: none;
    }

    .ai-panel {
        position: relative;
    }

    .ai-panel__label {
        font-size: 0.75rem;
        font-weight: 700;
        color: rgb(var(--ai-heading));
        margin-bottom: 0.75rem;
    }

    :global(.ai-markdown-surface) {
        color: inherit;
    }

    :global(.ai-markdown-surface) {
        color: rgb(var(--ai-ink));
    }

    :global(.ai-markdown-surface h1) {
        margin: 0.75rem 0 0.4rem;
        font-size: 1.0rem;
        letter-spacing: 0.02em;
        text-transform: none;
        font-weight: 900;
        color: rgb(var(--ai-heading));
    }

    :global(.ai-markdown-surface h2) {
        margin: 0.7rem 0 0.35rem;
        font-size: 0.95rem;
        letter-spacing: 0.015em;
        text-transform: none;
        font-weight: 850;
        color: rgb(var(--ai-heading));
    }

    :global(.ai-markdown-surface h3) {
        margin: 0.65rem 0 0.3rem;
        font-size: 0.9rem;
        letter-spacing: 0.01em;
        text-transform: none;
        font-weight: 800;
        color: rgb(var(--ai-heading));
    }

    :global(.ai-markdown-surface h4) {
        margin: 0.6rem 0 0.25rem;
        font-size: 0.86rem;
        letter-spacing: 0.01em;
        text-transform: none;
        font-weight: 800;
        color: rgb(var(--ai-heading));
    }

    :global(.ai-markdown-surface h5),
    :global(.ai-markdown-surface h6) {
        margin: 0.55rem 0 0.2rem;
        font-size: 0.82rem;
        letter-spacing: 0.01em;
        text-transform: none;
        font-weight: 750;
        color: rgb(var(--ai-heading));
    }

    :global(.ai-markdown-surface p) {
        margin: 0.3rem 0;
        font-size: 0.88rem;
        line-height: 1.55;
        color: inherit;
    }

    :global(.ai-markdown-surface ul) {
        margin: 0.35rem 0 0.65rem;
        padding-left: 1.2rem;
        list-style: disc;
        list-style-position: outside;
    }

    :global(.ai-markdown-surface ol) {
        margin: 0.35rem 0 0.65rem;
        padding-left: 1.3rem;
        list-style: decimal;
        list-style-position: outside;
    }

    :global(.ai-markdown-surface ul ul),
    :global(.ai-markdown-surface ol ol),
    :global(.ai-markdown-surface ul ol),
    :global(.ai-markdown-surface ol ul) {
        margin: 0.2rem 0 0.4rem;
    }

    :global(.ai-markdown-surface li) {
        margin: 0.25rem 0;
        font-size: 0.88rem;
        color: inherit;
    }

    :global(.ai-markdown-surface li::marker) {
        color: rgb(var(--ai-marker) / 0.55);
    }

    :global(.ai-markdown-surface strong) {
        font-weight: 700;
        color: rgb(var(--ai-strong));
    }

    :global(.ai-markdown-surface em) {
        color: rgb(var(--ai-ink) / 0.82);
    }

    :global(.ai-markdown-surface code) {
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
        font-size: 0.75rem;
        padding: 0.1rem 0.3rem;
        border-radius: 0.4rem;
        background: rgb(var(--brand-700) / 0.1);
        color: rgb(var(--ai-code));
    }

    :global(.dark .ai-markdown-surface code),
    :global([data-theme='dark'] .ai-markdown-surface code) {
        background: rgb(var(--brand-400) / 0.25);
    }

    :global(.ai-markdown-surface pre) {
        margin: 0.5rem 0 0.75rem;
        padding: 0.75rem 0.9rem;
        border-radius: 0.75rem;
        background: rgb(var(--brand-700) / 0.08);
        border: 1px solid rgb(var(--brand-700) / 0.12);
        overflow-x: auto;
    }

    :global(.dark .ai-markdown-surface pre),
    :global([data-theme='dark'] .ai-markdown-surface pre) {
        background: color-mix(in srgb, var(--color-slate-900) 60%, transparent);
        border-color: rgb(var(--brand-400) / 0.2);
    }

    :global(.ai-markdown-surface pre code) {
        display: block;
        padding: 0;
        background: transparent;
        color: inherit;
        font-size: 0.78rem;
        line-height: 1.55;
    }

    :global(.ai-markdown-surface blockquote) {
        margin: 0.5rem 0 0.75rem;
        padding: 0.5rem 0.9rem;
        border: 1px solid rgb(var(--brand-500) / 0.25);
        background: rgb(var(--brand-500) / 0.08);
        border-radius: 0.6rem;
        color: inherit;
    }

    :global(.dark .ai-markdown-surface blockquote),
    :global([data-theme='dark'] .ai-markdown-surface blockquote) {
        background: rgb(var(--brand-500) / 0.18);
        border-color: rgb(var(--brand-300) / 0.35);
    }

    :global(.ai-markdown-surface a) {
        color: rgb(var(--ai-heading));
        text-decoration: underline;
        text-decoration-thickness: 1px;
        text-underline-offset: 2px;
    }

    :global(.ai-markdown-surface hr) {
        border: none;
        height: 1px;
        margin: 0.6rem 0 0.8rem;
        background: color-mix(in srgb, var(--color-slate-400) 35%, transparent);
    }

    :global(.dark .ai-markdown-surface hr),
    :global([data-theme='dark'] .ai-markdown-surface hr) {
        background: color-mix(in srgb, var(--color-slate-600) 50%, transparent);
    }

    :global(.ai-markdown-surface table) {
        width: 100%;
        border-collapse: collapse;
        margin: 0.5rem 0 0.75rem;
        font-size: 0.82rem;
    }

    :global(.ai-markdown-surface th),
    :global(.ai-markdown-surface td) {
        padding: 0.35rem 0.5rem;
        border-bottom: 1px solid color-mix(in srgb, var(--color-slate-400) 25%, transparent);
        text-align: left;
    }

    :global(.dark .ai-markdown-surface th),
    :global(.dark .ai-markdown-surface td),
    :global([data-theme='dark'] .ai-markdown-surface th),
    :global([data-theme='dark'] .ai-markdown-surface td) {
        border-bottom-color: color-mix(in srgb, var(--color-slate-600) 45%, transparent);
    }

    :global(.ai-markdown-surface th) {
        font-weight: 700;
        color: rgb(var(--ai-code));
        font-size: 0.75rem;
    }

    :global(.ai-markdown-surface > :first-child) {
        margin-top: 0;
    }

    :global(.ai-markdown-surface > :last-child) {
        margin-bottom: 0;
    }

    .ai-bubble {
        position: relative;
        padding: 0.75rem 0.9rem;
        border-radius: 1rem;
        border: 1px solid transparent;
        background: color-mix(in srgb, var(--color-slate-100) 90%, transparent);
        color: rgb(var(--ai-ink));
        box-shadow: 0 8px 16px color-mix(in srgb, var(--color-slate-900) 8%, transparent);
    }

    :global(.dark) .ai-bubble,
    :global([data-theme='dark']) .ai-bubble {
        background: color-mix(in srgb, var(--color-slate-900) 72%, transparent);
    }

    .ai-bubble.ai-surface {
        padding: 1.1rem 1.2rem;
        border-color: rgb(var(--brand-500) / 0.22);
        background: rgb(var(--brand-500) / 0.08);
        box-shadow: none;
    }

    :global(.dark) .ai-bubble.ai-surface,
    :global([data-theme='dark']) .ai-bubble.ai-surface {
        background: rgb(var(--brand-700) / 0.18);
        border-color: rgb(var(--brand-400) / 0.35);
        box-shadow: none;
    }

    .ai-bubble--assistant {
        border-color: rgb(var(--brand-500) / 0.35);
    }

    :global(.theme-bluetit:not(.dark)) .ai-bubble--assistant {
        border-color: rgb(var(--brand-600) / 0.35);
    }
    :global(.theme-bluetit.dark) .ai-bubble--assistant {
        border-color: rgb(var(--brand-400) / 0.40);
    }

    .ai-bubble--user {
        border-color: color-mix(in srgb, var(--color-slate-400) 30%, transparent);
        background: color-mix(in srgb, var(--color-slate-200) 70%, transparent);
    }

    :global(.dark) .ai-bubble--user,
    :global([data-theme='dark']) .ai-bubble--user {
        background: color-mix(in srgb, var(--color-slate-800) 80%, transparent);
    }

    .ai-bubble__role {
        font-size: 0.75rem;
        font-weight: 700;
        color: rgb(var(--ai-muted));
        margin-bottom: 0.4rem;
    }

    .ai-bubble__content {
        font-size: 0.88rem;
        line-height: 1.55;
        white-space: pre-wrap;
    }

    .ai-bubble--assistant .ai-bubble__content {
        white-space: normal;
    }

    :global(.ai-bubble--assistant .ai-markdown-surface h1),
    :global(.ai-bubble--assistant .ai-markdown-surface h2),
    :global(.ai-bubble--assistant .ai-markdown-surface h3),
    :global(.ai-bubble--assistant .ai-markdown-surface h4),
    :global(.ai-bubble--assistant .ai-markdown-surface h5),
    :global(.ai-bubble--assistant .ai-markdown-surface h6) {
        margin-top: 0.5rem;
        margin-bottom: 0.2rem;
    }

    :global(.ai-bubble--assistant .ai-markdown-surface p) {
        margin: 0.2rem 0;
    }

    :global(.ai-bubble--assistant .ai-markdown-surface ul),
    :global(.ai-bubble--assistant .ai-markdown-surface ol) {
        margin: 0.25rem 0 0.55rem;
    }

    .ai-bubble--assistant :global(.ai-markdown-surface p),
    .ai-bubble--assistant :global(.ai-markdown-surface li) {
        color: inherit;
    }

    .ai-thread {
        border-radius: 1.25rem;
        padding: 0.9rem;
        border: 1px solid color-mix(in srgb, var(--color-slate-400) 16%, transparent);
        background: color-mix(in srgb, var(--color-slate-50) 60%, transparent);
        box-shadow: 0 8px 18px color-mix(in srgb, var(--color-slate-900) 6%, transparent);
    }

    :global(.dark) .ai-thread,
    :global([data-theme='dark']) .ai-thread {
        border-color: rgb(var(--brand-400) / 0.18);
        background: color-mix(in srgb, var(--color-slate-950) 22%, transparent);
        box-shadow: 0 10px 22px color-mix(in srgb, var(--color-slate-950) 28%, transparent);
    }
</style>
