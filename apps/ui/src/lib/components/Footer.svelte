<script lang="ts">
    import { onMount } from 'svelte';
    import { fetchVersion, type VersionInfo } from '../api';
    
    let version = $state(__APP_VERSION__.split('+')[0]);
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
                // Show clean version - hide "+unknown" suffix if git hash isn't available
                version = info.git_hash === "unknown" ? info.base_version : info.version;
            } catch (e) {
                console.error('Failed to fetch version info', e);
            }
        })();
    });

    // Bird facts - mix of real and funny
    const birdFacts = [
        // Real facts
        "Hummingbirds can fly backwards and are the only birds that can hover in place",
        "Crows can recognize human faces and remember people who have wronged them",
        "The Arctic Tern migrates over 44,000 miles annually - the longest migration of any bird",
        "Owls cannot move their eyeballs, which is why they can rotate their heads up to 270 degrees",
        "A group of flamingos is called a 'flamboyance'",
        "Pigeons can do math at roughly the same level as monkeys",
        "The Peregrine Falcon can dive at speeds over 240 mph, making it the fastest animal on Earth",
        "A woodpecker's tongue wraps around its skull to cushion its brain from impacts",
        "Ravens can imitate human speech and other sounds like car engines and toilets flushing",
        "The European Robin will attack its own reflection thinking it's a rival",
        "Some parrots can live for over 80 years",
        "A hummingbird's heart beats up to 1,260 times per minute",
        "Chickens can distinguish over 100 different faces of their own species",
        "The Bassian Thrush farts to find food - the gas startles worms out of hiding",
        "Penguins propose to their mates with a pebble",
        "Blue jays can mimic the calls of hawks to scare other birds away from feeders",
        "Cardinals and robins have been observed 'anting' - letting ants crawl on them to ward off parasites",
        "Some species of birds sleep with one eye open to watch for predators",
        "A bird's feathers weigh more than its skeleton",
        "Starlings can mimic over 20 different bird species",
        "The Kiwi is the only bird with nostrils at the end of its beak",
        "Hoatzin chicks have claws on their wings to climb trees",
        "The wandering albatross has the largest wingspan of any living bird, up to 11.8 feet",
        "A mockingbird can learn up to 200 different songs in its lifetime",
        "Some vultures can fly at altitudes of 37,000 feet",
        "The ostrich is the largest bird in the world and can run up to 43 mph",
        "Hummingbirds consume about half their body weight in sugar daily",
        "The call of the lyrebird is the most complex of any bird, mimicking chainsaws and camera shutters",
        "Puffin beaks change color; they are dull in winter and bright orange in spring",
        "The sword-billed hummingbird is the only bird with a bill longer than its body",
        "Crows have been observed using tools, such as bending wires to hook food",
        "The Kakapo is the world's only flightless parrot and is nocturnal",
        "Birds have hollow bones which help them fly by reducing their weight",
        "The Bee Hummingbird is the smallest bird in the world, weighing less than a penny",
        "Frigatebirds can stay in the air for months at a time without landing",
        "The Greater Honeyguide bird leads humans to honey hives in exchange for wax",
        "Some species of ducks sleep in a row; the ones at the ends keep one eye open",
        "The eyes of an ostrich are bigger than its brain",
        "A group of crows is called a 'murder'",
        "Falcons can see a 10 cm object from a distance of 1.5 km",
        "The feathers of a flamingo turn pink due to pigments in the algae and crustaceans they eat",
        "Swans mate for life and can become aggressive when protecting their nests",
        "The Harpy Eagle's talons are as large as a grizzly bear's claws",
        "Woodpeckers don't get headaches because their skulls have air pockets to absorb shock",
        "The Kea parrot is known for investigating (and destroying) cars in New Zealand",
        "Emperor Penguins can dive to depths of over 500 meters",
        "The Shoebill stork can stand motionless for hours to ambush prey",
        "Some birds, like the Bar-tailed Godwit, fly over 7,000 miles non-stop",
        "The Oilbird uses echolocation to navigate in dark caves, similar to bats",
        "Male Bowerbirds build elaborate structures decorated with blue objects to attract mates",
        "The African Grey Parrot is considered one of the most intelligent birds",
        "Swifts spend most of their lives in the air and can even sleep while flying",
        "The Secretary Bird stomps on snakes with a force of 5 times its body weight",
        "Some owls hunt fish instead of rodents",
        "The common poorwill is the only bird known to go into torpor (hibernation) for weeks",
        "Kingfishers have specialized eyes that allow them to see underwater without refraction issues",
        "The Dodo was a flightless bird native to Mauritius that went extinct in the 17th century",
        "Great Tits in the UK learned to open milk bottles to drink the cream",
        "The Andean Condor uses thermal currents to fly for hours without flapping wings",
        "Magpies are one of the few animals that can recognize themselves in a mirror",
        "The cassowary is often called the world's most dangerous bird",
        "The malleefowl builds a giant compost heap to incubate its eggs",
        "The tailorbird sews leaves together to make its nest using spider silk",
        "The sociable weaver builds the largest communal nests, housing up to 100 pairs",
        "Golden eagles have been known to hunt wolves",
        "The bearded vulture's diet consists of 70-90% bone",
        "Shrikes impale their prey on thorns or barbed wire to save it for later",
        // Funny ones
        "Birds aren't real - they're government surveillance drones (allegedly)",
        "If you've ever been pooped on by a bird, congratulations on your blessing from above",
        "Scientists say pigeons are just beach chickens",
        "The early bird gets the worm, but the second mouse gets the cheese",
        "Geese have teeth on their tongues. Sleep well tonight!",
        "Ducks have been known to commit crimes. They're fowl play experts",
        "A bird in the hand is worth two in the bush, but significantly messier",
        "Penguins are just formal chickens dressed for a gala",
        "Owls are the original internet surveillance cameras",
        "If birds could text, they would leave you on 'read' just like cats",
        "Roosters scream at the sun because they are afraid of the dark"
    ];

    let currentFactIndex = $state(0);
    let isTransitioning = $state(false);
    const year = new Date().getFullYear();

    onMount(() => {
        const interval = setInterval(() => {
            isTransitioning = true;
            setTimeout(() => {
                currentFactIndex = (currentFactIndex + 1) % birdFacts.length;
                isTransitioning = false;
            }, 300);
        }, 8000);

        // Randomize starting fact
        currentFactIndex = Math.floor(Math.random() * birdFacts.length);

        return () => clearInterval(interval);
    });
