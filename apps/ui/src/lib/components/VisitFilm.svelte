<script lang="ts">
    import { holdVisitFilm, releaseVisitFilm } from '../utils/visit-films';

    /**
     * A visit's photograph that comes alive: the stored crop, and over it a few silent seconds
     * of the same visit once the film is made and the picture is on screen.
     *
     * The photograph is always there, so the layout never moves and a missing film is simply a
     * photograph. The film is fetched only when the picture first scrolls near the viewport,
     * plays only while it is visible, and is never fetched for reduced motion or a data-saver
     * connection. It is decoration over a photograph the card already labels, so it is hidden
     * from readers.
     */
    interface Props {
        frigateEvent: string;
        poster: string;
        /** False when no film was made for this visit; only the photograph is shown. */
        film: boolean;
        class?: string;
        width?: number;
        height?: number;
    }

    let { frigateEvent, poster, film, class: className = '', width, height }: Props = $props();

    let frame = $state<HTMLElement | null>(null);
    let video = $state<HTMLVideoElement | null>(null);
    let near = $state(false);
    let visible = $state(false);
    let src = $state<string | null>(null);
    let playing = $state(false);

    let still = $state(false);
    $effect(() => {
        if (typeof window === 'undefined') return;
        const query = window.matchMedia('(prefers-reduced-motion: reduce)');
        const connection = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection;
        const sync = () => {
            still =
                query.matches ||
                document.documentElement.classList.contains('reduced-motion') ||
                connection?.saveData === true;
        };
        sync();
        query.addEventListener('change', sync);
        return () => query.removeEventListener('change', sync);
    });

    $effect(() => {
        if (!frame || !film || typeof IntersectionObserver === 'undefined') return;
        const nearObserver = new IntersectionObserver(
            (entries) => {
                if (entries.some((entry) => entry.isIntersecting)) {
                    near = true;
                    nearObserver.disconnect();
                }
            },
            { rootMargin: '200px' }
        );
        const visibleObserver = new IntersectionObserver((entries) => {
            visible = entries.some((entry) => entry.isIntersecting);
        });
        nearObserver.observe(frame);
        visibleObserver.observe(frame);
        return () => {
            nearObserver.disconnect();
            visibleObserver.disconnect();
        };
    });

    $effect(() => {
        if (!near || !film || still) return;
        const event = frigateEvent;
        let current = true;
        void holdVisitFilm(event).then((url) => {
            if (current) src = url;
        });
        return () => {
            current = false;
            src = null;
            playing = false;
            releaseVisitFilm(event);
        };
    });

    $effect(() => {
        if (!video || !src) return;
        if (visible) {
            void video.play().catch(() => {
                // Autoplay refused (a power-saving mode): the photograph stays.
            });
        } else {
            video.pause();
        }
    });
</script>

<span bind:this={frame} class="relative block overflow-hidden {className}" data-visit-film={film ? 'film' : 'photo'}>
    <img src={poster} alt="" loading="lazy" decoding="async" {width} {height} class="h-full w-full object-cover" />
    {#if src}
        <video
            bind:this={video}
            {src}
            muted
            loop
            playsinline
            preload="auto"
            disablepictureinpicture
            aria-hidden="true"
            tabindex="-1"
            class="absolute inset-0 h-full w-full object-cover transition-opacity duration-500 {playing ? 'opacity-100' : 'opacity-0'}"
            onplaying={() => (playing = true)}
        ></video>
    {/if}
</span>
