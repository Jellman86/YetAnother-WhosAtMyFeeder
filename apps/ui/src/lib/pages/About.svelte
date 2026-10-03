<script lang="ts">
    import { fetchVersion, type VersionInfo } from '../api';
    import { docsRefForBranch } from '../app/app-version';
    import { APP_ICON_192_URL } from '../assets';
    import InstancePipeline from '../components/InstancePipeline.svelte';
    import InstanceSummary from '../components/InstanceSummary.svelte';
    import PrivacySummary from '../components/PrivacySummary.svelte';
    import { onMount } from 'svelte';
    import { fetchClassifierLabels, fetchCommunityStats, fetchEvents, fetchFeederPortrait } from '../api';
    import type { Detection, FeederPortrait as FeederPortraitData } from '../api';
    import FeederPortrait from '../components/FeederPortrait.svelte';
    import DetectionModal from '../components/DetectionModal.svelte';
    import SpeciesDetailModal from '../components/SpeciesDetailModal.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { detectionsStore } from '../stores/detections.svelte';
    import { settingsStore } from '../stores/settings.svelte';
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

    // The opener states what this feeder has recorded, not what the software can do, beside
    // its latest visit. The wider count is how many installs reported to telemetry this week.
    let portrait = $state.raw<FeederPortraitData | null>(null);
    let communityInstalls = $state<number | null>(null);
    let communityReadEnabled = $state<boolean | null>(null);
    let selectedEvent = $state<Detection | null>(null);
    let selectedSpecies = $state<string | null>(null);
    let openingEvent = $state<string | null>(null);
    let classifierLabels = $state<string[]>([]);
    let portraitRefresh = $state(0);
    let portraitGeneration = 0;

    async function openVisit(frigateEvent: string) {
        if (openingEvent) return;
        openingEvent = frigateEvent;
        try {
            const [labels, rows] = await Promise.all([
                authStore.hasOwnerAccess && classifierLabels.length === 0
                    ? fetchClassifierLabels().catch(() => ({ labels: [] as string[] }))
                    : Promise.resolve({ labels: classifierLabels }),
                fetchEvents({ eventId: frigateEvent, limit: 1 })
            ]);
            classifierLabels = labels.labels ?? [];
            const detection = rows[0] ?? null;
            if (!detection) {
                toastStore.error($_('about.portrait.gone', { default: 'That visit is no longer in the history.' }));
                return;
            }
            selectedEvent = detection;
        } catch (error) {
            toastStore.error(getErrorMessage(error) || $_('common.error', { default: 'Action failed' }));
        } finally {
            openingEvent = null;
        }
    }

    async function loadPortrait(signal: AbortSignal, generation: number): Promise<void> {
        try {
            const next = await fetchFeederPortrait(signal);
            if (!signal.aborted && generation === portraitGeneration) portrait = next;
        } catch (error) {
            if (signal.aborted || generation !== portraitGeneration) return;
            // Without the portrait the page is still worth reading; it opens on the prose.
            if (isTransientRequestError(error)) {
                logger.warn('Feeder portrait unavailable', { message: getErrorMessage(error) });
            } else {
                logger.error('Failed to load the feeder portrait', error);
            }
        }
    }

    $effect(() => {
        const publicVersion = authStore.isGuest ? detectionsStore.publicHistoryVersion : 0;
        void publicVersion;
        void portraitRefresh;
        const generation = ++portraitGeneration;
        const controller = new AbortController();
        // A hidden or deleted visit must leave the page, including its downloaded film,
        // before a new public projection arrives. A failed refresh stays clear.
        portrait = null;
        void loadPortrait(controller.signal, generation);
        return () => {
            controller.abort();
            if (generation === portraitGeneration) portraitGeneration += 1;
        };
    });

    onMount(() => {
        const controller = new AbortController();
        // Each read degrades on its own: a portrait without the community count, or the
        // count without a portrait, is still an About page.
        void fetchCommunityStats()
            .then((stats) => {
                if (controller.signal.aborted) return;
                communityInstalls = stats.active_installs ?? null;
                communityReadEnabled = stats.enabled;
            })
            .catch((error) => logger.warn('Community count unavailable', { message: getErrorMessage(error) }));
        return () => controller.abort();
    });

    function forgetVisit(frigateEvent: string): void {
        // The latest visit was deleted or hidden: the facts and the visit beside them move on.
        if (portrait?.latest_visit?.frigate_event === frigateEvent) portraitRefresh += 1;
    }

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

        {#if portrait}
            <FeederPortrait
                {portrait}
                {communityInstalls}
                {openingEvent}
                onopenvisit={openVisit}
                onopenspecies={(name) => (selectedSpecies = name)}
            />
        {/if}

        <div class="space-y-3 text-sm leading-6 text-slate-700 dark:text-slate-300">
            <p>{$_('about.project_desc_2')}</p>
            <p>
                {projectDescription.before}<a href="https://github.com/mmcc-xx/WhosAtMyFeeder" target="_blank" rel="noopener noreferrer" class="text-brand-600 hover:underline dark:text-brand-400">WhosAtMyFeeder</a>{projectDescription.after}
            </p>
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
        onDeleteSuccess={(frigateEvent: string) => forgetVisit(frigateEvent)}
        onHideSuccess={(frigateEvent: string, _time: string | undefined, isHidden: boolean) => {
            if (isHidden) forgetVisit(frigateEvent);
        }}
    />
{/if}
{#if selectedSpecies}<SpeciesDetailModal speciesName={selectedSpecies} onclose={() => (selectedSpecies = null)} />{/if}
