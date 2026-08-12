<script lang="ts">
    import { fetchVersion, type VersionInfo } from '../api';
    import { APP_ICON_192_URL } from '../assets';
    import InstancePipeline from '../components/InstancePipeline.svelte';
    import InstanceSummary from '../components/InstanceSummary.svelte';
    import PrivacySummary from '../components/PrivacySummary.svelte';
    import { onMount } from 'svelte';
    import { fetchEvents, fetchEventFilters, fetchEventsCount, getThumbnailUrl } from '../api';
    import type { Detection } from '../api';
    import { fetchDetectionsActivityHeatmapSpan } from '../api/leaderboard';
    import { getErrorMessage, isTransientRequestError } from '../utils/error-handling';
    import { logger } from '../utils/logger';
    import { _ } from 'svelte-i18n';

    type LinkParts = {
        before: string;
        after: string;
    };

    const appVersion = typeof __APP_VERSION__ === 'string' ? __APP_VERSION__ : 'unknown';
    const appVersionBase = appVersion.includes('+') ? appVersion.split('+')[0] : appVersion;
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
            } catch {
                // Fall back to build-time version info when runtime fetch fails.
            }
        })();
    });

    // The colophon states what this feeder has recorded, not what the software can do.
    let totalDetections = $state<number | null>(null);
    let speciesCount = $state<number | null>(null);
    let weekCount = $state<number | null>(null);
    let recentPhotos = $state<Detection[]>([]);

    onMount(() => {
        const controller = new AbortController();
        void (async () => {
            try {
                const [count, filters, heatmap, recent] = await Promise.all([
                    fetchEventsCount(),
                    fetchEventFilters(),
                    fetchDetectionsActivityHeatmapSpan('week'),
                    fetchEvents({ limit: 4 })
                ]);
                if (controller.signal.aborted) return;
                totalDetections = count.count ?? null;
                speciesCount = filters.species?.length ?? null;
                weekCount = heatmap.total_count ?? null;
                recentPhotos = recent.slice(0, 4);
            } catch (error) {
                if (controller.signal.aborted) return;
                // The colophon degrades to prose; the page is still worth reading.
                if (isTransientRequestError(error)) {
                    logger.warn('About summary unavailable', { message: getErrorMessage(error) });
                } else {
                    logger.error('Failed to load About summary', error);
                }
            }
        })();
        return () => controller.abort();
    });

    const repoUrl = 'https://github.com/Jellman86/YetAnother-WhosAtMyFeeder';
    let docsRefBranch = $derived(
        versionInfo.branch && versionInfo.branch !== 'unknown' ? versionInfo.branch : 'main'
    );

    const linkToken = '{link}';
    const splitLinkTemplate = (text: string): LinkParts => {
        const splitAt = text.indexOf(linkToken);
        if (splitAt === -1) {
            return { before: text, after: '' };
        }
        return {
            before: text.slice(0, splitAt),
            after: text.slice(splitAt + linkToken.length)
        };
    };

    let projectDescription = $derived(splitLinkTemplate($_('about.project_desc_1')));
    let creditsLinks = $derived([
        {
            href: 'https://github.com/mmcc-xx/WhosAtMyFeeder',
            label: 'WhosAtMyFeeder',
            parts: splitLinkTemplate($_('about.credits_list.inspiration'))
        },
        {
            href: 'https://frigate.video',
            label: 'Frigate',
            parts: splitLinkTemplate($_('about.credits_list.frigate'))
        },
        {
            href: 'https://github.com/tphakala/birdnet-go',
            label: 'BirdNET-Go',
            parts: splitLinkTemplate($_('about.credits_list.birdnet'))
        },
        {
            href: 'https://youtu.be/hCQCP-5g5bo',
            label: 'Ben Jordan',
            parts: splitLinkTemplate($_('about.credits_list.benjordan'))
        }
    ]);

    let quickActions = $derived([
        {
            href: `${repoUrl}/tree/${docsRefBranch}/docs`,
            label: $_('about.links.docs')
        },
        {
            href: `${repoUrl}/blob/${docsRefBranch}/CHANGELOG.md`,
            label: $_('about.view_changelog')
        },
        {
            href: `${repoUrl}/issues`,
            label: $_('about.links.issues')
        }
    ]);
</script>

