/** The HTTP fixtures model group pagination separately from capture pagination. */
import type { GardenCapture } from '../src/lib/api/garden';
import { groupGardenVisits } from '../src/lib/utils/garden-explorer';

export function gardenVisitResponse(items: readonly unknown[], url: URL): object {
    const groups = groupGardenVisits(items as GardenCapture[]);
    const limit = Number(url.searchParams.get('limit') ?? 24);
    const offset = Number(url.searchParams.get('offset') ?? 0);
    if (url.pathname.endsWith('/captures')) {
        const id = decodeURIComponent(url.pathname.split('/').at(-2) ?? '');
        const members = groups.find((group) => group.id === id)?.items ?? [];
        return { items: members.slice(offset, offset + limit), total: members.length, offset, limit };
    }
    return { visits: groups.slice(offset, offset + limit).map((group) => ({
        id: group.id, kind: group.kind, capture_count: group.items.length,
        start_time: group.items.at(-1)?.observed_at, end_time: group.items[0].observed_at,
        representative: group.items[0]
    })), total: groups.length, capture_total: items.length, limit, offset };
}
