<script lang="ts">
    import { settingsStore } from '../stores/settings.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { _ } from 'svelte-i18n';

    const isOwner = $derived(authStore.showSettings);

    // Table names are identifiers, not copy, so they are never translated.
    const storageTables = [
        { key: 'detections', table: 'detections' },
        { key: 'audio', table: 'audio_detections' },
        { key: 'taxonomy', table: 'taxonomy_cache' }
    ];

    const outbound = $derived([
        { key: 'inat', on: true },
        { key: 'weather', on: true },
        { key: 'llm', on: Boolean(settingsStore.settings?.llm_enabled) },
        { key: 'telemetry', on: Boolean(settingsStore.settings?.telemetry_enabled) }
    ]);
</script>

    <section aria-labelledby="about-stores-title">
        <h3 id="about-stores-title" class="text-sm font-bold text-slate-900 dark:text-white">
            {$_('about.storage.title', { default: 'What it stores' })}
        </h3>
        <dl class="mt-2 divide-y divide-slate-200/70 text-xs dark:divide-slate-700/50">
            {#each storageTables as row (row.key)}
                <div class="py-1.5">
                    <dt class="font-mono text-[11px] font-semibold text-slate-800 dark:text-slate-100">
                        {row.table}
                    </dt>
                    <dd class="text-slate-500 dark:text-slate-400">
                        {$_(`about.storage.${row.key}_desc`)}
                    </dd>
                </div>
            {/each}
        </dl>
        <p class="mt-2 text-[11px] text-slate-500 dark:text-slate-400">
            {$_('about.storage.note', {
                default: 'SQLite under /data. Schema changes ship reversible migrations.'
            })}
        </p>
    </section>

    <section aria-labelledby="about-outbound-title">
        <h3 id="about-outbound-title" class="text-sm font-bold text-slate-900 dark:text-white">
            {$_('about.outbound.title', { default: 'What leaves your network' })}
        </h3>
        <dl class="mt-2 divide-y divide-slate-200/70 text-xs dark:divide-slate-700/50">
            {#each outbound as item (item.key)}
                <div class="flex items-center gap-3 py-1.5">
                    <span class="min-w-0 flex-1">
                        <dt class="font-semibold text-slate-800 dark:text-slate-100">
                            {$_(`about.outbound.${item.key}`)}
                        </dt>
                        <dd class="text-slate-500 dark:text-slate-400">
                            {$_(`about.outbound.${item.key}_desc`)}
                        </dd>
                    </span>
                    <span
                        class="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider {item.on
                            ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300'
                            : 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400'}"
                    >
                        {item.on
                            ? $_('about.pipeline.enabled', { default: 'enabled' })
                            : $_('about.pipeline.off', { default: 'off' })}
                    </span>
                </div>
            {/each}
        </dl>
        {#if !isOwner}
            <p class="mt-2 text-[11px] text-slate-500 dark:text-slate-400">
                {$_('about.outbound.guest_note', {
                    default: 'Shown for transparency. Only the owner can change these.'
                })}
            </p>
        {/if}
    </section>
