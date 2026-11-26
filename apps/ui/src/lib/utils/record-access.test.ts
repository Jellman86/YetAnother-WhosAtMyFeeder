import { describe, expect, it } from 'vitest';
import { canDownloadRecordClip, canWatchRecordVideo, recordingClipsOn, type RecordAccess } from './record-access';

const owner: RecordAccess = { isGuest: false, publicAccessShowClips: false, publicAccessAllowClipDownloads: false };
const guest = (showClips: boolean, downloads = false): RecordAccess => ({
    isGuest: true,
    publicAccessShowClips: showClips,
    publicAccessAllowClipDownloads: downloads
});

describe('who may watch a record\'s video', () => {
    it('lets the owner watch whatever the guest switches say', () => {
        expect(canWatchRecordVideo(owner)).toBe(true);
    });

    it('lets a guest watch only while the owner shares clips', () => {
        expect(canWatchRecordVideo(guest(true))).toBe(true);
        expect(canWatchRecordVideo(guest(false))).toBe(false);
    });
});

describe('who may download a record\'s clip', () => {
    it('lets the owner download, but never through a share link', () => {
        expect(canDownloadRecordClip(owner, { shared: false })).toBe(true);
        expect(canDownloadRecordClip(owner, { shared: true })).toBe(false);
    });

    it('lets a guest download only when clips are shown and downloads are allowed', () => {
        expect(canDownloadRecordClip(guest(true, true), { shared: false })).toBe(true);
        expect(canDownloadRecordClip(guest(true, false), { shared: false })).toBe(false);
        // Downloads switched on are no way round clips switched off.
        expect(canDownloadRecordClip(guest(false, true), { shared: false })).toBe(false);
    });
});

describe('whether a full visit can be fetched', () => {
    it('needs clips and recording clips on, read from the owner settings or else the public ones', () => {
        expect(recordingClipsOn({ clips_enabled: true, recording_clip_enabled: true }, null)).toBe(true);
        expect(recordingClipsOn(null, { clips_enabled: true, recording_clip_enabled: true })).toBe(true);
        expect(recordingClipsOn(null, { clips_enabled: true, recording_clip_enabled: false })).toBe(false);
        expect(recordingClipsOn({ clips_enabled: false, recording_clip_enabled: true }, { clips_enabled: true, recording_clip_enabled: true })).toBe(false);
        expect(recordingClipsOn(null, null)).toBe(false);
    });
});
