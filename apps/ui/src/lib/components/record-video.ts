import type { VideoHeading } from './video-heading';

/** The clip the shared player shows: a record's, a share link's or a Garden capture's. */
export interface RecordVideo {
    frigateEvent: string;
    heading: VideoHeading | null;
    /** Set only for a share link, which plays its one clip without sign-in. */
    shareToken: string | null;
    playIntent: 'auto' | 'user';
}
