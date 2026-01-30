<script lang="ts">
    import { onMount } from 'svelte';
    import { fetchVersion, type VersionInfo } from '../api';
    import { _ } from 'svelte-i18n';

    const appVersion = typeof __APP_VERSION__ === 'string' ? __APP_VERSION__ : 'unknown';
    const appVersionBase = appVersion.includes('+') ? appVersion.split('+')[0] : appVersion;
    let versionInfo = $state<VersionInfo>({
        version: appVersion,
        base_version: appVersionBase,
        git_hash: __GIT_HASH__
    });

    $effect(() => {
        (async () => {
            try {
                const info = await fetchVersion();
                versionInfo = info;
            } catch (e) {
                console.error('Failed to fetch version info', e);
            }
        })();
    });

    let features = $derived([
        {
            icon: '🤖',
            title: $_('about.feature_list.ai_models.title'),
            description: $_('about.feature_list.ai_models.desc')
        },
        {
            icon: '🎵',
            title: $_('about.feature_list.multi_sensor.title'),
            description: $_('about.feature_list.multi_sensor.desc')
        },
        {
            icon: '🎬',
            title: $_('about.feature_list.video_analysis.title'),
            description: $_('about.feature_list.video_analysis.desc')
        },
        {
            icon: '🔔',
            title: $_('about.feature_list.notifications.title'),
            description: $_('about.feature_list.notifications.desc')
        },
        {
            icon: '🧠',
            title: $_('about.feature_list.ai_insights.title'),
            description: $_('about.feature_list.ai_insights.desc')
        },
        {
            icon: '🏷️',
            title: $_('about.feature_list.taxonomy.title'),
            description: $_('about.feature_list.taxonomy.desc')
        },
        {
            icon: '🌦️',
            title: $_('about.feature_list.weather.title'),
            description: $_('about.feature_list.weather.desc')
        },
        {
            icon: '🏠',
            title: $_('about.feature_list.home_assistant.title'),
            description: $_('about.feature_list.home_assistant.desc')
        },
        {
            icon: '🌍',
            title: $_('about.feature_list.birdweather.title'),
            description: $_('about.feature_list.birdweather.desc')
        },
        {
            icon: '📊',
            title: $_('about.feature_list.observability.title'),
            description: $_('about.feature_list.observability.desc')
        },
        {
            icon: '⚡',
            title: $_('about.feature_list.fast_path.title'),
            description: $_('about.feature_list.fast_path.desc')
        },
        {
            icon: '🔓',
            title: $_('about.feature_list.guest_mode.title'),
            description: $_('about.feature_list.guest_mode.desc')
        }
    ]);

    let techStack = $derived([
        { category: $_('about.tech.backend'), items: ['Python 3.12', 'FastAPI', 'SQLite', 'Alembic'] },
        { category: $_('about.tech.frontend'), items: ['Svelte 5', 'TypeScript', 'Tailwind CSS', 'Vite'] },
        { category: $_('about.tech.ml'), items: ['ONNX Runtime', 'TensorFlow Lite', 'OpenCV'] },
        { category: $_('about.tech.messaging'), items: ['MQTT (aiomqtt)', 'Server-Sent Events'] },
        { category: $_('about.tech.deployment'), items: ['Docker', 'Docker Compose', 'Nginx'] }
    ]);

    const steps = [1, 2, 3, 4, 5, 6, 7, 8];
</script>

