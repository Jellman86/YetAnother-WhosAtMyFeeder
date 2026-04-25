<script lang="ts">
    interface Props {
        checked: boolean;
        // ID of the element whose text should announce the toggle (usually the
        // SettingsRow label container).  Required for screen-reader correctness.
        labelledBy: string;
        srLabel: string;
        disabled?: boolean;
        onchange: (next: boolean) => void;
    }

    let { checked, labelledBy, srLabel, disabled = false, onchange }: Props = $props();

    function toggle() {
        if (disabled) return;
        onchange(!checked);
    }
</script>

<button
    type="button"
    role="switch"
    aria-checked={checked}
    aria-labelledby={labelledBy}
    aria-disabled={disabled || undefined}
    onclick={toggle}
    onkeydown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            toggle();
        }
    }}
    class="relative inline-flex h-6 w-11 flex-shrink-0 rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-teal-400 dark:focus:ring-offset-slate-900
           {disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
           {checked ? 'bg-teal-500' : 'bg-slate-300 dark:bg-slate-600'}"
>
    <span class="sr-only">{srLabel}</span>
    <span
        class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {checked ? 'translate-x-5' : 'translate-x-0'}"
    ></span>
</button>
