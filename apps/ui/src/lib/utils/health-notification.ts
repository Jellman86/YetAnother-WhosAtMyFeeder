/**
 * Why the backend's health is not ok, in a form the notification can word: "Health status:
 * degraded" says nothing an owner can act on. Read from the same `/health` reading that raised it.
 */
export type HealthNotificationCause = 'mqtt_down' | 'mqtt_not_configured' | 'frigate_down' | 'pipeline_critical' | 'other';

function record(value: unknown): Record<string, unknown> {
    return value && typeof value === 'object' ? (value as Record<string, unknown>) : {};
}

export function healthNotificationCause(health: unknown): HealthNotificationCause {
    const reading = record(health);
    const mqtt = String(record(reading.mqtt).connection_state ?? '').toLowerCase();
    if (mqtt === 'disconnected') return 'mqtt_down';
    if (mqtt === 'not_configured') return 'mqtt_not_configured';
    if (String(record(reading.frigate_api).state ?? '').toLowerCase() === 'unreachable') return 'frigate_down';
    if (record(reading.event_pipeline).critical_failure_active === true) return 'pipeline_critical';
    return 'other';
}
