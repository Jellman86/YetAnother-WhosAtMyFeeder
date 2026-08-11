<script lang="ts">
    import { fetchVersion, type VersionInfo } from '../api';
    import { APP_ICON_192_URL } from '../assets';
    import InstancePipeline from '../components/InstancePipeline.svelte';
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

    <!-- Build detail, for issue reports -->
    <section id="about-build" aria-labelledby="about-build-heading" class="card-base space-y-3 p-6">
        <h2 id="about-build-heading" class="font-display text-xl font-bold text-slate-900 dark:text-white">
            {$_('about.build.title', { default: 'This build' })}
        </h2>
        <dl class="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-4">
            <div>
                <dt class="text-xs text-slate-500 dark:text-slate-400">{$_('about.build.version', { default: 'Version' })}</dt>
                <dd class="font-mono text-slate-900 dark:text-white">v{versionInfo.base_version}</dd>
            </div>
            <div>
                <dt class="text-xs text-slate-500 dark:text-slate-400">{$_('about.build.branch', { default: 'Branch' })}</dt>
                <dd class="font-mono text-slate-900 dark:text-white">{versionInfo.branch}</dd>
            </div>
            <div>
                <dt class="text-xs text-slate-500 dark:text-slate-400">{$_('about.build.commit', { default: 'Commit' })}</dt>
                <dd class="font-mono text-slate-900 dark:text-white">{versionInfo.git_hash}</dd>
            </div>
            <div>
                <dt class="text-xs text-slate-500 dark:text-slate-400">{$_('about.build.licence', { default: 'Licence' })}</dt>
                <dd class="text-slate-900 dark:text-white">{$_('common.mit_license')}</dd>
            </div>
        </dl>
        <p class="text-xs text-slate-500 dark:text-slate-400">
            {$_('about.build.note', {
                default: 'Include these when reporting an issue. They contain no keys, URLs or camera names.'
            })}
        </p>
    </section>

    <!-- Credits -->
    <section id="about-credits" aria-labelledby="about-credits-heading" class="card-base space-y-3 p-6">
        <h2 id="about-credits-heading" class="font-display text-xl font-bold text-slate-900 dark:text-white">
            {$_('about.credits')}
        </h2>
        <p class="text-sm text-slate-700 dark:text-slate-300">{$_('about.credits_list.preamble')}</p>
        <ul class="space-y-1.5 text-sm text-slate-700 dark:text-slate-300">
            {#each creditsLinks as credit}
                <li>
                    {credit.parts.before}<a href={credit.href} target="_blank" rel="noopener noreferrer" class="text-brand-600 hover:underline dark:text-brand-400">{credit.label}</a>{credit.parts.after}
                </li>
            {/each}
            <li>{$_('about.credits_list.ai_assistants')}</li>
            <li>{$_('about.flaticon_credit')}</li>
        </ul>
        <p class="pt-1 text-xs text-slate-500 dark:text-slate-400">
            {$_('about.license_notice', { values: { year: new Date().getFullYear(), license: $_('common.mit_license') } })}
        </p>
    </section>
</div>