<div class="mx-auto max-w-5xl space-y-6">
    <!-- Colophon: what this is, in plain sentences -->
    <section id="about-project" aria-labelledby="about-project-heading" class="card-base space-y-4 p-6">
        <div class="flex items-start gap-4">
            <img src={APP_ICON_192_URL} alt="" class="h-14 w-14 shrink-0 object-contain" />
            <div class="min-w-0">
                <h2 id="about-project-heading" class="font-display text-2xl font-bold text-slate-900 dark:text-white">
                    {$_('app.title')}
                </h2>
                <p class="text-sm text-slate-500 dark:text-slate-400">{$_('app.tagline')}</p>
            </div>
            <a
                href={`${repoUrl}/blob/${docsRefBranch}/CHANGELOG.md`}
                target="_blank"
                rel="noopener noreferrer"
                class="ml-auto shrink-0 rounded-full border border-slate-200/80 px-3 py-1 font-mono text-xs text-slate-600 transition-colors hover:border-brand-300/60 focus-ring dark:border-slate-700 dark:text-slate-300"
                title={$_('about.view_changelog')}
            >
                v{versionInfo.base_version}
            </a>
        </div>

        <div class="space-y-3 text-sm leading-6 text-slate-700 dark:text-slate-300">
            <p>
                {projectDescription.before}<a href="https://github.com/mmcc-xx/WhosAtMyFeeder" target="_blank" rel="noopener noreferrer" class="text-brand-600 hover:underline dark:text-brand-400">WhosAtMyFeeder</a>{projectDescription.after}
            </p>
            <p>{$_('about.project_desc_2')}</p>
        </div>

        {#if totalDetections !== null || recentPhotos.length > 0}
            <div class="grid gap-5 border-t border-slate-200/70 pt-4 sm:grid-cols-[minmax(0,1fr)_auto] dark:border-slate-700/50">
                <dl class="flex flex-wrap gap-x-8 gap-y-3" data-about-stats>
                    <div>
                        <dd class="font-display text-2xl font-bold tabular-nums text-slate-900 dark:text-white">
                            {totalDetections?.toLocaleString() ?? '—'}
                        </dd>
                        <dt class="text-xs text-slate-500 dark:text-slate-400">
                            {$_('about.stats.detections', { default: 'detections stored' })}
                        </dt>
                    </div>
                    <div>
                        <dd class="font-display text-2xl font-bold tabular-nums text-slate-900 dark:text-white">
                            {speciesCount ?? '—'}
                        </dd>
                        <dt class="text-xs text-slate-500 dark:text-slate-400">
                            {$_('about.stats.species', { default: 'species identified' })}
                        </dt>
                    </div>
                    <div>
                        <dd class="font-display text-2xl font-bold tabular-nums text-slate-900 dark:text-white">
                            {weekCount ?? '—'}
                        </dd>
                        <dt class="text-xs text-slate-500 dark:text-slate-400">
                            {$_('about.stats.week', { default: 'visits this week' })}
                        </dt>
                    </div>
                </dl>

                {#if recentPhotos.length > 0}
                    <div class="flex gap-2" data-about-photos>
                        {#each recentPhotos as photo (photo.frigate_event)}
                            <img
                                src={getThumbnailUrl(photo.frigate_event)}
                                alt=""
                                loading="lazy"
                                decoding="async"
                                width="64"
                                height="64"
                                class="h-16 w-16 rounded-xl object-cover"
                            />
                        {/each}
                    </div>
                {/if}
            </div>
        {/if}

        <div class="flex flex-wrap gap-2 pt-1">
            {#each quickActions as action}
                <a
                    href={action.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    class="btn btn-secondary min-h-11 px-3 py-2 text-xs"
                >
                    {action.label}
                </a>
            {/each}
        </div>
    </section>

    <!-- How it works, annotated with what this instance is doing -->
    <section id="about-workflow" aria-labelledby="about-workflow-heading" class="card-base space-y-4 p-6">
        <div>
            <h2 id="about-workflow-heading" class="font-display text-xl font-bold text-slate-900 dark:text-white">
                {$_('about.how_it_works')}
            </h2>
            <p class="mt-1 text-sm text-slate-600 dark:text-slate-400">
                {$_('about.pipeline.subtitle', {
                    default: 'The standard pipeline, showing what this instance is doing.'
                })}
            </p>
        </div>
        <InstancePipeline />
    </section>

    <InstanceSummary {versionInfo} />

    <!-- What it keeps, what it sends, who to thank: one closing row -->
    <section class="card-base p-6" aria-labelledby="about-close-heading">
        <h2 id="about-close-heading" class="sr-only">
            {$_('about.close.title', { default: 'Data, privacy and credits' })}
        </h2>
        <div class="grid gap-8 md:grid-cols-3">
            <PrivacySummary />

            <section aria-labelledby="about-credits-heading">
                <h3 id="about-credits-heading" class="text-sm font-bold text-slate-900 dark:text-white">
                    {$_('about.credits')}
                </h3>
                <ul class="mt-2 space-y-1.5 text-xs text-slate-600 dark:text-slate-300">
                    {#each creditsLinks as credit}
                        <li>
                            {credit.parts.before}<a href={credit.href} target="_blank" rel="noopener noreferrer" class="text-brand-600 hover:underline dark:text-brand-400">{credit.label}</a>{credit.parts.after}
                        </li>
                    {/each}
                    <li>{$_('about.credits_list.ai_assistants')}</li>
                    <li>{$_('about.flaticon_credit')}</li>
                </ul>
                <p class="mt-3 text-[11px] text-slate-500 dark:text-slate-400">
                    {$_('about.license_notice', { values: { year: new Date().getFullYear(), license: $_('common.mit_license') } })}
                </p>
            </section>
        </div>
    </section>
</div>
