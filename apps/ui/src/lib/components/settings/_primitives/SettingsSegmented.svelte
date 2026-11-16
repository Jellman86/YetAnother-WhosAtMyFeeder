<script lang="ts" generics="T extends string">
    import { _ } from 'svelte-i18n';
    import Segmented from '../../ui/Segmented.svelte';

    interface Option {
        value: T;
        label: string;
        /** A line under the label; options that carry one are listed, one per line, with a radio. */
        sub?: string;
        meta?: string;
        /** A small colour sample beside the label (accent colour themes). */
        swatch?: string;
    }

    interface Props {
        value: T;
        options: Option[];
        onchange: (next: T) => void;
        /** The id of the visible label that names this set of options; each option is named by its own words. */
        labelledBy: string;
        /** Kept for callers; the shape now follows the options (see below). */
        layout?: 'tile' | 'card';
        columns?: 1 | 2 | 3;
    }

    let { value, options, onchange, labelledBy }: Props = $props();

    const uid = $props.id();
    // Short labels sit on one neutral track with the chosen one raised. Four or more choices, or
    // choices that need a sentence each, would not fit on one line: a select, or a radio list.
    const described = $derived(options.some((option) => option.sub || option.meta));
    const shape = $derived(described ? 'list' : options.length >= 4 ? 'select' : 'track');
    // A saved value none of the options name (set by an environment variable, say) is shown as
    // itself, so the select never claims a choice that is not the saved one.
    const unknownValue = $derived(value && !options.some((option) => option.value === value) ? value : null);
</script>

{#if shape === 'select'}
    <select
        class="select-base min-h-11 w-full"
        aria-labelledby={labelledBy}
        {value}
        onchange={(event) => onchange((event.currentTarget as HTMLSelectElement).value as T)}
    >
        {#if unknownValue}
            <option value={unknownValue}>{$_('settings.common.set_outside', { values: { value: unknownValue }, default: '{value} (set outside Settings)' })}</option>
        {/if}
        {#each options as option (option.value)}
            <option value={option.value}>{option.label}</option>
        {/each}
    </select>
{:else if shape === 'list'}
    <div class="space-y-1" role="radiogroup" aria-labelledby={labelledBy}>
        {#each options as option (option.value)}
            {@const active = option.value === value}
            <label class="flex min-h-11 cursor-pointer items-start gap-3 rounded-lg px-2 py-2 hover:bg-surface-raised has-focus-visible:ring-2 has-focus-visible:ring-focus">
                <input
                    type="radio"
                    class="mt-1 h-4 w-4 shrink-0 accent-accent"
                    name="{uid}-choice"
                    value={option.value}
                    checked={active}
                    onchange={() => onchange(option.value)}
                />
                <span class="min-w-0">
                    <span class="flex items-center gap-2 text-sm {active ? 'font-semibold text-strong' : 'font-medium text-strong'}">
                        {#if option.swatch}<span class="h-3 w-3 shrink-0 rounded-full {option.swatch}" aria-hidden="true"></span>{/if}
                        {option.label}
                    </span>
                    {#if option.sub}<span class="mt-0.5 block text-sm leading-snug text-muted">{option.sub}</span>{/if}
                    {#if option.meta}<span class="mt-0.5 block text-xs text-muted">{option.meta}</span>{/if}
                </span>
            </label>
        {/each}
    </div>
{:else}
    <!-- The shared choose-one track (components/ui/Segmented.svelte), so Settings and the Explorer
         mark a choice the same way. -->
    <Segmented {value} options={options.map(({ value: optionValue, label, swatch }) => ({ value: optionValue, label, swatch }))} {onchange} {labelledBy} />
{/if}
