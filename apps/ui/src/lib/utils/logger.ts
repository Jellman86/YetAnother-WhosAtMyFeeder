/**
 * Structured logging utility for frontend
 *
 * Provides a consistent logging interface that can be easily
 * swapped out for production error tracking services.
 */

export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

interface LogContext {
    [key: string]: unknown;
}

export function formatErrorForLog(error: unknown, includeStack: boolean): unknown {
    if (!(error instanceof Error)) {
        return error;
    }

    return {
        message: error.message,
        ...(includeStack ? { stack: error.stack } : {}),
        name: error.name
    };
}

export function sanitizeLogContext(context: LogContext | undefined, includeStack: boolean): LogContext | undefined {
    if (!context) {
        return undefined;
    }

    return Object.fromEntries(
        Object.entries(context).map(([key, value]) => [key, formatErrorForLog(value, includeStack)])
    );
}

class Logger {
    private isDevelopment: boolean;

    constructor() {
        this.isDevelopment = import.meta.env.DEV || import.meta.env.MODE === 'development';
    }

    /**
     * Log debug message (only in development)
     */
    debug(message: string, context?: LogContext): void {
        if (this.isDevelopment) {
            console.debug(`[DEBUG] ${message}`, context || '');
        }
    }

    /**
     * Log informational message
     */
    info(message: string, context?: LogContext): void {
        if (this.isDevelopment) {
            console.info(`[INFO] ${message}`, context || '');
        }
        // In production, could send to analytics
    }

    /**
     * Log warning message
     */
    warn(message: string, context?: LogContext): void {
        console.warn(`[WARN] ${message}`, sanitizeLogContext(context, this.isDevelopment) || '');
        // In production, could send to error tracking
    }

    /**
     * Log error message
     */
    error(message: string, error?: unknown, context?: LogContext): void {
        const errorContext = {
            ...sanitizeLogContext(context, this.isDevelopment),
            error: formatErrorForLog(error, this.isDevelopment)
        };

        console.error(`[ERROR] ${message}`, errorContext);

        // In production, send to error tracking service (Sentry, LogRocket, etc.)
        // this.sendToErrorTracking(message, errorContext);
    }

    /**
     * Log SSE connection event
     */
    sseEvent(type: string, data?: unknown): void {
        if (this.isDevelopment) {
            console.log(`[SSE] ${type}`, data || '');
        }
    }

    /**
     * Log API request
     */
    apiRequest(method: string, url: string, context?: LogContext): void {
        if (this.isDevelopment) {
            console.log(`[API] ${method} ${url}`, context || '');
        }
    }

    /**
     * Log API response
     */
    apiResponse(method: string, url: string, status: number, context?: LogContext): void {
        if (this.isDevelopment) {
            const level = status >= 400 ? 'error' : status >= 300 ? 'warn' : 'log';
            console[level](`[API] ${method} ${url} → ${status}`, context || '');
        }
    }

    /**
     * Future: Send to production error tracking
     */
    private sendToErrorTracking(message: string, context: LogContext): void {
        // Example integration points:
        // - Sentry.captureException()
        // - LogRocket.captureException()
        // - Custom backend endpoint
    }
}

// Singleton instance
export const logger = new Logger();
