import * as vscode from 'vscode';
import { loopEngine } from './loopEngine';
import { config } from './config';
import { modelRegistry } from './modelRegistry';

/**
 * Tree item types for the sidebar view.
 */
type SidebarItemType = 'status' | 'config' | 'action' | 'info';

class SidebarItem extends vscode.TreeItem {
    constructor(
        public readonly label: string,
        public readonly itemType: SidebarItemType,
        public readonly value?: string,
        public readonly commandId?: string,
    ) {
        super(label, vscode.TreeItemCollapsibleState.None);

        if (value) {
            this.description = value;
        }

        if (commandId) {
            this.command = {
                command: commandId,
                title: label,
            };
        }

        // Set icons based on type
        switch (itemType) {
            case 'status':
                this.iconPath = new vscode.ThemeIcon('info');
                break;
            case 'config':
                this.iconPath = new vscode.ThemeIcon('settings-gear');
                break;
            case 'action':
                this.iconPath = new vscode.ThemeIcon('play');
                break;
            case 'info':
                this.iconPath = new vscode.ThemeIcon('book');
                break;
        }
    }
}

/**
 * Provides the sidebar TreeView for the Ralph Loop panel.
 * Displays session status and configuration options.
 */
export class SidebarProvider implements vscode.TreeDataProvider<SidebarItem> {
    private _onDidChangeTreeData = new vscode.EventEmitter<SidebarItem | undefined>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    constructor() {
        // Refresh the tree when loop state changes
        loopEngine.onStateChange(() => this.refresh());
        loopEngine.onIterationEnd(() => this.refresh());
    }

    refresh(): void {
        this._onDidChangeTreeData.fire(undefined);
    }

    getTreeItem(element: SidebarItem): vscode.TreeItem {
        return element;
    }

    getChildren(): SidebarItem[] {
        const session = loopEngine.currentSession;
        const items: SidebarItem[] = [];

        // --- Session Status ---
        if (session && session.state !== 'idle') {
            const elapsed = this.formatElapsed(Date.now() - session.startTime);
            const stateIcon = this.stateEmoji(session.state);

            items.push(new SidebarItem('Status', 'status', `${stateIcon} ${session.state.toUpperCase()}`));
            items.push(new SidebarItem('Iteration', 'status', `${session.currentIteration} / ${session.maxIterations}`));
            items.push(new SidebarItem('Elapsed', 'status', elapsed));
            items.push(new SidebarItem('Mode', 'status', session.mode));
            items.push(new SidebarItem('Model', 'status', session.model));
            items.push(new SidebarItem('Marker', 'status', session.completionMarker));

            // Separator
            items.push(new SidebarItem('─── Controls ───', 'info'));
            if (session.state === 'running') {
                items.push(new SidebarItem('⏸️ Pause', 'action', undefined, 'ralph.pause'));
                items.push(new SidebarItem('🛑 Stop', 'action', undefined, 'ralph.stop'));
                items.push(new SidebarItem('🔴 Emergency Stop', 'action', undefined, 'ralph.emergency'));
            } else if (session.state === 'paused') {
                items.push(new SidebarItem('▶️ Resume', 'action', undefined, 'ralph.pause'));
                items.push(new SidebarItem('🛑 Stop', 'action', undefined, 'ralph.stop'));
            }
        } else {
            items.push(new SidebarItem('Status', 'status', '⏹️ IDLE'));
            items.push(new SidebarItem('▶️ Start Loop', 'action', undefined, 'ralph.start'));
        }

        // --- Configuration ---
        items.push(new SidebarItem('─── Configuration ───', 'info'));
        items.push(new SidebarItem('Mode', 'config', config.defaultMode, 'ralph.setConfigMode'));
        items.push(new SidebarItem('Model', 'config', config.defaultModel, 'ralph.setConfigModel'));
        items.push(new SidebarItem('Max Iterations', 'config', `${config.maxIterations}`, 'ralph.configureIterations'));
        items.push(new SidebarItem('Task File', 'config', config.taskFile || '(not set)', 'ralph.setConfigTaskFile'));
        items.push(new SidebarItem('Progress File', 'config', config.progressFile || 'progress.txt'));
        items.push(new SidebarItem('Prompt File', 'config', config.promptFile || '(none)', 'ralph.setConfigPromptFile'));
        items.push(new SidebarItem('Use Git', 'config', config.useGit ? '✅' : '❌', 'ralph.toggleUseGit'));
        items.push(new SidebarItem('Branch/Session', 'config', config.createBranchEverySession ? '✅' : '❌', 'ralph.toggleCreateBranchEverySession'));

        return items;
    }

    private formatElapsed(ms: number): string {
        const seconds = Math.floor(ms / 1000) % 60;
        const minutes = Math.floor(ms / 60000);
        return `${minutes}m ${seconds}s`;
    }

    private stateEmoji(state: string): string {
        switch (state) {
            case 'running': return '🟢';
            case 'paused': return '🟡';
            case 'stopped': return '🔴';
            default: return '⏹️';
        }
    }

    dispose(): void {
        this._onDidChangeTreeData.dispose();
    }
}

/**
 * Help & Feedback sidebar view.
 */
export class HelpProvider implements vscode.TreeDataProvider<SidebarItem> {
    private _onDidChangeTreeData = new vscode.EventEmitter<SidebarItem | undefined>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    getTreeItem(element: SidebarItem): vscode.TreeItem {
        return element;
    }

    getChildren(): SidebarItem[] {
        return [
            new SidebarItem('📖 Documentation', 'info', undefined, 'ralph.reportBug'),
            new SidebarItem('🐛 Report a Bug', 'action', undefined, 'ralph.reportBug'),
            new SidebarItem('🔧 Toggle Debug Logging', 'action', undefined, 'ralph.toggleDebugLogging'),
        ];
    }
}
