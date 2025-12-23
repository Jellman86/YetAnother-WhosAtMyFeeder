export interface Detection {
    id?: number;
    frigate_event: string;
    display_name: string;
    score: number;
    detection_time: string;
    camera_name: string;
    detection_index?: number;
    category_name?: string;
}

export interface SpeciesCount {
    species: string;
    count: number;
}

export interface Settings {
    frigate_url: string;
    mqtt_server: string;
    mqtt_port: number;
    mqtt_auth: boolean;
    mqtt_username?: string;
    mqtt_password?: string;
    classification_threshold: number;
    cameras: string[];
}

export interface SettingsUpdate {
    frigate_url: string;
    mqtt_server: string;
    mqtt_port: number;
    mqtt_auth: boolean;
    mqtt_username?: string;
    mqtt_password?: string;
    classification_threshold: number;
    cameras: string[];
}

const API_BASE = '/api';

async function handleResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
        const error = await response.text();
        throw new Error(error || `HTTP ${response.status}`);
    }
    return response.json();
}

export async function fetchEvents(limit = 50, offset = 0): Promise<Detection[]> {
    const response = await fetch(`${API_BASE}/events?limit=${limit}&offset=${offset}`);
    return handleResponse<Detection[]>(response);
}

export async function fetchSpecies(): Promise<SpeciesCount[]> {
    const response = await fetch(`${API_BASE}/species`);
    return handleResponse<SpeciesCount[]>(response);
}

export async function fetchSettings(): Promise<Settings> {
    const response = await fetch(`${API_BASE}/settings`);
    return handleResponse<Settings>(response);
}

export async function updateSettings(settings: SettingsUpdate): Promise<{ status: string }> {
    const response = await fetch(`${API_BASE}/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
    });
    return handleResponse<{ status: string }>(response);
}

export async function checkHealth(): Promise<{ status: string; service: string }> {
    const response = await fetch('/health');
    return handleResponse<{ status: string; service: string }>(response);
}

export interface FrigateTestResult {
    status: string;
    frigate_url: string;
    version: string;
}

export async function testFrigateConnection(): Promise<FrigateTestResult> {
    const response = await fetch(`${API_BASE}/frigate/test`);
    return handleResponse<FrigateTestResult>(response);
}

export async function fetchFrigateConfig(): Promise<any> {
    const response = await fetch(`${API_BASE}/frigate/config`);
    return handleResponse<any>(response);
}

export interface ClassifierStatus {
    loaded: boolean;
    error: string | null;
    labels_count: number;
    enabled: boolean;
}

export async function fetchClassifierStatus(): Promise<ClassifierStatus> {
    const response = await fetch(`${API_BASE}/classifier/status`);
    return handleResponse<ClassifierStatus>(response);
}

export function getSnapshotUrl(frigateEvent: string): string {
    return `${API_BASE}/frigate/${frigateEvent}/snapshot.jpg`;
}

export function getThumbnailUrl(frigateEvent: string): string {
    return `${API_BASE}/frigate/${frigateEvent}/thumbnail.jpg`;
}

export function getClipUrl(frigateEvent: string): string {
    return `${API_BASE}/frigate/${frigateEvent}/clip.mp4`;
}