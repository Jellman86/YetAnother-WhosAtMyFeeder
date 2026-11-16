<script lang="ts">
    import StatusIcon from './StatusIcon.svelte';
    import { TONE_CHIP, type Tone } from './tone';

    /**
     * A state in words: the label, an icon whose shape follows the tone, and the tone's colours.
     * The label always carries the meaning; colour and shape only help the eye find it.
     */
    type Props = {
        tone: Tone;
        label: string;
        /** Extra detail on hover, such as the raw word the backend reported. */
        title?: string;
        size?: 'sm' | 'md';
        class?: string;
    };

    let { tone, label, title, size = 'sm', class: className = '' }: Props = $props();
</script>

<span
    class="inline-flex max-w-full items-center gap-1.5 rounded-full border font-semibold {TONE_CHIP[tone]} {size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-sm'} {className}"
    {title}
    data-status-chip={tone}
>
    <StatusIcon {tone} class={size === 'sm' ? 'h-3.5 w-3.5' : 'h-4 w-4'} />
    <span class="min-w-0 wrap-break-word">{label}</span>
</span>
