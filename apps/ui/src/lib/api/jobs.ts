import type { paths } from './generated/openapi';

export type JobsSnapshot = paths['/api/jobs']['get']['response'];
export type ServerJob = JobsSnapshot['items'][number];
