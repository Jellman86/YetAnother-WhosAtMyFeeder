<script lang="ts">
    import { fetchVersion, type VersionInfo } from '../api';
    import { _ } from 'svelte-i18n';

    type FeatureDefinition = {
        icon: string;
        titleKey: string;
        descriptionKey: string;
        badgeKey?: string;
    };

    type ResourceLinkDefinition = {
        href: string | '__docs__';
        labelKey: string;
        descriptionKey: string;
        iconPath: string;
    };

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

    const featureDefinitions: FeatureDefinition[] = [
        {
            icon: '🤖',
            titleKey: 'about.feature_list.ai_models.title',
            descriptionKey: 'about.feature_list.ai_models.desc'
        },
        {
            icon: '🎵',
            titleKey: 'about.feature_list.multi_sensor.title',
            descriptionKey: 'about.feature_list.multi_sensor.desc'
        },
        {
            icon: '🎬',
            titleKey: 'about.feature_list.video_analysis.title',
            descriptionKey: 'about.feature_list.video_analysis.desc'
        },
        {
            icon: '🔔',
            titleKey: 'about.feature_list.notifications.title',
            descriptionKey: 'about.feature_list.notifications.desc'
        },
        {
            icon: '🧠',
            titleKey: 'about.feature_list.ai_insights.title',
            descriptionKey: 'about.feature_list.ai_insights.desc'
        },
        {
            icon: '🏷️',
            titleKey: 'about.feature_list.taxonomy.title',
            descriptionKey: 'about.feature_list.taxonomy.desc'
        },
        {
            icon: '🌿',
            titleKey: 'about.feature_list.inaturalist_submissions.title',
            descriptionKey: 'about.feature_list.inaturalist_submissions.desc',
            badgeKey: 'about.feature_list.inaturalist_submissions.badge'
        },
        {
            icon: '🌦️',
            titleKey: 'about.feature_list.weather.title',
            descriptionKey: 'about.feature_list.weather.desc'
        },
        {
            icon: '🏠',
            titleKey: 'about.feature_list.home_assistant.title',
            descriptionKey: 'about.feature_list.home_assistant.desc'
        },
        {
            icon: '🌍',
            titleKey: 'about.feature_list.birdweather.title',
            descriptionKey: 'about.feature_list.birdweather.desc'
        },
        {
            icon: '📊',
            titleKey: 'about.feature_list.observability.title',
            descriptionKey: 'about.feature_list.observability.desc'
        },
        {
            icon: '🦝',
            titleKey: 'about.feature_list.wildlife.title',
            descriptionKey: 'about.feature_list.wildlife.desc'
        },
        {
            icon: '⚡',
            titleKey: 'about.feature_list.fast_path.title',
            descriptionKey: 'about.feature_list.fast_path.desc'
        },
        {
            icon: '🔓',
            titleKey: 'about.feature_list.guest_mode.title',
            descriptionKey: 'about.feature_list.guest_mode.desc'
        }
    ];

    let features = $derived(
        featureDefinitions.map((feature) => ({
            icon: feature.icon,
            title: $_(feature.titleKey),
            description: $_(feature.descriptionKey),
            badge: feature.badgeKey ? $_(feature.badgeKey) : undefined
        }))
    );

    let techStack = $derived([
        { category: $_('about.tech.backend'), items: ['Python 3.12', 'FastAPI', 'SQLite', 'Alembic'] },
        { category: $_('about.tech.frontend'), items: ['Svelte 5', 'TypeScript', 'Tailwind CSS', 'Vite'] },
        { category: $_('about.tech.ml'), items: ['ONNX Runtime', 'TensorFlow Lite', 'OpenCV'] },
        { category: $_('about.tech.messaging'), items: ['MQTT (aiomqtt)', 'Server-Sent Events'] },
        { category: $_('about.tech.deployment'), items: ['Docker', 'Docker Compose', 'Nginx'] }
    ]);

    const repoUrl = 'https://github.com/Jellman86/YetAnother-WhosAtMyFeeder';
    let docsRefBranch = $derived(
        versionInfo.branch && versionInfo.branch !== 'unknown' ? versionInfo.branch : 'main'
    );

    const steps = [1, 2, 3, 4, 5, 6, 7, 8];
    const stepColumns = [steps.slice(0, Math.ceil(steps.length / 2)), steps.slice(Math.ceil(steps.length / 2))];

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

    let sectionLinks = $derived([
        { id: 'about-project', label: $_('about.title') },
        { id: 'about-workflow', label: $_('about.how_it_works') },
        { id: 'about-features', label: $_('about.features') },
        { id: 'about-stack', label: $_('about.tech_stack') },
        { id: 'about-docs', label: $_('about.docs_resources') },
        { id: 'about-credits', label: $_('about.credits') }
    ]);

    const resourceLinkDefinitions: ResourceLinkDefinition[] = [
        {
            href: repoUrl,
            labelKey: 'about.links.repo',
            descriptionKey: 'about.links.repo_desc',
            iconPath: 'M10 3.5a6.5 6.5 0 0 1 2.157 12.633c-.157.028-.214-.067-.214-.149 0-.104.004-.445.004-.806 0-.282-.09-.463-.192-.556.63-.07 1.292-.311 1.292-1.403 0-.31-.11-.565-.291-.764.029-.071.126-.357-.028-.744 0 0-.238-.077-.78.292a2.664 2.664 0 0 0-1.422 0c-.542-.369-.78-.292-.78-.292-.154.387-.057.673-.028.744-.181.2-.291.454-.291.764 0 1.09.66 1.333 1.289 1.403a.752.752 0 0 0-.18.498c0 .36.004.702.004.806 0 .082-.057.179-.215.149A6.5 6.5 0 0 1 10 3.5Z'
        },
        {
            href: '__docs__',
            labelKey: 'about.links.docs',
            descriptionKey: 'about.links.docs_desc',
            iconPath: 'M4.75 3.25h7.25a2.5 2.5 0 0 1 2.5 2.5v10a.5.5 0 0 1-.757.429A3.25 3.25 0 0 0 12 15.75H5.5a.75.75 0 0 1-.75-.75v-9.25a2.5 2.5 0 0 1 2.5-2.5Zm7.25 11.25c.921 0 1.812.244 2.593.706a.5.5 0 0 0 .757-.429V6.5a2.25 2.25 0 0 1 2.25-2.25h.75a.5.5 0 0 1 .5.5V15a2.75 2.75 0 0 1-2.75 2.75H12a2.75 2.75 0 0 1-2.75-2.75V14.5H12Z'
        },
        {
            href: 'https://frigate.video',
            labelKey: 'about.links.frigate',
            descriptionKey: 'about.links.frigate_desc',
            iconPath: 'M3.5 5.75A2.25 2.25 0 0 1 5.75 3.5h8.5a2.25 2.25 0 0 1 2.25 2.25v8.5a2.25 2.25 0 0 1-2.25 2.25h-8.5A2.25 2.25 0 0 1 3.5 14.25v-8.5Zm5 2a.75.75 0 0 0-1.125.65v3.2a.75.75 0 0 0 1.125.65l2.8-1.6a.75.75 0 0 0 0-1.3l-2.8-1.6Z'
        },
        {
            href: 'https://github.com/tphakala/birdnet-go',
            labelKey: 'about.links.birdnet',
            descriptionKey: 'about.links.birdnet_desc',
            iconPath: 'M9.75 3.75a.75.75 0 0 1 1.5 0V8a.75.75 0 0 1-1.5 0V3.75Zm-3 2.5a.75.75 0 0 1 1.5 0V8a.75.75 0 0 1-1.5 0V6.25Zm6 0a.75.75 0 0 1 1.5 0V8a.75.75 0 0 1-1.5 0V6.25ZM4.5 10.5a5.5 5.5 0 1 1 11 0v2.25a3.25 3.25 0 0 1-3.25 3.25h-4.5A3.25 3.25 0 0 1 4.5 12.75V10.5Z'
        }
    ];

    let resourceLinks = $derived(
        resourceLinkDefinitions.map((resource) => ({
            ...resource,
            href: resource.href === '__docs__' ? `${repoUrl}/tree/${docsRefBranch}/docs` : resource.href,
            label: $_(resource.labelKey),
            description: $_(resource.descriptionKey)
        }))
    );

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

