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

    /** Whether the install-count read is on, as the About page learned from the read itself. */
    let { communityReadEnabled = null }: { communityReadEnabled?: boolean | null } = $props();
    const ebirdEnabled = $derived(
        Boolean(settingsStore.settings?.ebird_enabled ?? authStore.ebirdEnabled)
    );

    // eBird sightings ship with a map, and the map tiles are fetched from
    // OpenStreetMap by each viewer's browser. Both calls are listed because the
    // panel's promise is that nothing else leaves the network.
    const outbound = $derived([
        { key: 'inat', on: true },
        { key: 'weather', on: true },
        { key: 'ebird', on: ebirdEnabled },
        { key: 'osm', on: ebirdEnabled },
        { key: 'llm', on: Boolean(settingsStore.llmEnabled) },
        { key: 'telemetry', on: Boolean(settingsStore.settings?.telemetry_enabled) },
        { key: 'community', on: communityReadEnabled ?? Boolean(settingsStore.settings?.update_check_enabled) }
    ]);
</script>

    <section aria-labelledby="about-stores-title">
        <h3 id="about-stores-title" class="text-sm font-bold text-slate-900 dark:text-white">
            {$_('about.storage.title', { default: 'What it stores' })}
        </h3>
        <dl class="mt-2 divide-y divide-slate-200/70 text-xs dark:divide-slate-700/50">
            {#each storageTables as row (row.key)}
                <div class="py-1.5">
                    <dt class="font-mono text-2xs font-semibold text-slate-800 dark:text-slate-100">
                        {row.table}
                    </dt>
                    <dd class="text-slate-600 dark:text-slate-400">
                        {$_(`about.storage.${row.key}_desc`)}
                    </dd>
                </div>
            {/each}
        </dl>
        <p class="mt-2 text-2xs text-slate-600 dark:text-slate-400">
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
                <!-- Each group is a term and two descriptions (what it is for, whether it is on) as direct
                     children, which is the only shape a definition list reads correctly in. -->
                <div class="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 py-1.5">
                    <dt class="col-start-1 font-semibold text-slate-800 dark:text-slate-100">
                        {$_(`about.outbound.${item.key}`)}
                    </dt>
                    <dd class="col-start-1 text-slate-600 dark:text-slate-400">
                        {$_(`about.outbound.${item.key}_desc`)}
                    </dd>
                    <dd
                        class="col-start-2 row-span-2 row-start-1 shrink-0 rounded-sm px-1.5 py-0.5 text-3xs font-bold uppercase tracking-wider {item.on
                            ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300'
                            : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'}"
                    >
                        {item.on
                            ? $_('about.pipeline.enabled', { default: 'enabled' })
                            : $_('about.pipeline.off', { default: 'off' })}
                    </dd>
                </div>
            {/each}
        </dl>
        {#if !isOwner}
            <p class="mt-2 text-2xs text-slate-600 dark:text-slate-400">
                {$_('about.outbound.guest_note', {
                    default: 'Shown for transparency. Only the owner can change these.'
                })}
            </p>
        {/if}
    </section>
