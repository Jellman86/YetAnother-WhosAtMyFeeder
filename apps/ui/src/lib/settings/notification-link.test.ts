import { describe, expect, it } from 'vitest';
import { notificationLinkPreview } from './notification-link';

describe('notification link preview', () => {
    it('opens the detection here by default', () => {
        expect(notificationLinkPreview('yawamf', ' https://feeder.example.com/ ', '', 'abc')).toBe(
            'https://feeder.example.com/events?event=abc'
        );
    });
    it('opens the tracked object in Frigate when chosen', () => {
        expect(notificationLinkPreview('frigate', 'https://feeder.example.com', 'https://frigate.example.com/', 'a b')).toBe(
            'https://frigate.example.com/explore?event_id=a%20b'
        );
    });
    it('is honest about no link', () => {
        expect(notificationLinkPreview('yawamf', '', 'https://frigate.example.com', 'abc')).toBeNull();
        expect(notificationLinkPreview('frigate', 'https://feeder.example.com', '   ', 'abc')).toBeNull();
    });
});