<div class="max-w-5xl mx-auto space-y-8">
    <!-- Header -->
    <header class="text-center space-y-4">
        <div class="flex items-center justify-center gap-3">
            <div class="w-16 h-16 rounded-2xl bg-transparent border border-slate-200/70 dark:border-slate-700/60 shadow-sm flex items-center justify-center overflow-hidden p-2">
                <img src="/pwa-192x192.png" alt={$_('app.title')} class="w-full h-full object-contain bg-transparent" />
            </div>
        </div>
        <h1 class="text-4xl font-bold text-gradient">{$_('app.logo_title')} {$_('app.logo_subtitle')}</h1>
        <p class="text-lg text-slate-600 dark:text-slate-400">
            {$_('app.tagline')}
        </p>
        <div class="flex items-center justify-center gap-4 text-sm text-slate-500 dark:text-slate-400">
            <a
                href={`${repoUrl}/blob/${docsRefBranch}/CHANGELOG.md`}
                target="_blank"
                rel="noopener noreferrer"
                class="px-3 py-1 rounded-full bg-slate-100 dark:bg-slate-800 font-mono hover:text-brand-600 dark:hover:text-brand-400 transition-colors"
                title={$_('about.view_changelog')}
            >
                v{versionInfo.base_version}
            </a>
            <a
                href="https://github.com/Jellman86/YetAnother-WhosAtMyFeeder"
                target="_blank"
                rel="noopener noreferrer"
                class="flex items-center gap-1.5 hover:text-brand-600 dark:hover:text-brand-400 transition-colors"
            >
                <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path fill-rule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" clip-rule="evenodd" />
                </svg>
                {$_('common.github')}
            </a>
            <span class="text-slate-300 dark:text-slate-600">|</span>
            <span>{$_('common.mit_license')}</span>
        </div>
        <div class="flex flex-wrap items-center justify-center gap-2 pt-1">
            {#each quickActions as action}
                <a
                    href={action.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    class="inline-flex items-center rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 transition-colors hover:border-brand-500 hover:text-brand-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-brand-500 dark:hover:text-brand-300"
                >
                    {action.label}
                </a>
            {/each}
        </div>
    </header>

    <nav aria-label={$_('about.jump_to')} class="card-base p-4">
        <div class="flex flex-wrap items-center justify-center gap-2">
            <span class="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                {$_('about.jump_to')}
            </span>
            {#each sectionLinks as section}
                <a
                    href={`#${section.id}`}
                    class="rounded-full border border-slate-200 px-3 py-1 text-xs font-medium text-slate-700 transition-colors hover:border-brand-500 hover:text-brand-700 dark:border-slate-700 dark:text-slate-300 dark:hover:border-brand-500 dark:hover:text-brand-300"
                >
                    {section.label}
                </a>
            {/each}
        </div>
    </nav>

    <!-- About the Project -->
    <section id="about-project" aria-labelledby="about-project-heading" class="card-base p-6 space-y-4">
        <h2 id="about-project-heading" class="text-2xl font-bold text-slate-900 dark:text-white">{$_('about.title')}</h2>
        <div class="space-y-3 text-slate-700 dark:text-slate-300">
            <p>
                {projectDescription.before}<a href="https://github.com/mmcc-xx/WhosAtMyFeeder" target="_blank" rel="noopener noreferrer" class="text-brand-600 dark:text-brand-400 hover:underline">WhosAtMyFeeder</a>{projectDescription.after}
            </p>
            <p>
                {$_('about.project_desc_2')}
            </p>
        </div>
    </section>

    <!-- How It Works -->
    <section id="about-workflow" aria-labelledby="about-workflow-heading" class="card-base p-6 space-y-4">
        <h2 id="about-workflow-heading" class="text-2xl font-bold text-slate-900 dark:text-white">{$_('about.how_it_works')}</h2>
        <div class="space-y-4">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                {#each stepColumns as column}
                    <div class="space-y-3">
                        {#each column as step}
                            <div class="flex items-start gap-3">
                                <div class="w-8 h-8 rounded-full bg-brand-100 dark:bg-brand-900/30 flex items-center justify-center flex-shrink-0 text-brand-700 dark:text-brand-300 font-bold">{step}</div>
                                <div>
                                    <h3 class="font-semibold text-slate-900 dark:text-white">{$_(`about.steps.${step}.title`)}</h3>
                                    <p class="text-sm text-slate-600 dark:text-slate-400">{$_(`about.steps.${step}.desc`)}</p>
                                </div>
                            </div>
                        {/each}
                    </div>
                {/each}
            </div>
        </div>
    </section>

    <!-- Features Grid -->
    <section id="about-features" aria-labelledby="about-features-heading" class="space-y-4">
        <h2 id="about-features-heading" class="text-2xl font-bold text-slate-900 dark:text-white">{$_('about.features')}</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {#each features as feature}
                <div class="card-base p-4 hover:shadow-card-hover transition-shadow duration-200">
                    <div class="flex items-start gap-3">
                        <span class="inline-flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-brand-100/60 text-base dark:bg-brand-900/30">
                            {feature.icon}
                        </span>
                        <div class="space-y-1">
                            <div class="flex items-center gap-2">
                                <h3 class="font-semibold text-slate-900 dark:text-white text-sm">{feature.title}</h3>
                                {#if feature.badge}
                                    <span class="text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-400/20 dark:text-amber-200">
                                        {feature.badge}
                                    </span>
                                {/if}
                            </div>
                            <p class="text-xs text-slate-600 dark:text-slate-400">{feature.description}</p>
                        </div>
                    </div>
                </div>
            {/each}
        </div>
    </section>

    <!-- Tech Stack -->
    <section id="about-stack" aria-labelledby="about-stack-heading" class="card-base p-6 space-y-4">
        <h2 id="about-stack-heading" class="text-2xl font-bold text-slate-900 dark:text-white">{$_('about.tech_stack')}</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {#each techStack as stack}
                <div class="space-y-2">
                    <h3 class="font-semibold text-brand-700 dark:text-brand-400 text-sm">{stack.category}</h3>
                    <ul class="space-y-1">
                        {#each stack.items as item}
                            <li class="text-sm text-slate-600 dark:text-slate-400 flex items-center gap-2">
                                <span class="w-1 h-1 rounded-full bg-slate-400"></span>
                                {item}
                            </li>
                        {/each}
                    </ul>
                </div>
            {/each}
        </div>
    </section>

    <!-- Documentation & Links -->
    <section id="about-docs" aria-labelledby="about-docs-heading" class="card-base p-6 space-y-4">
        <h2 id="about-docs-heading" class="text-2xl font-bold text-slate-900 dark:text-white">{$_('about.docs_resources')}</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            {#each resourceLinks as resource}
                <a
                    href={resource.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    class="flex items-center gap-3 p-3 rounded-lg border border-slate-200 dark:border-slate-700 hover:border-brand-500 dark:hover:border-brand-500 hover:bg-slate-50 dark:hover:bg-slate-800 transition-all group"
                >
                    <span class="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300">
                        <svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                            <path d={resource.iconPath} />
                        </svg>
                    </span>
                    <div>
                        <div class="font-semibold text-slate-900 dark:text-white group-hover:text-brand-600 dark:group-hover:text-brand-400">{resource.label}</div>
                        <div class="text-xs text-slate-500 dark:text-slate-400">{resource.description}</div>
                    </div>
                </a>
            {/each}
        </div>
    </section>

    <!-- Credits -->
    <section id="about-credits" aria-labelledby="about-credits-heading" class="card-base p-6 space-y-4">
        <h2 id="about-credits-heading" class="text-2xl font-bold text-slate-900 dark:text-white">{$_('about.credits')}</h2>
        <div class="space-y-2 text-sm text-slate-700 dark:text-slate-300">
            <p>{$_('about.credits_list.preamble')}</p>
            <ul class="list-disc list-inside space-y-1 ml-4">
                {#each creditsLinks as credit}
                    <li>
                        {credit.parts.before}<a href={credit.href} target="_blank" rel="noopener noreferrer" class="text-brand-600 dark:text-brand-400 hover:underline">{credit.label}</a>{credit.parts.after}
                    </li>
                {/each}
                <li>{$_('about.credits_list.ai_assistants')}</li>
                <li>
                    <a href="https://www.flaticon.com/free-icons/bird" target="_blank" rel="noopener noreferrer" class="text-brand-600 dark:text-brand-400 hover:underline">
                        {$_('about.flaticon_credit')}
                    </a>
                </li>
            </ul>
        </div>
    </section>

    <!-- License -->
    <footer class="text-center text-sm text-slate-500 dark:text-slate-400 py-4">
        <p>{$_('about.license_notice', { values: { year: new Date().getFullYear(), license: $_('common.mit_license') } })}</p>
        <p class="mt-1">{$_('about.built_with_ai')}</p>
    </footer>
</div>
