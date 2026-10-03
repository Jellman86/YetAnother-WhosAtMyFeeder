<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { getReelImageUrl, type FeederPortrait } from '../api';
    import { formatDate, formatDateTime } from '../utils/datetime';
    import VisitFilm from './VisitFilm.svelte';

    /**
     * The About page's opener: this feeder in a few facts it has measured, beside its latest
     * visit, which plays a few silent seconds once a film is made. Visits follow the
     * leaderboard's rule and days are the viewer's days. A guest is told the facts cover only
     * the shared window, so a short window never reads as a young feeder.
     */
    interface Props {
        portrait: FeederPortrait;
        communityInstalls?: number | null;
        /** The visit whose record is being fetched, so its button can say so. */
        openingEvent?: string | null;
        onopenvisit: (frigateEvent: string) => void;
        onopenspecies: (name: string) => void;
    }

    let { portrait, communityInstalls = null, openingEvent = null, onopenvisit, onopenspecies }: Props = $props();

    const latest = $derived(portrait.latest_visit ?? null);
    const opening = $derived(latest !== null && openingEvent === latest.frigate_event);

    // The busiest day is a calendar date, not an instant: read at midday so no offset moves it.
    const busiestDate = $derived(portrait.busiest_day ? formatDate(`${portrait.busiest_day.date}T12:00:00`) : null);

    const heading = $derived.by(() => {
        if (portrait.scope === 'shared') {
            return portrait.shared_days === 0
                ? $_('about.portrait.shared_today', { default: 'Today at this feeder.' })
                : $_('about.portrait.shared_days', {
                      values: { days: portrait.shared_days ?? 0 },
                      default: 'The last {days} days at this feeder.'
                  });
        }
        return portrait.started_at
            ? $_('about.portrait.since', {
                  values: { date: formatDate(portrait.started_at) },
                  default: 'Watching since {date}.'
              })
            : $_('about.portrait.empty', { default: 'No visits recorded yet. This fills in as birds arrive.' });
    });

    function visits(count: number): string {
        return count === 1
            ? $_('about.portrait.visit_count_one', { default: '1 visit' })
            : $_('about.portrait.visit_count', { values: { count: count.toLocaleString() }, default: '{count} visits' });
    }
</script>

<section class="grid gap-5 md:grid-cols-2 md:items-center" aria-labelledby="about-portrait-heading" data-feeder-portrait>
    {#if latest}
        <button
            type="button"
            class="group relative block aspect-video w-full overflow-hidden rounded-2xl border border-slate-200/80 bg-slate-900 text-left shadow-card transition-[transform,box-shadow] duration-200 ease-out hover:-translate-y-0.5 hover:shadow-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 motion-reduce:transform-none dark:border-slate-700/60 dark:shadow-card-dark"
            aria-label={$_('about.portrait.open_visit', {
                values: { name: latest.display_name, time: formatDateTime(latest.detection_time) },
                default: 'Open the {name} visit from {time}'
            })}
            aria-busy={opening}
            data-feeder-portrait-visit
            onclick={() => onopenvisit(latest.frigate_event)}
        >
            <VisitFilm
                frigateEvent={latest.frigate_event}
                poster={getReelImageUrl(latest.frigate_event)}
                film={Boolean(latest.film_url)}
                width={640}
                height={360}
                class="h-full w-full"
            />
            <span class="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-slate-950/80 to-transparent px-4 pb-3 pt-10" aria-hidden="true">
                <span class="block text-xs font-semibold text-white/75">{$_('about.portrait.latest', { default: 'Latest visit' })}</span>
                <span class="block truncate text-base font-semibold text-white">{latest.display_name}</span>
                <span class="block text-xs text-white/75">{formatDateTime(latest.detection_time)}</span>
            </span>
            {#if opening}
                <span class="absolute inset-0 flex items-center justify-center bg-slate-950/45" aria-hidden="true">
                    <span class="inline-block h-6 w-6 animate-spin rounded-full border-2 border-white border-t-transparent"></span>
                </span>
            {/if}
        </button>
    {/if}

    <div class="min-w-0 space-y-4 {latest ? '' : 'md:col-span-2'}">
        <h3 id="about-portrait-heading" class="font-display text-xl font-semibold leading-snug text-slate-900 dark:text-white">
            {heading}
        </h3>
        {#if portrait.visits > 0}
            <dl class="grid grid-cols-2 gap-x-6 gap-y-4" data-feeder-portrait-facts>
                <div>
                    <dd class="font-display text-2xl font-bold tabular-nums text-slate-900 dark:text-white">{portrait.visits.toLocaleString()}</dd>
                    <dt class="text-xs text-slate-500 dark:text-slate-400">{$_('about.portrait.visits', { default: 'visits' })}</dt>
                </div>
                <div>
                    <dd class="font-display text-2xl font-bold tabular-nums text-slate-900 dark:text-white">{portrait.species.toLocaleString()}</dd>
                    <dt class="text-xs text-slate-500 dark:text-slate-400">{$_('about.portrait.species', { default: 'species' })}</dt>
                </div>
                {#if portrait.busiest_day && busiestDate}
                    <div class="min-w-0">
                        <dt class="text-xs text-slate-500 dark:text-slate-400">{$_('about.portrait.busiest_day', { default: 'Busiest day' })}</dt>
                        <dd class="mt-0.5 truncate text-sm font-semibold text-slate-900 dark:text-white">{busiestDate}</dd>
                        <dd class="text-xs tabular-nums text-slate-500 dark:text-slate-400">{visits(portrait.busiest_day.visits)}</dd>
                    </div>
                {/if}
                {#if portrait.newest_arrival}
                    {@const arrival = portrait.newest_arrival}
                    <div class="min-w-0">
                        <dt class="text-xs text-slate-500 dark:text-slate-400">{$_('about.portrait.newest_arrival', { default: 'Newest arrival' })}</dt>
                        <dd class="mt-0.5 truncate text-sm font-semibold">
                            <button
                                type="button"
                                class="min-h-[44px] min-w-[44px] max-w-full truncate text-left text-brand-600 hover:underline focus-ring dark:text-brand-400"
                                data-feeder-portrait-arrival
                                onclick={() => onopenspecies(arrival.species)}
                            >
                                {arrival.display_name}
                            </button>
                        </dd>
                        <dd class="text-xs text-slate-500 dark:text-slate-400">
                            {$_('about.portrait.first_seen', { values: { date: formatDate(arrival.first_seen) }, default: 'first seen {date}' })}
                        </dd>
                    </div>
                {/if}
            </dl>
        {/if}
        {#if communityInstalls !== null}
            <p class="text-xs text-slate-500 dark:text-slate-400" data-about-community>
                {$_('about.portrait.community', {
                    values: { count: communityInstalls.toLocaleString() },
                    default: '{count} feeders ran YA-WAMF this week.'
                })}
            </p>
        {/if}
    </div>
</section>
