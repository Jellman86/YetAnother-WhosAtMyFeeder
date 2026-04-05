import { describe, expect, it } from 'vitest';

import jobsPageSource from './Jobs.svelte?raw';

describe('jobs page active work semantics', () => {
    it('renders actual active jobs instead of fake thread slots', () => {
        expect(jobsPageSource).toContain("from '../stores/backfill_status.svelte'");
        expect(jobsPageSource).toContain('let presentedActiveJobs = $derived.by(() =>');
        expect(jobsPageSource).toContain('{#each presentedActiveJobs as job (job.id)}');
        expect(jobsPageSource).toContain("jobs.coordinator_job', { default: 'Coordinator Job' }");
        expect(jobsPageSource).toContain("jobs.active_job', { default: 'Active Job' }");
        expect(jobsPageSource).not.toContain("from '../jobs/active-slots'");
        expect(jobsPageSource).not.toContain('activeSlotAssignments');
        expect(jobsPageSource).not.toContain('presentedActiveSlots');
        expect(jobsPageSource).not.toContain("jobs.thread_slot', { default: 'Thread {index}'");
        expect(jobsPageSource).not.toContain("jobs.thread_idle', { default: 'Idle' }");
    });

    it('keeps active jobs in a stable started-at order', () => {
        expect(jobsPageSource).toContain('const startedDiff = (left.startedAt ?? 0) - (right.startedAt ?? 0);');
        expect(jobsPageSource).toContain('return left.id.localeCompare(right.id);');
    });

    it('sorts recent jobs by newest terminal event and renders job icons', () => {
        expect(jobsPageSource).toContain('let recentJobs = $derived.by(() =>');
        expect(jobsPageSource).toContain('const finishedDiff = rightFinishedAt - leftFinishedAt;');
        expect(jobsPageSource).toContain('{#each recentJobs as job (job.id)}');
        expect(jobsPageSource).toContain('presentJobKindIcon(job.kind)');
    });

    it('explains that backfill cards represent coordinator work', () => {
        expect(jobsPageSource).toContain('function isBackfillKind(kind: string)');
        expect(jobsPageSource).toContain("jobs.coordinator_detail', { default: 'One coordinator job manages classifier worker capacity for this backfill.' }");
    });
});
