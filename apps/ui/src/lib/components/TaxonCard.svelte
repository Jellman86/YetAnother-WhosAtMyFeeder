<script lang="ts">
    import { untrack } from 'svelte';
    import { _, locale } from 'svelte-i18n';
    import { currentNamingStyle } from '../taxonomy/naming-style';
    import { taxonNames } from '../taxonomy/nomenclature';
    import {
        authorityText,
        groupOtherNames,
        heardCount,
        iucnCategory,
        languageLabel,
        ownPhoto,
        sameLocalDay,
        visitsView
    } from '../taxonomy/taxon-facts';
    import { placeCard, type Box } from '../taxonomy/card-placement';
    import { formatDay } from '../utils/datetime';
    import { groupReference, speciesReference, type TaxonReference } from '../utils/taxon-pictures';
    import { speciesOtherNames, type OtherNamesResult, type TaxonFactsStore } from '../utils/taxon-facts.svelte';
    import type { TaxonPeek } from '../utils/taxon-peek.svelte';
    import { portal } from '../utils/portal';
    import TaxonNameText from './TaxonNameText.svelte';

    /**
     * The card a taxon's name opens, set like a specimen label: what it is and who named it, then
     * what this install recorded of it (its own photograph, visits, first and last seen, calls),
     * then the reference detail (IUCN category, a short description, its names in other languages).
     * Portalled and placed in viewport coordinates, so no scrolling container clips it.
     *
     * Every fact has its own loading, absent and failed state, and one that is not known is left
     * out. A pinned card takes Tab into its controls, and Tab past them, or Escape, returns focus
     * to the name that opened it.
     */
    interface Props {
        peek: TaxonPeek;
        /** What this install recorded of each taxon, shared with the surface the card belongs to. */
        facts: TaxonFactsStore;
        /** A Garden animal: its catalogue is the model's animals, so a group's size is not a worldwide count. */
        subject?: 'bird' | 'animal';
    }

    let { peek, facts, subject = 'bird' }: Props = $props();

    const GAP = 8;
    const MARGIN = 8;

    const anchor = $derived(peek.anchor);
    const taxon = $derived(anchor?.taxon ?? null);
    const isSpecies = $derived(taxon?.rank === 'species');
    const describedRank = $derived(taxon?.rank === 'family' || taxon?.rank === 'order' ? taxon.rank : null);
    const names = $derived(taxon ? taxonNames(taxon, currentNamingStyle()) : null);
    const authority = $derived(authorityText(taxon?.authorship));
    const entry = $derived(taxon ? facts.get(taxon.taxon_id) : undefined);
    const visits = $derived(visitsView(entry, sameLocalDay));
    const calls = $derived(heardCount(entry));
    const own = $derived(ownPhoto(entry));
    const seenSpecies = $derived(taxon?.seen_species ?? 0);

    let card = $state<HTMLElement | null>(null);
    // Bumped as the page scrolls or resizes, so the card is placed against where its name is now.
    let frame = $state(0);
    let cardHeight = $state(0);
    // Measured rather than assumed: the card is sized in rem, so the reader's text size sets its width.
    let cardWidth = $state(0);

    /** The card stays inside the dialog the name sits in (the family tree, a record), else the window. */
    function container(element: Element): Box {
        const viewport = { left: 0, top: 0, right: window.innerWidth, bottom: window.innerHeight };
        const dialog = element.closest('[role="dialog"]')?.getBoundingClientRect();
        if (!dialog) return viewport;
        return {
            left: Math.max(viewport.left, dialog.left),
            top: Math.max(viewport.top, dialog.top),
            right: Math.min(viewport.right, dialog.right),
            bottom: Math.min(viewport.bottom, dialog.bottom)
        };
    }

    const position = $derived.by(() => {
        void frame;
        if (!anchor) return null;
        const size = { width: cardWidth || 320, height: cardHeight || (isSpecies ? 420 : 240) };
        return placeCard(anchor.element.getBoundingClientRect(), size, container(anchor.element), GAP, MARGIN);
    });

    // A card taller than its room scrolls inside; a fade at its foot says there is more, until the end.
    // Which card was scrolled to its end, so a new card always starts at its top with the fade showing.
    let endReached = $state<number | null>(null);
    const overflowing = $derived(Boolean(position && cardHeight > position.maxHeight + 1));
    const scrolledToEnd = $derived(taxon !== null && endReached === taxon.taxon_id);
    function measureScroll(event: Event): void {
        const box = event.currentTarget;
        if (!(box instanceof HTMLElement) || !taxon) return;
        endReached = box.scrollTop + box.clientHeight >= box.scrollHeight - 1 ? taxon.taxon_id : null;
    }

    /** The control that opened the card: the name, or the tree node around its marker. */
    function trigger(element: Element): HTMLElement | null {
        const found = element.closest<HTMLElement>('[data-taxon-peek-trigger]');
        return found ?? (element instanceof HTMLElement ? element : null);
    }

    function controls(): HTMLElement[] {
        return card ? [...card.querySelectorAll<HTMLElement>('button, summary')] : [];
    }

    $effect(() => {
        if (!anchor) return;
        const element = anchor.element;
        let pending: number | null = null;
        const follow = () => {
            if (pending !== null) return;
            pending = requestAnimationFrame(() => {
                pending = null;
                const rect = element.getBoundingClientRect();
                // A name scrolled out of sight closes its card: a card pointing at nothing helps no one.
                if (!element.isConnected || rect.bottom < 0 || rect.top > window.innerHeight) peek.close();
                else frame += 1;
            });
        };
        // A tap elsewhere closes a pinned card; another name is a trigger and handles itself.
        const outside = (event: PointerEvent) => {
            const target = event.target;
            if (!(target instanceof Element)) return;
            if (target.closest('[data-taxon-card], [data-taxon-peek-trigger]')) return;
            peek.close();
        };
        const keys = (event: KeyboardEvent) => {
            const active = document.activeElement;
            const inside = Boolean(card && active && card.contains(active));
            // Escape closes the card before anything behind it: the record or the tree stays open.
            if (event.key === 'Escape') {
                event.preventDefault();
                event.stopPropagation();
                if (inside) peek.closeTo(trigger(element));
                else peek.close();
                return;
            }
            if (event.key !== 'Tab' || !anchor.pinned) return;
            const list = controls();
            if (list.length === 0) return;
            const onTrigger = active instanceof Element && (active.contains(element) || element.contains(active));
            if (onTrigger && !event.shiftKey) {
                event.preventDefault();
                list[0].focus();
            } else if (inside) {
                const index = list.indexOf(active as HTMLElement);
                const leaving = event.shiftKey ? index <= 0 : index === list.length - 1;
                if (!leaving) return;
                event.preventDefault();
                const opener = trigger(element);
                if (event.shiftKey) opener?.focus();
                else peek.closeTo(opener);
            }
        };
        window.addEventListener('scroll', follow, true);
        window.addEventListener('resize', follow);
        window.addEventListener('keydown', keys, true);
        document.addEventListener('pointerdown', outside, true);
        return () => {
            if (pending !== null) cancelAnimationFrame(pending);
            window.removeEventListener('scroll', follow, true);
            window.removeEventListener('resize', follow);
            window.removeEventListener('keydown', keys, true);
            document.removeEventListener('pointerdown', outside, true);
        };
    });

    // The reference lookup is keyed by the name, not the taxon object: hovering, focusing or pinning
    // the same species places a fresh proxied taxon, and re-running the lookup for it once stranded
    // the card loading. A family or order is keyed by its rank too, apart from any species.
    let picture = $state<{ name: string; state: 'loading' } | { name: string; state: 'done'; reference: TaxonReference } | null>(null);
    const pictureName = $derived(taxon && (isSpecies || describedRank) ? `${describedRank ?? 'species'}:${taxon.scientific_name}` : null);

    $effect(() => {
        const name = pictureName;
        if (!name) return;
        // Read untracked: the picture this effect sets must not re-run it.
        if (untrack(() => picture?.name) === name) return;
        picture = { name, state: 'loading' };
        const separator = name.indexOf(':');
        const rank = name.slice(0, separator);
        const scientific = name.slice(separator + 1);
        const lookup = rank === 'family' || rank === 'order' ? groupReference(scientific, rank) : speciesReference(scientific);
        // A result for a name the card has moved away from is dropped by the name check.
        void lookup.then((reference) => {
            if (picture?.name === name) picture = { name, state: 'done', reference };
        });
    });

    const reference = $derived(picture && picture.name === pictureName && picture.state === 'done' ? picture.reference : null);
    const referenceLoading = $derived(Boolean(pictureName) && !reference);
    const conservation = $derived(isSpecies && reference?.state === 'ready' ? iucnCategory(reference.conservation) : null);

    // A species' names in other languages, read when its card first opens.
    let otherNames = $state<{ id: number; result: OtherNamesResult | null } | null>(null);
    const namesId = $derived(isSpecies && taxon ? taxon.taxon_id : null);

    $effect(() => {
        const id = namesId;
        if (id === null) return;
        if (untrack(() => otherNames?.id) === id) return;
        otherNames = { id, result: null };
        void speciesOtherNames(id).then((result) => {
            if (otherNames?.id === id) otherNames = { id, result };
        });
    });

    const namesResult = $derived(otherNames && otherNames.id === namesId ? otherNames.result : null);
    const nameGroups = $derived(
        namesResult?.state === 'ready' ? groupOtherNames(namesResult.names.names, (tag) => languageLabel(tag, $locale ?? 'en')) : []
    );

    // A photograph that failed to load gives way: an own photo to the reference, a reference to the placeholder.
    let brokenPhotos = $state.raw<ReadonlySet<string>>(new Set());
    function broke(url: string): void {
        brokenPhotos = new Set([...brokenPhotos, url]);
    }

    type Shown =
        | { kind: 'own'; url: string; caption: string; alt: string }
        | { kind: 'reference'; url: string }
        | { kind: 'loading' }
        | { kind: 'none'; text: string };

    const shown = $derived.by((): Shown | null => {
        if (!taxon || !names) return null;
        if (own && !brokenPhotos.has(own.url)) {
            const pictured = own.species_id === taxon.taxon_id
                ? names.primary.text
                : taxonNames({ rank: 'species', scientific_name: own.scientific_name, name: own.name }, currentNamingStyle()).primary.text;
            return {
                kind: 'own',
                url: own.url,
                caption: own.species_id === taxon.taxon_id
                    ? `${$_('taxonomy.your_photo', { default: 'Your photo' })}, ${formatDay(own.taken_at)}`
                    : $_('taxonomy.your_photo_of', { values: { name: pictured }, default: 'Your photo of {name}' }),
                alt: $_('taxonomy.own_photo_alt', { values: { species: pictured }, default: 'Your photograph of {species}' })
            };
        }
        if (isSpecies) {
            // Wait for the facts before showing the reference, so it never flashes before your own photo.
            if (visits.kind === 'loading' || referenceLoading) return { kind: 'loading' };
            if (reference?.state === 'ready' && reference.thumbnail && !brokenPhotos.has(reference.thumbnail)) {
                return { kind: 'reference', url: reference.thumbnail };
            }
            return { kind: 'none', text: $_('taxonomy.no_reference_photo', { default: 'No reference photo' }) };
        }
        // A group is pictured only by this install's photo of one of its members, never a reference image.
        return null;
    });

    /** The group's size and what was seen of it. An animal's catalogue is the model's, not the world's. */
    function seenLine(): string | null {
        if (!taxon || isSpecies) return null;
        if (subject === 'animal') {
            return $_('taxonomy.animal_seen', { values: { seen: seenSpecies }, default: '{seen, plural, =0 {None seen here} one {# seen here} other {# seen here}}' });
        }
        return $_('taxonomy.group_counts', {
            values: { total: taxon.species_count ?? 0, seen: seenSpecies },
            default: '{total, plural, one {# species} other {# species}} worldwide, {seen} seen here'
        });
    }

    function scopeLine(): string | null {
        const scope = facts.scope;
        if (!scope) return null;
        if (scope.scope === 'all') return $_('taxonomy.facts.scope_all', { default: 'Counts cover all history' });
        return $_('taxonomy.facts.scope_shared', {
            values: { days: scope.shared_days ?? 0 },
            default: '{days, plural, =0 {Counts cover today, as shared with visitors} one {Counts cover the last day shared with visitors} other {Counts cover the last # days shared with visitors}}'
        });
    }

    const description = $derived(reference?.state === 'ready' && (isSpecies || describedRank) ? reference.extract : null);
