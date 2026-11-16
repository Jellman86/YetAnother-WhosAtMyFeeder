<script lang="ts">
    import { _ } from 'svelte-i18n';
</script>

<!-- OpenStreetMap's tiles are used on condition that the map credits its contributors, so the
     credit is part of every map and is drawn in the app's own ink rather than left to Leaflet. -->
<a
    href="https://www.openstreetmap.org/copyright"
    target="_blank"
    rel="noopener noreferrer"
    class="absolute bottom-0 right-0 z-10 inline-flex min-h-6 items-center rounded-tl-md bg-white px-2 text-2xs font-medium text-slate-700 underline underline-offset-2 focus-ring dark:bg-slate-900 dark:text-slate-200"
    data-map-credit
>
    {$_('common.map_credit', { default: '© OpenStreetMap contributors' })}
</a>
