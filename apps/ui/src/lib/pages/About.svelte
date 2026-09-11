<script lang="ts">
    import { fetchVersion, type VersionInfo } from '../api';
    import { docsRefForBranch } from '../app/app-version';
    import { APP_ICON_192_URL } from '../assets';
    import InstancePipeline from '../components/InstancePipeline.svelte';
    import InstanceSummary from '../components/InstanceSummary.svelte';
    import PrivacySummary from '../components/PrivacySummary.svelte';
    import { onMount } from 'svelte';
    import {
        fetchAboutShowcase,
        fetchClassifierLabels,
        fetchCommunityStats,
        fetchEvents,
        fetchEventFilters,
        fetchEventsCount
    } from '../api';
    import type { AboutShowcaseItem, Detection } from '../api';
    import CaptureReel from '../components/CaptureReel.svelte';
    import DetectionModal from '../components/DetectionModal.svelte';
    import SpeciesDetailModal from '../components/SpeciesDetailModal.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { settingsStore } from '../stores/settings.svelte';
    import { fetchDetectionsActivityHeatmapSpan } from '../api/leaderboard';
    import { getErrorMessage, isTransientRequestError } from '../utils/error-handling';
    import { toastStore } from '../stores/toast.svelte';
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
    // The opener: this install's own photographs, one crop per species, each opening its
    // record. The wider count is how many installs reported to telemetry this week.
    let showcase = $state<AboutShowcaseItem[]>([]);
    let communityInstalls = $state<number | null>(null);
    let communityReadEnabled = $state<boolean | null>(null);
    let selectedEvent = $state<Detection | null>(null);
    let selectedSpecies = $state<string | null>(null);
    let openingEvent = $state<string | null>(null);
    let classifierLabels = $state<string[]>([]);

    async function openCapture(item: AboutShowcaseItem) {
        if (openingEvent) return;
        openingEvent = item.frigate_event;
        try {
            const [labels, rows] = await Promise.all([
                authStore.hasOwnerAccess && classifierLabels.length === 0
                    ? fetchClassifierLabels().catch(() => ({ labels: [] as string[] }))
                    : Promise.resolve({ labels: classifierLabels }),
                fetchEvents({ eventId: item.frigate_event, limit: 1 })
            ]);
            classifierLabels = labels.labels ?? [];
            const detection = rows[0] ?? null;
            if (!detection) {
                toastStore.error($_('about.opener.gone', { default: 'That visit is no longer in the history.' }));
                return;
            }
            selectedEvent = detection;
        } catch (error) {
            toastStore.error(getErrorMessage(error) || $_('common.error', { default: 'Action failed' }));
        } finally {
            openingEvent = null;
        }
    }

    onMount(() => {
        const controller = new AbortController();
        // Each read degrades on its own: a reel without a count, or a count without a reel,
        // is still an About page.
        void fetchAboutShowcase()
            .then((response) => {
                if (!controller.signal.aborted) showcase = response.items;
            })
            .catch((error) => logger.warn('About reel unavailable', { message: getErrorMessage(error) }));
        void fetchCommunityStats()
            .then((stats) => {
                if (controller.signal.aborted) return;
                communityInstalls = stats.active_installs ?? null;
                communityReadEnabled = stats.enabled;
            })
            .catch((error) => logger.warn('Community count unavailable', { message: getErrorMessage(error) }));
        void (async () => {
            try {
                const [count, filters, heatmap] = await Promise.all([
                    fetchEventsCount(),
                    fetchEventFilters(),
                    fetchDetectionsActivityHeatmapSpan('week')
                ]);
                if (controller.signal.aborted) return;
                totalDetections = count.count ?? null;
                speciesCount = filters.species?.length ?? null;
                weekCount = heatmap.total_count ?? null;
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
    let docsRefBranch = $derived(docsRefForBranch(versionInfo.branch));

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

<!-- No self-imposed width: the owner PageHeader above uses the shell width, and a
     narrower page below it reads as a mismatched second header. -->
<div class="space-y-6">
    <!-- Colophon: what this is, in plain sentences -->
    <section id="about-project" aria-labelledby="about-project-heading" class="space-y-4 px-1 pt-2">
        <div class="flex items-start gap-4">
            <div class="min-w-0">
                <!-- The PageHeader already says "About" for owners; repeating it here was the
                     second half of the doubled heading. -->
                <h2 id="about-project-heading" class="font-display text-3xl font-bold leading-tight text-slate-900 dark:text-white">
                    {$_('app.full_title', { default: 'Yet Another WhosAtMyFeeder' })}
                </h2>
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

        {#if showcase.length > 0}
            <div class="-mx-1 sm:-mx-2" data-about-opener>
                <CaptureReel items={showcase} {openingEvent} onopen={openCapture} />
                <p class="mt-2 px-1 text-sm text-slate-500 dark:text-slate-400 sm:px-2" data-about-opener-caption>
                    {$_('about.opener.caption', { default: 'Some of them even sat still for a photo.' })}
                </p>
            </div>
        {/if}

        <div class="space-y-3 text-sm leading-6 text-slate-700 dark:text-slate-300">
            <p>{$_('about.project_desc_2')}</p>
            <p>
                {projectDescription.before}<a href="https://github.com/mmcc-xx/WhosAtMyFeeder" target="_blank" rel="noopener noreferrer" class="text-brand-600 hover:underline dark:text-brand-400">WhosAtMyFeeder</a>{projectDescription.after}
            </p>
        </div>

        {#if totalDetections !== null}
            <div class="border-t border-slate-200/70 pt-4 dark:border-slate-700/50">
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
                    {#if communityInstalls !== null}
                        <div data-about-community>
                            <dd class="font-display text-2xl font-bold tabular-nums text-slate-900 dark:text-white">
                                {communityInstalls.toLocaleString()}
                            </dd>
                            <dt class="text-xs text-slate-500 dark:text-slate-400">
                                {$_('about.stats.feeders', { default: 'feeders ran it this week' })}
                            </dt>
                        </div>
                    {/if}
                </dl>
            </div>
        {/if}

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
            <PrivacySummary {communityReadEnabled} />

            <section aria-labelledby="about-credits-heading">
                <h3 id="about-credits-heading" class="text-sm font-bold text-slate-900 dark:text-white">
                    {$_('about.reference_thanks', { default: 'Reference & thanks' })}
                </h3>
                <ul class="mt-2 space-y-1.5 text-xs">
                    {#each quickActions as action}
                        <li>
                            <a
                                href={action.href}
                                target="_blank"
                                rel="noopener noreferrer"
                                class="group inline-flex items-center gap-1.5 text-brand-600 focus-ring dark:text-brand-400"
                            >
                                <span class="group-hover:underline">{action.label}</span>
                                <!-- Sized in the icon rather than left to the display font, which
                                     rendered the bare arrow glyph far larger than its label. -->
                                <svg
                                    class="h-2.5 w-2.5 shrink-0 text-slate-400 dark:text-slate-500"
                                    viewBox="0 0 12 12"
                                    fill="none"
                                    stroke="currentColor"
                                    stroke-width="1.6"
                                    aria-hidden="true"
                                >
                                    <path stroke-linecap="round" stroke-linejoin="round" d="M4.25 2.75h5v5" />
                                    <path stroke-linecap="round" stroke-linejoin="round" d="M9.25 2.75 2.75 9.25" />
                                </svg>
                            </a>
                        </li>
                    {/each}
                </ul>

                <p class="mt-4 text-xs font-semibold text-slate-800 dark:text-slate-100">
                    {$_('about.thanks_to', { default: 'Thanks to' })}
                </p>
                <ul class="mt-1 space-y-1 text-xs text-slate-600 dark:text-slate-300">
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

{#if selectedEvent}
    <DetectionModal
        detection={selectedEvent}
        {classifierLabels}
        llmReady={settingsStore.llmReady}
        showVideoButton={false}
        readOnly={!authStore.hasOwnerAccess}
        onClose={() => (selectedEvent = null)}
        onViewSpecies={(species: string) => { selectedSpecies = species; selectedEvent = null; }}
        onDeleteSuccess={(frigateEvent: string) => { showcase = showcase.filter((item) => item.frigate_event !== frigateEvent); }}
        onHideSuccess={(frigateEvent: string, _time: string | undefined, isHidden: boolean) => {
            if (isHidden) showcase = showcase.filter((item) => item.frigate_event !== frigateEvent);
        }}
    />
{/if}
{#if selectedSpecies}<SpeciesDetailModal speciesName={selectedSpecies} onclose={() => (selectedSpecies = null)} />{/if}