</script>

{#snippet fact(label: string, value: string, key: string, strong = false)}
    <div class="min-w-0">
        <dt class="taxon-rank">{label}</dt>
        <dd class="mt-0.5 tabular-nums {strong ? 'font-display text-base font-bold text-slate-900 dark:text-white' : 'text-xs text-slate-800 dark:text-slate-100'}" data-fact={key}>{value}</dd>
    </div>
{/snippet}

{#snippet authorityAfter(kind: 'common' | 'scientific')}
    {#if authority && kind === 'scientific'}<span class="font-normal not-italic text-slate-600 dark:text-slate-400" data-taxon-authority>{` ${authority}`}</span>{/if}
{/snippet}

{#if anchor && taxon && names && position}
    <div
        use:portal
        bind:this={card}
        class="pointer-events-auto fixed z-90 w-80 overflow-hidden rounded-xl border border-line bg-surface text-left shadow-lg"
        style:left="{position.left}px"
        style:top="{position.top}px"
        style:max-width="calc(100vw - {MARGIN * 2}px)"
        role="group"
        aria-label={names.primary.text}
        bind:clientWidth={cardWidth}
        onpointerenter={() => peek.stay()}
        onpointerleave={() => peek.leave()}
        data-taxon-card
    >
        {#key taxon.taxon_id}
            <div
                class="overflow-y-auto overscroll-contain"
                style:max-height="{position.maxHeight}px"
                onscroll={measureScroll}
                data-taxon-card-scroll
            >
                <!-- Measured inside the scroll box, so placement reads the card's natural height, not its clamped one. -->
                <div bind:clientHeight={cardHeight}>
                    {#if shown}
                        <div class="relative aspect-video w-full overflow-hidden bg-surface-raised" data-taxon-card-figure>
                            {#if shown.kind === 'own'}
                                <img src={shown.url} alt={shown.alt} class="h-full w-full object-cover" onerror={() => broke(shown.url)} data-taxon-card-own-picture />
                                <span class="absolute bottom-1.5 left-1.5 max-w-full truncate rounded-md bg-slate-950/70 px-1.5 py-0.5 text-3xs font-medium text-white" data-taxon-card-caption>{shown.caption}</span>
                            {:else if shown.kind === 'reference'}
                                <img
                                    src={shown.url}
                                    alt={$_('detection.species_reference_alt', { values: { species: names.primary.text }, default: 'Reference photograph of {species}' })}
                                    class="h-full w-full object-cover"
                                    onerror={() => broke(shown.url)}
                                    data-taxon-card-picture
                                />
                                <span class="absolute bottom-1.5 left-1.5 max-w-full truncate rounded-md bg-slate-950/70 px-1.5 py-0.5 text-3xs font-medium text-white" data-taxon-card-caption>
                                    {$_('taxonomy.reference_photo', { default: 'Reference photo' })}
                                </span>
                            {:else if shown.kind === 'loading'}
                                <div class="h-full w-full animate-pulse bg-slate-100 motion-reduce:animate-none dark:bg-slate-800" aria-hidden="true"></div>
                            {:else}
                                <div class="flex h-full w-full flex-col items-center justify-center gap-1 text-slate-600 dark:text-slate-400" data-taxon-card-no-picture>
                                    <svg class="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M4 18 9 13l3 3 2-2 6 6M15 8h.01M5 4h14a1 1 0 0 1 1 1v14H4V5a1 1 0 0 1 1-1Z" stroke-linecap="round" stroke-linejoin="round" /></svg>
                                    <span class="text-2xs">{shown.text}</span>
                                </div>
                            {/if}
                        </div>
                    {/if}

                    <div class="space-y-3 p-4">
                        <header class="space-y-0.5">
                            <p class="taxon-rank" data-taxon-card-rank>
                                {$_(`taxonomy.rank.${taxon.rank}`, { default: taxon.rank })}{#if anchor.current}<span class="font-normal normal-case tracking-normal">{` · ${subject === 'animal'
                                    ? $_('taxonomy.legend_this_animal', { default: 'This animal' })
                                    : $_('taxonomy.legend_this_bird', { default: 'This bird' })}`}</span>{/if}
                            </p>
                            <p class="font-display text-lg font-bold leading-snug text-slate-900 dark:text-white">
                                <TaxonNameText name={names.primary} />{@render authorityAfter(names.primary.kind)}
                            </p>
                            {#if names.secondary}
                                <p class="text-sm text-slate-600 dark:text-slate-300">
                                    <TaxonNameText name={names.secondary} />{@render authorityAfter(names.secondary.kind)}
                                </p>
                            {/if}
                        </header>

                        {#if calls !== null || conservation}
                            <ul class="flex flex-wrap gap-1.5" data-taxon-card-badges>
                                {#if calls !== null}
                                    <li
                                        class="inline-flex items-center gap-1 rounded-md border border-line px-1.5 py-0.5 text-2xs text-slate-700 dark:text-slate-200"
                                        data-taxon-card-heard
                                    >
                                        <svg class="h-3 w-3" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><path d="M2 7v2M5 4.5v7M8 2v12M11 5v6M14 7v2" /></svg>
                                        <span class="font-semibold">{$_('taxonomy.heard', { default: 'Heard' })}</span>
                                        <span class="tabular-nums">{$_('taxonomy.heard_calls', { values: { count: calls }, default: '{count, plural, one {# call} other {# calls}}' })}</span>
                                    </li>
                                {/if}
                                {#if conservation}
                                    <li class="inline-flex items-center gap-1 rounded-md border border-line px-1.5 py-0.5 text-2xs text-slate-700 dark:text-slate-200" data-taxon-card-iucn>
                                        <span class="font-semibold">{$_('taxonomy.iucn_label', { default: 'IUCN' })}</span>
                                        <span>{$_(`taxonomy.iucn.${conservation}`, { default: conservation })} ({conservation})</span>
                                    </li>
                                {/if}
                            </ul>
                        {/if}

                        <section class="space-y-1.5 border-t border-line-soft pt-3" aria-label={$_('taxonomy.facts.heading', { default: 'Recorded here' })} data-taxon-card-facts>
                            {#if seenLine()}
                                <p class="text-xs tabular-nums {seenSpecies > 0 ? 'font-semibold text-emerald-700 dark:text-emerald-300' : 'text-slate-600 dark:text-slate-400'}" data-taxon-card-seen>{seenLine()}</p>
                            {/if}
                            {#if visits.kind === 'loading'}
                                <div class="space-y-1.5" aria-busy="true" data-taxon-card-facts-loading>
                                    <span class="sr-only">{$_('taxonomy.facts.loading', { default: 'Loading what was recorded here' })}</span>
                                    <div class="h-3 w-3/4 animate-pulse rounded-sm bg-slate-100 motion-reduce:animate-none dark:bg-slate-800" aria-hidden="true"></div>
                                    <div class="h-3 w-1/2 animate-pulse rounded-sm bg-slate-100 motion-reduce:animate-none dark:bg-slate-800" aria-hidden="true"></div>
                                </div>
                            {:else if visits.kind === 'failed'}
                                <p class="flex flex-wrap items-center gap-x-2 text-xs text-slate-600 dark:text-slate-300" data-taxon-card-facts-failed>
                                    {$_('taxonomy.facts.failed', { default: 'What was recorded here could not load.' })}
                                    <button type="button" class="btn btn-ghost min-h-11 px-2 text-xs" onclick={() => facts.request([taxon.taxon_id], { retryFailed: true })}>
                                        {$_('taxonomy.facts.retry', { default: 'Try again' })}
                                    </button>
                                </p>
                            {:else if visits.kind === 'none'}
                                <p class="text-xs text-slate-600 dark:text-slate-400" data-taxon-card-visits>{$_('taxonomy.facts.no_visits', { default: 'No visits recorded' })}</p>
                            {:else if visits.kind === 'seen'}
                                <!-- Label above figure, as the day bar sets its figures: the eye reads across one row. -->
                                <dl class="grid grid-cols-3 gap-x-3" data-taxon-card-visits>
                                    {@render fact($_('taxonomy.facts.visits', { default: 'Visits' }), visits.visits.toLocaleString($locale ?? undefined), 'visits', true)}
                                    {#if !isSpecies}
                                        {@render fact($_('taxonomy.facts.last_visit', { default: 'Last visit' }), formatDay(visits.lastSeen), 'last')}
                                    {:else if visits.sameDay}
                                        {@render fact($_('taxonomy.facts.seen_on', { default: 'Seen' }), formatDay(visits.lastSeen), 'last')}
                                    {:else}
                                        {@render fact($_('taxonomy.facts.first_seen', { default: 'First seen' }), formatDay(visits.firstSeen), 'first')}
                                        {@render fact($_('taxonomy.facts.last_seen', { default: 'Last seen' }), formatDay(visits.lastSeen), 'last')}
                                    {/if}
                                </dl>
                            {/if}
                            {#if visits.kind === 'seen' || visits.kind === 'none'}
                                {#if scopeLine()}<p class="text-3xs text-slate-600 dark:text-slate-400" data-taxon-card-scope>{scopeLine()}</p>{/if}
                            {/if}
                        </section>

                        {#if pictureName && (isSpecies || describedRank)}
                            {#if referenceLoading}
                                <div class="space-y-1.5 border-t border-line-soft pt-3" aria-hidden="true">
                                    <div class="h-3 w-full animate-pulse rounded-sm bg-slate-100 motion-reduce:animate-none dark:bg-slate-800"></div>
                                    <div class="h-3 w-5/6 animate-pulse rounded-sm bg-slate-100 motion-reduce:animate-none dark:bg-slate-800"></div>
                                </div>
                            {:else if reference?.state === 'failed'}
                                <p class="border-t border-line-soft pt-3 text-2xs text-slate-600 dark:text-slate-400" data-taxon-card-description-failed>
                                    {$_('taxonomy.description_failed', { default: 'The description could not load.' })}
                                </p>
                            {:else if description}
                                <div class="space-y-1 border-t border-line-soft pt-3" data-taxon-card-description>
                                    <p class="line-clamp-3 text-xs leading-relaxed text-slate-700 dark:text-slate-300">{description}</p>
                                    {#if reference?.state === 'ready' && reference.summarySource}
                                        <p class="text-3xs text-slate-600 dark:text-slate-400" data-taxon-card-description-source>
                                            {$_('taxonomy.description_from', { values: { source: reference.summarySource }, default: 'From {source}' })}
                                        </p>
                                    {/if}
                                </div>
                            {/if}
                        {/if}

                        {#if isSpecies}
                            {#if namesResult === null}
                                <div class="h-3 w-2/5 animate-pulse rounded-sm bg-slate-100 motion-reduce:animate-none dark:bg-slate-800" aria-hidden="true"></div>
                            {:else if namesResult.state === 'failed'}
                                <p class="text-2xs text-slate-600 dark:text-slate-400" data-taxon-card-names-failed>{$_('taxonomy.names_failed', { default: 'Other names could not load.' })}</p>
                            {:else if nameGroups.length > 0}
                                <details class="group border-t border-line-soft" data-taxon-card-names>
                                    <summary class="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 rounded-md text-xs font-semibold text-slate-700 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-focus dark:text-slate-200 [&::-webkit-details-marker]:hidden">
                                        {$_('taxonomy.names_count', { values: { count: nameGroups.length }, default: '{count, plural, one {Names in # language} other {Names in # languages}}' })}
                                        <svg class="h-4 w-4 shrink-0 text-slate-500 dark:text-slate-400 transition-transform group-open:rotate-180 motion-reduce:transition-none" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m4 6 4 4 4-4" stroke-linecap="round" stroke-linejoin="round" /></svg>
                                    </summary>
                                    <dl class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 pb-1 text-xs">
                                        {#each nameGroups as group (group.language)}
                                            <dt class="text-slate-600 dark:text-slate-400" lang={$locale ?? undefined}>{group.label}</dt>
                                            <dd class="text-slate-800 dark:text-slate-100" lang={group.language}>{group.names.join(', ')}</dd>
                                        {/each}
                                    </dl>
                                    {#if namesResult.names.truncated}
                                        <p class="pb-1 text-3xs text-slate-600 dark:text-slate-400">{$_('taxonomy.names_truncated', { default: 'The catalogue holds more names than are shown.' })}</p>
                                    {/if}
                                </details>
                            {/if}
                        {/if}
                    </div>
                </div>
            </div>
        {/key}
        {#if overflowing && !scrolledToEnd}
            <!-- In the surface colour of either theme, over the last lines, never catching the pointer. -->
            <div class="pointer-events-none absolute inset-x-0 bottom-0 h-10 bg-linear-to-t/srgb from-surface to-transparent" aria-hidden="true" data-taxon-card-more></div>
        {/if}
    </div>
{/if}