<div class="max-w-5xl mx-auto space-y-8">
    <!-- Header -->
    <div class="text-center space-y-4">
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
                href="https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/blob/dev/CHANGELOG.md"
                target="_blank"
                rel="noopener noreferrer"
                class="px-3 py-1 rounded-full bg-slate-100 dark:bg-slate-800 font-mono hover:text-brand-600 dark:hover:text-brand-400 transition-colors"
                title="View changelog"
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
    </div>

    <!-- About the Project -->
    <div class="card-base p-6 space-y-4">
        <h2 class="text-2xl font-bold text-slate-900 dark:text-white">{$_('about.title')}</h2>
        <div class="space-y-3 text-slate-700 dark:text-slate-300">
            <p>
                {@html $_('about.project_desc_1', { values: { 
                    link: `<a href="https://github.com/mmcc-xx/WhosAtMyFeeder" target="_blank" rel="noopener noreferrer" class="text-brand-600 dark:text-brand-400 hover:underline">WhosAtMyFeeder</a>` 
                } })}
            </p>
            <p>
                {$_('about.project_desc_2')}
            </p>
        </div>
    </div>

    <!-- How It Works -->
    <div class="card-base p-6 space-y-4">
        <h2 class="text-2xl font-bold text-slate-900 dark:text-white">{$_('about.how_it_works')}</h2>
        <div class="space-y-4">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div class="space-y-3">
                    {#each steps.slice(0, 4) as step}
                        <div class="flex items-start gap-3">
                            <div class="w-8 h-8 rounded-full bg-brand-100 dark:bg-brand-900/30 flex items-center justify-center flex-shrink-0 text-brand-700 dark:text-brand-300 font-bold">{step}</div>
                            <div>
                                <h3 class="font-semibold text-slate-900 dark:text-white">{$_(`about.steps.${step}.title`)}</h3>
                                <p class="text-sm text-slate-600 dark:text-slate-400">{$_(`about.steps.${step}.desc`)}</p>
                            </div>
                        </div>
                    {/each}
                </div>
                <div class="space-y-3">
                    {#each steps.slice(4, 8) as step}
                        <div class="flex items-start gap-3">
                            <div class="w-8 h-8 rounded-full bg-brand-100 dark:bg-brand-900/30 flex items-center justify-center flex-shrink-0 text-brand-700 dark:text-brand-300 font-bold">{step}</div>
                            <div>
                                <h3 class="font-semibold text-slate-900 dark:text-white">{$_(`about.steps.${step}.title`)}</h3>
                                <p class="text-sm text-slate-600 dark:text-slate-400">{$_(`about.steps.${step}.desc`)}</p>
                            </div>
                        </div>
                    {/each}
                </div>
            </div>
        </div>
    </div>

    <!-- Features Grid -->
    <div class="space-y-4">
        <h2 class="text-2xl font-bold text-slate-900 dark:text-white">{$_('about.features')}</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {#each features as feature}
                <div class="card-base p-4 hover:shadow-card-hover transition-shadow duration-200">
                    <div class="flex items-start gap-3">
                        <span class="text-3xl flex-shrink-0">{feature.icon}</span>
                        <div class="space-y-1">
                            <h3 class="font-semibold text-slate-900 dark:text-white text-sm">{feature.title}</h3>
                            <p class="text-xs text-slate-600 dark:text-slate-400">{feature.description}</p>
                        </div>
                    </div>
                </div>
            {/each}
        </div>
    </div>

    <!-- Tech Stack -->
    <div class="card-base p-6 space-y-4">
        <h2 class="text-2xl font-bold text-slate-900 dark:text-white">{$_('about.tech_stack')}</h2>
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
    </div>

    <!-- Documentation & Links -->
    <div class="card-base p-6 space-y-4">
        <h2 class="text-2xl font-bold text-slate-900 dark:text-white">{$_('about.docs_resources')}</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <a href="https://github.com/Jellman86/YetAnother-WhosAtMyFeeder" target="_blank" rel="noopener noreferrer"
               class="flex items-center gap-3 p-3 rounded-lg border border-slate-200 dark:border-slate-700 hover:border-brand-500 dark:hover:border-brand-500 hover:bg-slate-50 dark:hover:bg-slate-800 transition-all group">
                <span class="text-2xl">📚</span>
                <div>
                    <div class="font-semibold text-slate-900 dark:text-white group-hover:text-brand-600 dark:group-hover:text-brand-400">{$_('about.links.repo')}</div>
                    <div class="text-xs text-slate-500 dark:text-slate-400">{$_('about.links.repo_desc')}</div>
                </div>
            </a>
            <a href="https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/tree/main/docs" target="_blank" rel="noopener noreferrer"
               class="flex items-center gap-3 p-3 rounded-lg border border-slate-200 dark:border-slate-700 hover:border-brand-500 dark:hover:border-brand-500 hover:bg-slate-50 dark:hover:bg-slate-800 transition-all group">
                <span class="text-2xl">📖</span>
                <div>
                    <div class="font-semibold text-slate-900 dark:text-white group-hover:text-brand-600 dark:group-hover:text-brand-400">{$_('about.links.docs')}</div>
                    <div class="text-xs text-slate-500 dark:text-slate-400">{$_('about.links.docs_desc')}</div>
                </div>
            </a>
            <a href="https://frigate.video" target="_blank" rel="noopener noreferrer"
               class="flex items-center gap-3 p-3 rounded-lg border border-slate-200 dark:border-slate-700 hover:border-brand-500 dark:hover:border-brand-500 hover:bg-slate-50 dark:hover:bg-slate-800 transition-all group">
                <span class="text-2xl">📹</span>
                <div>
                    <div class="font-semibold text-slate-900 dark:text-white group-hover:text-brand-600 dark:group-hover:text-brand-400">{$_('about.links.frigate')}</div>
                    <div class="text-xs text-slate-500 dark:text-slate-400">{$_('about.links.frigate_desc')}</div>
                </div>
            </a>
            <a href="https://github.com/tphakala/birdnet-go" target="_blank" rel="noopener noreferrer"
               class="flex items-center gap-3 p-3 rounded-lg border border-slate-200 dark:border-slate-700 hover:border-brand-500 dark:hover:border-brand-500 hover:bg-slate-50 dark:hover:bg-slate-800 transition-all group">
                <span class="text-2xl">🎵</span>
                <div>
                    <div class="font-semibold text-slate-900 dark:text-white group-hover:text-brand-600 dark:group-hover:text-brand-400">{$_('about.links.birdnet')}</div>
                    <div class="text-xs text-slate-500 dark:text-slate-400">{$_('about.links.birdnet_desc')}</div>
                </div>
            </a>
        </div>
    </div>

    <!-- Credits -->
    <div class="card-base p-6 space-y-4">
        <h2 class="text-2xl font-bold text-slate-900 dark:text-white">{$_('about.credits')}</h2>
        <div class="space-y-2 text-sm text-slate-700 dark:text-slate-300">
            <p>{$_('about.credits_list.preamble')}</p>
            <ul class="list-disc list-inside space-y-1 ml-4">
                <li>
                    {@html $_('about.credits_list.inspiration', { values: { 
                        link: `<a href="https://github.com/mmcc-xx/WhosAtMyFeeder" target="_blank" rel="noopener noreferrer" class="text-brand-600 dark:text-brand-400 hover:underline">WhosAtMyFeeder</a>` 
                    } })}
                </li>
                <li>
                    {@html $_('about.credits_list.frigate', { values: { 
                        link: `<a href="https://frigate.video" target="_blank" rel="noopener noreferrer" class="text-brand-600 dark:text-brand-400 hover:underline">Frigate</a>` 
                    } })}
                </li>
                <li>
                    {@html $_('about.credits_list.birdnet', { values: { 
                        link: `<a href="https://github.com/tphakala/birdnet-go" target="_blank" rel="noopener noreferrer" class="text-brand-600 dark:text-brand-400 hover:underline">BirdNET-Go</a>` 
                    } })}
                </li>
                <li>
                    {@html $_('about.credits_list.benjordan', { values: { 
                        link: `<a href="https://youtu.be/hCQCP-5g5bo" target="_blank" rel="noopener noreferrer" class="text-brand-600 dark:text-brand-400 hover:underline">Ben Jordan</a>` 
                    } })}
                </li>
                <li>{$_('about.credits_list.ai_assistants')}</li>
                <li>
                    <a href="https://www.flaticon.com/free-icons/bird" title="bird icons" target="_blank" rel="noopener noreferrer" class="text-brand-600 dark:text-brand-400 hover:underline">
                        Bird icons created by Freepik - Flaticon
                    </a>
                </li>
            </ul>
        </div>
    </div>

    <!-- License -->
    <div class="text-center text-sm text-slate-500 dark:text-slate-400 py-4">
        <p>© {new Date().getFullYear()} Jellman86 • Licensed under the {$_('common.mit_license')}</p>
        <p class="mt-1">{$_('about.built_with_ai')}</p>
    </div>
</div>

<style>
    .shadow-glow {
        box-shadow: 0 0 20px -5px rgba(20, 184, 166, 0.5);
    }
</style>
