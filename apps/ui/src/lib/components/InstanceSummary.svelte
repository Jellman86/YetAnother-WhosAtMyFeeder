<script lang="ts">
    import { onMount } from 'svelte';
    import { fetchClassifierStatus } from '../api';
    import type { ClassifierStatus, VersionInfo } from '../api';
    import { authStore } from '../stores/auth.svelte';
    import { getErrorMessage, isTransientRequestError } from '../utils/error-handling';
    import { logger } from '../utils/logger';
    import { _ } from 'svelte-i18n';

    interface Props {
        versionInfo: VersionInfo;
    }

    let { versionInfo }: Props = $props();

    let classifier = $state<ClassifierStatus | null>(null);
    let copied = $state(false);
    let copyFailed = $state(false);

    const isOwner = $derived(authStore.showSettings);

    onMount(() => {
        void (async () => {
            try {
                classifier = await fetchClassifierStatus();
            } catch (error) {
                if (isTransientRequestError(error)) {
                    logger.warn('Classifier status unavailable', { message: getErrorMessage(error) });
                } else {
                    logger.error('Failed to fetch classifier status', error);
                }
            }
        })();
    });

    const acceleration = $derived(
        classifier?.active_provider ??
            classifier?.inference_backend ??
            $_('about.pipeline.unknown', { default: 'unknown' })
    );

    // Deliberately no keys, URLs or camera names: this is meant to be pasted in public.
    const supportSummary = $derived(
        [
            `v${versionInfo.base_version}`,
            versionInfo.branch,
            versionInfo.git_hash,
            acceleration,
            classifier?.effective_model_id ?? classifier?.active_model_id ?? 'no model'
        ]
            .filter(Boolean)
            .join(' · ')
    );

    async function copySummary(): Promise<void> {
        try {
            await navigator.clipboard.writeText(supportSummary);
            copied = true;
            copyFailed = false;
            setTimeout(() => (copied = false), 2000);
        } catch (error) {
            // Clipboard access can be refused; the text stays selectable either way.
            copyFailed = true;
            logger.warn('Clipboard write refused', { message: getErrorMessage(error) });
        }
    }
</script>

{#if isOwner}
    <section class="card-base space-y-4 p-6" data-about-instance aria-labelledby="about-instance-heading">
        <h2 id="about-instance-heading" class="font-display text-xl font-bold text-slate-900 dark:text-white">
            {$_('about.instance.title', { default: 'This instance' })}
        </h2>

        <div class="grid gap-6 sm:grid-cols-[minmax(0,0.8fr)_minmax(0,1.6fr)]">
            <div>
                <p class="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
                    {$_('about.instance.acceleration', { default: 'Acceleration' })}
                </p>
                <p class="font-display text-2xl font-bold text-slate-900 dark:text-white">{acceleration}</p>
                {#if classifier?.fallback_reason}
                    <p class="mt-1 text-[11px] leading-snug text-slate-500 dark:text-slate-400">
                        {classifier.fallback_reason}
                    </p>
                {/if}
            </div>

            <div>
                <p class="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
                    {$_('about.instance.for_issue', { default: 'For an issue report' })}
                </p>
                <div class="mt-1.5 flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-700 dark:bg-slate-900/50">
                    <code class="min-w-0 flex-1 truncate font-mono text-xs text-slate-700 dark:text-slate-200">
                        {supportSummary}
                    </code>
                    <button class="btn btn-secondary min-h-11 shrink-0 px-3 py-1.5 text-xs" onclick={copySummary}>
                        {copied
                            ? $_('about.instance.copied', { default: 'Copied' })
                            : $_('about.instance.copy', { default: 'Copy' })}
                    </button>
                </div>
                <p class="mt-1.5 text-[11px] text-slate-500 dark:text-slate-400">
                    {copyFailed
                        ? $_('about.instance.copy_failed', {
                              default: 'Copying was refused, select the text instead.'
                          })
                        : $_('about.instance.no_secrets', {
                              default: 'Contains no keys, URLs or camera names.'
                          })}
                </p>
            </div>
        </div>
    </section>
{/if}
