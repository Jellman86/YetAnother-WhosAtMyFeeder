import { explorerWindow, type ExplorerWindow } from './explorer-query';

/**
 * The window of the Explorer results on screen.
 *
 * A read works out its own window and publishes it only with the results it read. An expanded
 * visit, a Garden capture read and the heard calls follow this window, so none of them asks about
 * a window the screen is not showing: not while a refresh is in flight, and not after one fails.
 */
export class ShownExplorerWindow {
    current = $state.raw<ExplorerWindow>(explorerWindow('all', {}, new Date(0)));

    publish(window: ExplorerWindow): void {
        this.current = window;
    }
}
