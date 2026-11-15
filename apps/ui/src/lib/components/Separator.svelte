<script lang="ts">
    /**
     * The "·" between two facts on one line. It takes the ink of the text around it, so it meets the
     * same contrast that text does in every theme, and screen readers skip it. `spaced` puts the
     * spaces inside it, for a line that is not laid out with a gap.
     */
    let { spaced = false }: { spaced?: boolean } = $props();
</script>

<span aria-hidden="true" data-separator>{spaced ? ' · ' : '·'}</span>
