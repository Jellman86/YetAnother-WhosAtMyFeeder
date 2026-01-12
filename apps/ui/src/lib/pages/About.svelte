<script lang="ts">
    import { onMount } from 'svelte';
    import { fetchVersion, type VersionInfo } from '../api';

    let versionInfo = $state<VersionInfo>({
        version: __APP_VERSION__,
        base_version: __APP_VERSION__.split('+')[0],
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

    const features = [
        {
            icon: '🤖',
            title: 'Advanced AI Models',
            description: 'Choose from MobileNetV2 (fast), ConvNeXt (high accuracy), or EVA-02 (elite ~91% accuracy)'
        },
        {
            icon: '🎵',
            title: 'Multi-Sensor Correlation',
            description: 'Cross-reference visual detections with BirdNET-Go audio identifications for verified sightings'
        },
        {
            icon: '🎬',
            title: 'Auto Video Analysis',
            description: 'Automatically scan 15+ frames from video clips for higher accuracy using temporal ensemble logic'
        },
        {
            icon: '🔔',
            title: 'Rich Notifications',
            description: 'Discord, Telegram, and Pushover support with customizable filters and species-specific alerts'
        },
        {
            icon: '🧠',
            title: 'AI Naturalist Insights',
            description: 'Get behavioral analysis of your visitors using Gemini, OpenAI, or Claude language models'
        },
        {
            icon: '🏷️',
            title: 'Taxonomy Normalization',
            description: 'Automatic scientific ↔ common name mapping using iNaturalist data'
        },
        {
            icon: '🌦️',
            title: 'Weather Enrichment',
            description: 'Track detections with local weather conditions and temperature data'
        },
        {
            icon: '🏠',
            title: 'Home Assistant Integration',
            description: 'Native sensors for tracking last detected bird and daily visitor counts'
        },
        {
            icon: '🌍',
            title: 'BirdWeather Reporting',
            description: 'Optional: Contribute your detections to the BirdWeather community science platform'
        },
        {
            icon: '📊',
            title: 'Observability',
            description: 'Built-in Prometheus metrics, optional telemetry, and real-time MQTT diagnostics'
        },
        {
            icon: '🦊',
            title: 'Wildlife Classifier',
            description: 'Identify squirrels, foxes, and other non-bird visitors to your feeder'
        },
        {
            icon: '⚡',
            title: 'Fast Path Efficiency',
            description: 'Skip local AI processing and use Frigate\'s sublabels directly to save CPU resources'
        }
    ];

    const techStack = [
        { category: 'Backend', items: ['Python 3.12', 'FastAPI', 'SQLite', 'Alembic'] },
        { category: 'Frontend', items: ['Svelte 5', 'TypeScript', 'Tailwind CSS', 'Vite'] },
        { category: 'ML Engine', items: ['ONNX Runtime', 'TensorFlow Lite', 'OpenCV'] },
        { category: 'Messaging', items: ['MQTT (aiomqtt)', 'Server-Sent Events'] },
        { category: 'Deployment', items: ['Docker', 'Docker Compose', 'Nginx'] }
    ];
</script>

<div class="max-w-5xl mx-auto space-y-8">
    <!-- Header -->
    <div class="text-center space-y-4">
        <div class="flex items-center justify-center gap-3">
            <div class="w-16 h-16 rounded-2xl bg-gradient-to-br from-brand-500 to-teal-400 flex items-center justify-center shadow-glow">
                <span class="text-3xl">🐦</span>
            </div>
        </div>
        <h1 class="text-4xl font-bold text-gradient">Yet Another WhosAtMyFeeder</h1>
        <p class="text-lg text-slate-600 dark:text-slate-400">
            AI-powered bird classification for your Frigate NVR
        </p>
        <div class="flex items-center justify-center gap-4 text-sm text-slate-500 dark:text-slate-400">
            <span class="px-3 py-1 rounded-full bg-slate-100 dark:bg-slate-800 font-mono">
                v{versionInfo.base_version}
            </span>
            <a
                href="https://github.com/Jellman86/YetAnother-WhosAtMyFeeder"
                target="_blank"
                rel="noopener noreferrer"
                class="flex items-center gap-1.5 hover:text-brand-600 dark:hover:text-brand-400 transition-colors"
            >
                <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path fill-rule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" clip-rule="evenodd" />
                </svg>
                GitHub
            </a>
            <span class="text-slate-300 dark:text-slate-600">|</span>
            <span>MIT License</span>
        </div>
    </div>

    <!-- About the Project -->
    <div class="card p-6 space-y-4">
        <h2 class="text-2xl font-bold text-slate-900 dark:text-white">About This Project</h2>
        <div class="space-y-3 text-slate-700 dark:text-slate-300">
            <p>
                YA-WAMF is a personal project started to experiment with AI-assisted coding. When the original
                <a href="https://github.com/mmcc-xx/WhosAtMyFeeder" target="_blank" rel="noopener noreferrer" class="text-brand-600 dark:text-brand-400 hover:underline">WhosAtMyFeeder</a>
                project became unmaintained, this was born as both a learning opportunity and a useful tool for bird enthusiasts.
            </p>
            <p>
                The entire application has been built with help from AI coding assistants - it's been an interesting exploration of what's possible with these tools.
                If you spot any rough edges, that's probably why!
            </p>
        </div>
    </div>

    <!-- How It Works -->
    <div class="card p-6 space-y-4">
        <h2 class="text-2xl font-bold text-slate-900 dark:text-white">How It Works</h2>
        <div class="space-y-4">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div class="space-y-3">
                    <div class="flex items-start gap-3">
                        <div class="w-8 h-8 rounded-full bg-brand-100 dark:bg-brand-900/30 flex items-center justify-center flex-shrink-0 text-brand-700 dark:text-brand-300 font-bold">1</div>
                        <div>
                            <h3 class="font-semibold text-slate-900 dark:text-white">Frigate Detects</h3>
                            <p class="text-sm text-slate-600 dark:text-slate-400">Your camera picks up movement, Frigate identifies it as a bird</p>
                        </div>
                    </div>
                    <div class="flex items-start gap-3">
                        <div class="w-8 h-8 rounded-full bg-brand-100 dark:bg-brand-900/30 flex items-center justify-center flex-shrink-0 text-brand-700 dark:text-brand-300 font-bold">2</div>
                        <div>
                            <h3 class="font-semibold text-slate-900 dark:text-white">MQTT Message</h3>
                            <p class="text-sm text-slate-600 dark:text-slate-400">Frigate publishes an event to your MQTT broker</p>
                        </div>
                    </div>
                    <div class="flex items-start gap-3">
                        <div class="w-8 h-8 rounded-full bg-brand-100 dark:bg-brand-900/30 flex items-center justify-center flex-shrink-0 text-brand-700 dark:text-brand-300 font-bold">3</div>
                        <div>
                            <h3 class="font-semibold text-slate-900 dark:text-white">YA-WAMF Processes</h3>
                            <p class="text-sm text-slate-600 dark:text-slate-400">The backend subscribes to MQTT and picks up the event</p>
                        </div>
                    </div>
                    <div class="flex items-start gap-3">
                        <div class="w-8 h-8 rounded-full bg-brand-100 dark:bg-brand-900/30 flex items-center justify-center flex-shrink-0 text-brand-700 dark:text-brand-300 font-bold">4</div>
                        <div>
                            <h3 class="font-semibold text-slate-900 dark:text-white">Classification</h3>
                            <p class="text-sm text-slate-600 dark:text-slate-400">Image runs through ML model (or uses Frigate's sublabel)</p>
                        </div>
                    </div>
                </div>
                <div class="space-y-3">
                    <div class="flex items-start gap-3">
                        <div class="w-8 h-8 rounded-full bg-brand-100 dark:bg-brand-900/30 flex items-center justify-center flex-shrink-0 text-brand-700 dark:text-brand-300 font-bold">5</div>
                        <div>
                            <h3 class="font-semibold text-slate-900 dark:text-white">Audio Correlation</h3>
                            <p class="text-sm text-slate-600 dark:text-slate-400">Cross-references with BirdNET-Go audio detections if available</p>
                        </div>
                    </div>
                    <div class="flex items-start gap-3">
                        <div class="w-8 h-8 rounded-full bg-brand-100 dark:bg-brand-900/30 flex items-center justify-center flex-shrink-0 text-brand-700 dark:text-brand-300 font-bold">6</div>
                        <div>
                            <h3 class="font-semibold text-slate-900 dark:text-white">Save & Notify</h3>
                            <p class="text-sm text-slate-600 dark:text-slate-400">Detection stored to database, notifications sent</p>
                        </div>
                    </div>
                    <div class="flex items-start gap-3">
                        <div class="w-8 h-8 rounded-full bg-brand-100 dark:bg-brand-900/30 flex items-center justify-center flex-shrink-0 text-brand-700 dark:text-brand-300 font-bold">7</div>
                        <div>
                            <h3 class="font-semibold text-slate-900 dark:text-white">Video Analysis</h3>
                            <p class="text-sm text-slate-600 dark:text-slate-400">Optional: Scans video clip frames for refined accuracy</p>
                        </div>
                    </div>
                    <div class="flex items-start gap-3">
                        <div class="w-8 h-8 rounded-full bg-brand-100 dark:bg-brand-900/30 flex items-center justify-center flex-shrink-0 text-brand-700 dark:text-brand-300 font-bold">8</div>
                        <div>
                            <h3 class="font-semibold text-slate-900 dark:text-white">Live Updates</h3>
                            <p class="text-sm text-slate-600 dark:text-slate-400">Dashboard receives real-time updates via Server-Sent Events</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Features Grid -->
    <div class="space-y-4">
        <h2 class="text-2xl font-bold text-slate-900 dark:text-white">Features</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {#each features as feature}
                <div class="card p-4 hover:shadow-lg transition-shadow duration-200">
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
    <div class="card p-6 space-y-4">
        <h2 class="text-2xl font-bold text-slate-900 dark:text-white">Technology Stack</h2>
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
    <div class="card p-6 space-y-4">
        <h2 class="text-2xl font-bold text-slate-900 dark:text-white">Documentation & Resources</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <a href="https://github.com/Jellman86/YetAnother-WhosAtMyFeeder" target="_blank" rel="noopener noreferrer"
               class="flex items-center gap-3 p-3 rounded-lg border border-slate-200 dark:border-slate-700 hover:border-brand-500 dark:hover:border-brand-500 hover:bg-slate-50 dark:hover:bg-slate-800 transition-all group">
                <span class="text-2xl">📚</span>
                <div>
                    <div class="font-semibold text-slate-900 dark:text-white group-hover:text-brand-600 dark:group-hover:text-brand-400">GitHub Repository</div>
                    <div class="text-xs text-slate-500 dark:text-slate-400">Source code, issues, and releases</div>
                </div>
            </a>
            <a href="https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/tree/main/docs" target="_blank" rel="noopener noreferrer"
               class="flex items-center gap-3 p-3 rounded-lg border border-slate-200 dark:border-slate-700 hover:border-brand-500 dark:hover:border-brand-500 hover:bg-slate-50 dark:hover:bg-slate-800 transition-all group">
                <span class="text-2xl">📖</span>
                <div>
                    <div class="font-semibold text-slate-900 dark:text-white group-hover:text-brand-600 dark:group-hover:text-brand-400">Documentation</div>
                    <div class="text-xs text-slate-500 dark:text-slate-400">Setup guides, API reference, and troubleshooting</div>
                </div>
            </a>
            <a href="https://frigate.video" target="_blank" rel="noopener noreferrer"
               class="flex items-center gap-3 p-3 rounded-lg border border-slate-200 dark:border-slate-700 hover:border-brand-500 dark:hover:border-brand-500 hover:bg-slate-50 dark:hover:bg-slate-800 transition-all group">
                <span class="text-2xl">📹</span>
                <div>
                    <div class="font-semibold text-slate-900 dark:text-white group-hover:text-brand-600 dark:group-hover:text-brand-400">Frigate NVR</div>
                    <div class="text-xs text-slate-500 dark:text-slate-400">Required: Open-source NVR with object detection</div>
                </div>
            </a>
            <a href="https://github.com/tphakala/birdnet-go" target="_blank" rel="noopener noreferrer"
               class="flex items-center gap-3 p-3 rounded-lg border border-slate-200 dark:border-slate-700 hover:border-brand-500 dark:hover:border-brand-500 hover:bg-slate-50 dark:hover:bg-slate-800 transition-all group">
                <span class="text-2xl">🎵</span>
                <div>
                    <div class="font-semibold text-slate-900 dark:text-white group-hover:text-brand-600 dark:group-hover:text-brand-400">BirdNET-Go</div>
                    <div class="text-xs text-slate-500 dark:text-slate-400">Optional: Audio bird identification</div>
                </div>
            </a>
        </div>
    </div>

    <!-- Credits -->
    <div class="card p-6 space-y-4">
        <h2 class="text-2xl font-bold text-slate-900 dark:text-white">Credits & Thanks</h2>
        <div class="space-y-2 text-sm text-slate-700 dark:text-slate-300">
            <p>This project wouldn't be possible without:</p>
            <ul class="list-disc list-inside space-y-1 ml-4">
                <li>The original <a href="https://github.com/mmcc-xx/WhosAtMyFeeder" target="_blank" rel="noopener noreferrer" class="text-brand-600 dark:text-brand-400 hover:underline">WhosAtMyFeeder</a> project for the inspiration</li>
                <li><a href="https://frigate.video" target="_blank" rel="noopener noreferrer" class="text-brand-600 dark:text-brand-400 hover:underline">Frigate</a> for being an excellent open-source NVR</li>
                <li><a href="https://github.com/tphakala/birdnet-go" target="_blank" rel="noopener noreferrer" class="text-brand-600 dark:text-brand-400 hover:underline">BirdNET-Go</a> for audio classification integration</li>
                <li><a href="https://youtu.be/hCQCP-5g5bo" target="_blank" rel="noopener noreferrer" class="text-brand-600 dark:text-brand-400 hover:underline">Ben Jordan</a> on YouTube for inspiring bird detection content</li>
                <li>AI assistants that helped build this application</li>
            </ul>
        </div>
    </div>

    <!-- License -->
    <div class="text-center text-sm text-slate-500 dark:text-slate-400 py-4">
        <p>© {new Date().getFullYear()} Jellman86 • Licensed under the MIT License</p>
        <p class="mt-1">Built with AI assistance for the love of bird watching 🐦</p>
    </div>
</div>
