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
    class="switch-track"
>
    <span class="sr-only">{srLabel}</span>
    <!-- The kit draws the off and on tracks, the disabled state from aria-disabled, the thumb's
         side from aria-checked, and the focus ring. -->
    <span class="switch-thumb"></span>
</button>
