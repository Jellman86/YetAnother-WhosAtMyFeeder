import type { Guarded } from '../api/core';

/**
 * For tests only: a stand-in for a guarded read. Application code cannot make a `Guarded` read
 * except through the guarded client, which is the point of the type; a test states the claim here.
 */
export function asGuarded<T>(read: Promise<T>): Guarded<T> {
    return read as Guarded<T>;
}
