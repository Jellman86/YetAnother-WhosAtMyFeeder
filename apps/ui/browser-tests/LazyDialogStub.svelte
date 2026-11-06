<script lang="ts">
    let { name, onclose }: { name: string; onclose: () => void } = $props();
</script>

<div role="dialog" aria-label={name} class="fixed inset-8 bg-white p-4">
    <p>{name} is open</p>
    <button class="btn btn-secondary" onclick={onclose}>Close {name}</button>
</div>
