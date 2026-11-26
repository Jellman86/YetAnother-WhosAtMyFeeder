/**
 * What a record may offer is decided by who is looking, never by the page it was opened from:
 * the owner sees everything, a guest sees what the owner's public-access switches share.
 */
export interface RecordAccess {
    isGuest: boolean;
    publicAccessShowClips: boolean;
    publicAccessAllowClipDownloads: boolean;
}

interface ClipSettings {
    clips_enabled?: boolean;
    recording_clip_enabled?: boolean;
}

export function canWatchRecordVideo(access: RecordAccess): boolean {
    return !access.isGuest || access.publicAccessShowClips;
}

/** A share link plays one clip and nothing more, so it never offers the file. */
export function canDownloadRecordClip(access: RecordAccess, { shared }: { shared: boolean }): boolean {
    if (shared || !canWatchRecordVideo(access)) return false;
    return !access.isGuest || access.publicAccessAllowClipDownloads;
}

/** A guest cannot read the owner's settings, so the public projection answers for them. */
export function recordingClipsOn(settings: ClipSettings | null | undefined, publicSettings: ClipSettings | null | undefined): boolean {
    const clips = settings?.clips_enabled ?? publicSettings?.clips_enabled ?? false;
    const recordings = settings?.recording_clip_enabled ?? publicSettings?.recording_clip_enabled ?? false;
    return clips && recordings;
}
