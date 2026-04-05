import type { Detection } from '../api';

type Translate = (key: string, options?: Record<string, unknown>) => string;

export interface VideoFailureInsight {
    errorCode: string;
    summary: string;
    causes: string[];
    checks: string[];
    isFrigateRelated: boolean;
}

function isEventHttpError(code: string): boolean {
    return code.startsWith('event_http_');
}

function isClipHttpError(code: string): boolean {
    return code.startsWith('clip_http_');
}

function isFrigateAvailabilityError(code: string): boolean {
    return (
        code === 'event_not_found' ||
        code === 'event_timeout' ||
        code === 'clip_timeout' ||
        code === 'event_request_error' ||
        code === 'clip_request_error' ||
        isEventHttpError(code) ||
        isClipHttpError(code)
    );
}

function isFrigateMediaError(code: string): boolean {
    return (
        isFrigateAvailabilityError(code) ||
        code === 'clip_not_found' ||
        code === 'clip_unavailable' ||
        code === 'clip_not_retained' ||
        code === 'frigate_retention_expired'
    );
}

function hasAccessibleMedia(detection: Detection): boolean {
    return detection.has_clip === true || detection.has_snapshot === true;
}

export function hasFrigateMediaIssue(detection: Detection): boolean {
    const code = String(detection.video_classification_error || '');
    if ((detection.has_frigate_event === false || code === 'event_not_found') && hasAccessibleMedia(detection)) {
        return false;
    }
    return (
        detection.has_frigate_event === false ||
        detection.has_snapshot === false ||
        detection.has_clip === false ||
        isFrigateMediaError(code)
    );
}

