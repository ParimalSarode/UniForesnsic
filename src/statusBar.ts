import * as vscode from 'vscode';
import { loopEngine } from './loopEngine';
import { LoopState } from './types';

/**
 * Manages the status bar item that shows loop state, iteration count, and elapsed time.
 */
export class StatusBar {
    private item: vscode.StatusBarItem;
    private timer: ReturnType<typeof setInterval> | null = null;

    constructor() {
        this.item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
        this.item.command = 'ralphLoopView.focus';
        this.update('idle');
        this.item.show();

        // Listen for state changes
        loopEngine.onStateChange((state) => this.update(state));
        loopEngine.onIterationEnd(() => this.update('running'));
    }

    private update(state: LoopState): void {
        const session = loopEngine.currentSession;

        // Clear existing timer
        if (this.timer) {
            clearInterval(this.timer);
            this.timer = null;
        }

        switch (state) {
            case 'running': {
                const iter = session ? `${session.currentIteration}/${session.maxIterations}` : '0/0';
                this.item.text = `$(sync~spin) Ralph: ${iter}`;
                this.item.tooltip = 'Ralph Loop is running — click to view sidebar';
                this.item.backgroundColor = undefined;

                // Update elapsed time every second
                this.timer = setInterval(() => {
                    if (session) {
                        const elapsed = this.formatElapsed(Date.now() - session.startTime);
                        this.item.text = `$(sync~spin) Ralph: ${session.currentIteration}/${session.maxIterations} · ${elapsed}`;
                    }
                }, 1000);
                break;
            }

            case 'paused':
                this.item.text = '$(debug-pause) Ralph: Paused';
                this.item.tooltip = 'Ralph Loop is paused — click to view sidebar';
                this.item.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
                break;

            case 'stopped':
                this.item.text = '$(debug-stop) Ralph: Stopping...';
                this.item.tooltip = 'Ralph Loop is stopping after current iteration';
                this.item.backgroundColor = new vscode.ThemeColor('statusBarItem.errorBackground');
                break;

            default:
                this.item.text = '$(circle-outline) Ralph Loop';
                this.item.tooltip = 'Ralph Loop — click to start';
                this.item.backgroundColor = undefined;
                break;
        }
    }

    private formatElapsed(ms: number): string {
        const seconds = Math.floor(ms / 1000) % 60;
        const minutes = Math.floor(ms / 60000);
        return `${minutes}m ${String(seconds).padStart(2, '0')}s`;
    }

    dispose(): void {
        if (this.timer) {
            clearInterval(this.timer);
        }
        this.item.dispose();
    }
}
