<script lang="ts">
    import { onMount } from 'svelte';
    import { setupWizardStore } from '../stores/setup_wizard.svelte';
    import WizardShell from '../components/setup/WizardShell.svelte';

    // First run: open the guided wizard and keep it up until the user finishes it,
    // even after the account step flips `initial_setup_complete`.
    onMount(() => {
        if (!setupWizardStore.active) {
            setupWizardStore.open('first_run');
        }
    });
</script>

{#if setupWizardStore.active}
    <div class="min-h-screen bg-surface-light dark:bg-surface-dark">
        <WizardShell />
    </div>
{/if}