</script>

<footer class="bg-white/50 dark:bg-slate-900/50 border-t border-slate-200/80 dark:border-slate-700/50 mt-auto backdrop-blur-sm">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <div class="flex flex-col md:flex-row justify-between items-center gap-4 text-sm text-slate-600 dark:text-slate-400">
            <div class="flex flex-col sm:flex-row items-center gap-2 sm:gap-4">
                <span class="font-medium text-slate-700 dark:text-slate-300">
                    Yet Another WhosAtMyFeeder
                </span>
                <span class="hidden sm:inline text-slate-400 dark:text-slate-500">|</span>
                <span title={versionInfo.git_hash !== "unknown" ? `Git: ${versionInfo.git_hash}` : ""}>v{version}</span>
            </div>

            <div class="flex items-center gap-4">
                <a
                    href="https://github.com/Jellman86/YetAnother-WhosAtMyFeeder"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="hover:text-slate-900 dark:hover:text-white transition-colors flex items-center gap-1.5"
                >
                    <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                        <path fill-rule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" clip-rule="evenodd" />
                    </svg>
                    GitHub
                </a>
                <span class="text-slate-400 dark:text-slate-500">|</span>
                <span>MIT License</span>
            </div>

            <div class="text-center md:text-right">
                <span>&copy; {year} Jellman86</span>
            </div>
        </div>

        <!-- Bird Facts Ticker -->
        <div class="mt-4 pt-4 border-t border-slate-200/60 dark:border-slate-700/40">
            <div class="flex items-center justify-center gap-2 text-xs text-slate-600 dark:text-slate-400">
                <span class="text-amber-500 dark:text-amber-400 flex-shrink-0">Did you know?</span>
                <span
                    class="transition-opacity duration-300 text-center"
                    class:opacity-0={isTransitioning}
                    class:opacity-100={!isTransitioning}
                >
                    {birdFacts[currentFactIndex]}
                </span>
            </div>
        </div>

        <div class="mt-3 text-center text-xs text-slate-500 dark:text-slate-500">
            Built with AI assistance for the love of bird watching
        </div>
    </div>
</footer>
