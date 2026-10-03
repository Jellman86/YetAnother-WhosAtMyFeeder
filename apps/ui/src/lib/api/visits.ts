import { API_BASE, fetchWithAbort } from './core';
import type { components, paths } from './generated/openapi';
import type { Detection } from './types';
import type { FetchEventsOptions } from './events';

type VisitResponse = components['schemas']['DetectionVisitResponse'];
export type DetectionVisit = Omit<VisitResponse, 'representative' | 'latest' | 'peak_capture' | 'start_time' | 'end_time'> & {
    start_time: string;
    end_time: string;
    representative: Detection;
    latest: Detection;
    peak_capture: Detection | null;
};
export interface VisitOptions extends FetchEventsOptions {
    startTime?: string;
    endTime?: string;
}

function requiredTimestamp(value: string | null): string {
    if (value === null || !Number.isFinite(Date.parse(value))) throw new Error('Capture time is unavailable');
    return value;
}

function detection(data: components['schemas']['DetectionResponse']): Detection {
    return {
        ...data,
        id: data.id ?? undefined,
        detection_time: requiredTimestamp(data.detection_time),
        observation_source: data.observation_source === 'manual_upload' ? 'manual_upload' : 'frigate',
        observation_location_source: data.observation_location_source === 'manual_pin' || data.observation_location_source === 'image_metadata' ? data.observation_location_source : null,
        archive_state: data.archive_state === 'pending' || data.archive_state === 'durable' || data.archive_state === 'unavailable' || data.archive_state === 'failed' ? data.archive_state : null,
        frigate_score: data.frigate_score ?? undefined,
        sub_label: data.sub_label ?? undefined,
        audio_species: data.audio_species ?? undefined,
        audio_score: data.audio_score ?? undefined,
        temperature: data.temperature ?? undefined,
        weather_condition: data.weather_condition ?? undefined,
        weather_cloud_cover: data.weather_cloud_cover ?? undefined,
        weather_wind_speed: data.weather_wind_speed ?? undefined,
        weather_wind_direction: data.weather_wind_direction ?? undefined,
        weather_precipitation: data.weather_precipitation ?? undefined,
        weather_rain: data.weather_rain ?? undefined,
        weather_snowfall: data.weather_snowfall ?? undefined,
        video_classification_score: data.video_classification_score ?? undefined,
        video_classification_label: data.video_classification_label ?? undefined,
        video_classification_timestamp: data.video_classification_timestamp ?? undefined,
        video_classification_status: data.video_classification_status === 'pending' || data.video_classification_status === 'processing' || data.video_classification_status === 'completed' || data.video_classification_status === 'failed' ? data.video_classification_status : null,
        // Producer diagnostics are loaded by the record's authoritative detail read.
        video_classification_diagnostics: undefined
    };
}

function query(options: VisitOptions): URLSearchParams {
    const params = new URLSearchParams();
    const fields = {
        limit: options.limit ?? 24, offset: options.offset ?? 0,
        start_date: options.startDate, end_date: options.endDate,
        start_time: options.startTime, end_time: options.endTime,
        species: options.species, camera: options.camera, sort: options.sort,
        favorites: options.favoritesOnly, audio_confirmed_only: options.audioConfirmedOnly,
        only_hidden: options.onlyHidden, multiple_species_only: options.multipleSpeciesOnly
    };
    for (const [key, value] of Object.entries(fields)) {
        if (value !== undefined && value !== false) params.set(key, String(value));
    }
    return params;
}

export async function fetchVisits(options: VisitOptions = {}): Promise<{ visits: DetectionVisit[]; total: number; gap_seconds: number }> {
    const result = await fetchWithAbort<paths['/api/visits']['get']['response']>(options.signal ? null : options.requestKey ?? 'visits', `${API_BASE}/visits?${query(options)}`, { signal: options.signal });
    return {
        ...result,
        visits: result.visits.map((visit) => ({
            ...visit, start_time: requiredTimestamp(visit.start_time), end_time: requiredTimestamp(visit.end_time), representative: detection(visit.representative), latest: detection(visit.latest),
            peak_capture: visit.peak_capture ? detection(visit.peak_capture) : null
        }))
    };
}

export async function fetchVisitCaptures(visitId: string, options: VisitOptions = {}): Promise<{ captures: Detection[]; total: number }> {
    const result = await fetchWithAbort<paths['/api/visits/{visit_id}/captures']['get']['response']>(options.signal ? null : options.requestKey ?? `visit-captures:${visitId}`, `${API_BASE}/visits/${encodeURIComponent(visitId)}/captures?${query(options)}`, { signal: options.signal });
    return { ...result, captures: result.captures.map(detection) };
}