export function getVideoFailureInsight(detection: Detection, t: Translate): VideoFailureInsight {
    const code = String(detection.video_classification_error || 'unknown');

    if ((detection.has_frigate_event === false || code === 'event_not_found') && hasAccessibleMedia(detection)) {
        return {
            errorCode: code,
            summary: t('detection.video_analysis.errors.event_missing_media_cached', {
                default: 'Frigate event metadata is gone, but cached media is still available in YA-WAMF.'
            }),
            causes: [
                t('detection.video_analysis.error_details.causes.event_missing_media_cached', {
                    default: 'YA-WAMF already cached media for this detection, so playback can still work even though the Frigate event no longer resolves.'
                }),
                t('detection.video_analysis.error_details.causes.event_missing_media_cached_retention', {
                    default: 'Frigate may have rotated event metadata out of retention while YA-WAMF kept the derived snapshot or full-visit clip.'
                })
            ],
            checks: [
                t('detection.video_analysis.error_details.checks_items.use_cached_media', {
                    default: 'Use the available snapshot or full clip in YA-WAMF; no immediate action is required if playback works.'
                }),
                t('detection.video_analysis.error_details.checks_items.frigate_retention_if_unexpected', {
                    default: 'If this happened sooner than expected, review Frigate event retention settings.'
                })
            ],
            isFrigateRelated: true
        };
    }

    if (detection.has_frigate_event === false || code === 'event_not_found') {
        return {
            errorCode: code,
            summary: t('detection.video_analysis.errors.event_missing', { default: 'Event not found in Frigate.' }),
            causes: [
                t('detection.video_analysis.error_details.causes.event_missing_retention', {
                    default: 'Frigate removed or no longer retained the event before follow-up checks completed.'
                }),
                t('detection.video_analysis.error_details.causes.event_missing_restart', {
                    default: 'Frigate restarted or its database state changed, so this event id is no longer present.'
                })
            ],
            checks: [
                t('detection.video_analysis.error_details.checks_items.frigate_event_page', {
                    default: 'Open the same event in Frigate and verify it still exists.'
                }),
                t('detection.video_analysis.error_details.checks_items.retention_settings', {
                    default: 'Review Frigate retention/settings and storage health.'
                })
            ],
            isFrigateRelated: true
        };
    }

    if (code === 'clip_not_retained' || code === 'frigate_retention_expired' || detection.has_clip === false) {
        return {
            errorCode: code,
            summary: t('detection.video_analysis.errors.clip_not_retained', {
                default: 'Clip no longer retained in Frigate (outside retention window).'
            }),
            causes: [
                t('detection.video_analysis.error_details.causes.clip_retention', {
                    default: 'Clip retention window expired before video analysis ran.'
                }),
                t('detection.video_analysis.error_details.causes.clip_policy', {
                    default: 'Recording policy may keep snapshots/events but not clips for this camera.'
                })
            ],
            checks: [
                t('detection.video_analysis.error_details.checks_items.recording_policy', {
                    default: 'Check Frigate camera recording/detection retention policy.'
                }),
                t('detection.video_analysis.error_details.checks_items.reduce_delay', {
                    default: 'Reduce video analysis delay if clips are being cleaned up too quickly.'
                })
            ],
            isFrigateRelated: true
        };
    }

    if (code === 'clip_not_found' || code === 'clip_unavailable') {
        return {
            errorCode: code,
            summary: t('detection.video_analysis.errors.clip_unavailable', {
                default: 'Clip not available. Using snapshot analysis instead.'
            }),
            causes: [
                t('detection.video_analysis.error_details.causes.clip_pending', {
                    default: 'Frigate had not finished clip generation when video analysis attempted retrieval.'
                }),
                t('detection.video_analysis.error_details.causes.clip_removed', {
                    default: 'Clip was removed or never written even though the event was detected.'
                })
            ],
            checks: [
                t('detection.video_analysis.error_details.checks_items.clip_endpoint', {
                    default: 'Confirm Frigate clip endpoint for this event returns media.'
                }),
                t('detection.video_analysis.error_details.checks_items.frigate_logs', {
                    default: 'Check Frigate logs around this event time for recording errors.'
                })
            ],
            isFrigateRelated: true
        };
    }

    if (code === 'clip_invalid' || code === 'clip_decode_failed') {
        return {
            errorCode: code,
            summary: code === 'clip_invalid'
                ? t('detection.video_analysis.errors.clip_invalid', {
                    default: 'Clip format invalid. Using snapshot analysis instead.'
                })
                : t('detection.video_analysis.errors.clip_decode_failed', {
                    default: 'Clip could not be decoded. Using snapshot analysis instead.'
                }),
            causes: [
                t('detection.video_analysis.error_details.causes.clip_corrupt', {
                    default: 'Clip bytes were incomplete/corrupted or not a valid playable media file.'
                }),
                t('detection.video_analysis.error_details.causes.transcode_issue', {
                    default: 'Frigate/ffmpeg encoding output may be incompatible or interrupted.'
                })
            ],
            checks: [
                t('detection.video_analysis.error_details.checks_items.play_clip', {
                    default: 'Try downloading and playing the clip directly from Frigate.'
                }),
                t('detection.video_analysis.error_details.checks_items.ffmpeg_health', {
                    default: 'Review Frigate ffmpeg/recording health and hardware acceleration logs.'
                })
            ],
            isFrigateRelated: true
        };
    }

    if (code === 'event_timeout' || code === 'clip_timeout') {
        return {
            errorCode: code,
            summary: t('detection.video_analysis.errors.timeout', {
                default: 'Frigate timed out while preparing the clip.'
            }),
            causes: [
                t('detection.video_analysis.error_details.causes.timeout_load', {
                    default: 'Frigate was slow or overloaded while event/clip metadata was requested.'
                }),
                t('detection.video_analysis.error_details.causes.timeout_network', {
                    default: 'Temporary network or reverse-proxy latency caused request timeout.'
                })
            ],
            checks: [
                t('detection.video_analysis.error_details.checks_items.container_load', {
                    default: 'Check Frigate container CPU/IO load at detection time.'
                }),
                t('detection.video_analysis.error_details.checks_items.network_path', {
                    default: 'Verify container-to-container networking and proxy path stability.'
                })
            ],
            isFrigateRelated: true
        };
    }

    if (isFrigateAvailabilityError(code)) {
        return {
            errorCode: code,
            summary: t('detection.video_analysis.errors.frigate_unavailable', {
                default: 'Frigate is unavailable. Using snapshot analysis instead.'
            }),
            causes: [
                t('detection.video_analysis.error_details.causes.frigate_unreachable', {
                    default: 'Frigate API could not be reached from YA-WAMF at this moment.'
                }),
                t('detection.video_analysis.error_details.causes.frigate_http_error', {
                    default: 'Frigate or reverse proxy returned a non-success HTTP response.'
                })
            ],
            checks: [
                t('detection.video_analysis.error_details.checks_items.api_health', {
                    default: 'Verify Frigate API health endpoint and auth configuration.'
                }),
                t('detection.video_analysis.error_details.checks_items.proxy_config', {
                    default: 'Review reverse-proxy routing and trusted proxy settings.'
                })
            ],
            isFrigateRelated: true
        };
    }

    if (code === 'video_timeout') {
        return {
            errorCode: code,
            summary: t('detection.video_analysis.error_details.video_timeout_summary', {
                default: 'Video classifier timed out before producing a result.'
            }),
            causes: [
                t('detection.video_analysis.error_details.causes.video_timeout_large_clip', {
                    default: 'Clip processing took longer than configured timeout.'
                }),
                t('detection.video_analysis.error_details.causes.video_timeout_resource', {
                    default: 'GPU/CPU resources were saturated while running inference.'
                })
            ],
            checks: [
                t('detection.video_analysis.error_details.checks_items.video_timeout_setting', {
                    default: 'Increase video analysis timeout or reduce sampled frames.'
                }),
                t('detection.video_analysis.error_details.checks_items.inference_resources', {
                    default: 'Check inference runtime/device utilization.'
                })
            ],
            isFrigateRelated: false
        };
    }

    if (code === 'video_no_results') {
        return {
            errorCode: code,
            summary: t('detection.video_analysis.errors.no_results', {
                default: 'Video analysis returned no results.'
            }),
            causes: [
                t('detection.video_analysis.error_details.causes.no_results_frames', {
                    default: 'Sampled frames did not contain usable bird features.'
                }),
                t('detection.video_analysis.error_details.causes.no_results_quality', {
                    default: 'Motion blur, occlusion, or low light prevented confident classification.'
                })
            ],
            checks: [
                t('detection.video_analysis.error_details.checks_items.retry_snapshot', {
                    default: 'Try manual snapshot or video reclassification later.'
                }),
                t('detection.video_analysis.error_details.checks_items.camera_quality', {
                    default: 'Review camera focus/exposure around feeder area.'
                })
            ],
            isFrigateRelated: false
        };
    }

    if (code === 'circuit_open' || code === 'stale_timeout' || code === 'video_cancelled' || code === 'video_exception') {
        return {
            errorCode: code,
            summary: t('detection.video_analysis.error_details.pipeline_summary', {
                default: 'Video analysis pipeline failed before completion.'
            }),
            causes: [
                t('detection.video_analysis.error_details.causes.pipeline_guard', {
                    default: 'Safety guard/circuit breaker paused background video jobs after repeated failures.'
                }),
                t('detection.video_analysis.error_details.causes.pipeline_exception', {
                    default: 'A runtime exception or cancellation interrupted the classification task.'
                })
            ],
            checks: [
                t('detection.video_analysis.error_details.checks_items.backend_logs', {
                    default: 'Check YA-WAMF backend logs around this detection for the exact exception.'
                }),
                t('detection.video_analysis.error_details.checks_items.retry_manual', {
                    default: 'Retry manual reclassification after service health stabilizes.'
                })
            ],
            isFrigateRelated: false
        };
    }

    return {
        errorCode: code,
        summary: t('detection.video_analysis.errors.unknown', {
            default: 'Video analysis failed. Using snapshot analysis instead.'
        }),
        causes: [
            t('detection.video_analysis.error_details.causes.unknown_1', {
                default: 'An unexpected error occurred in media retrieval or video processing.'
            }),
            t('detection.video_analysis.error_details.causes.unknown_2', {
                default: 'The event state changed while analysis was in progress.'
            })
        ],
        checks: [
            t('detection.video_analysis.error_details.checks_items.backend_logs', {
                default: 'Check YA-WAMF backend logs for technical details.'
            }),
            t('detection.video_analysis.error_details.checks_items.retry_manual', {
                default: 'Retry manual reclassification once services are healthy.'
            })
        ],
        isFrigateRelated: false
    };
}
