import * as vscode from 'vscode';
import { loopEngine } from './loopEngine';
import { config } from './config';
import { logger } from './logger';
import { modelRegistry } from './modelRegistry';
import { fileManager } from './fileManager';
import { SidebarProvider, HelpProvider } from './sidebarProvider';
import { StatusBar } from './statusBar';
import { AgentMode } from './types';

let sidebarProvider: SidebarProvider;
let helpProvider: HelpProvider;
let statusBar: StatusBar;

/**
 * Extension entry point — called when the extension is activated.
 */
export function activate(context: vscode.ExtensionContext): void {
    logger.info('Ralph Loop extension activating...');

    // Initialize model registry
    modelRegistry.load();

    // Register sidebar views
    sidebarProvider = new SidebarProvider();
    helpProvider = new HelpProvider();

    context.subscriptions.push(
        vscode.window.registerTreeDataProvider('ralphLoopView', sidebarProvider),
        vscode.window.registerTreeDataProvider('ralphHelpView', helpProvider),
    );

    // Register status bar
    statusBar = new StatusBar();
    context.subscriptions.push(statusBar as unknown as vscode.Disposable);

    // ── Commands ──────────────────────────────────────────────────

    // Start loop
    context.subscriptions.push(
        vscode.commands.registerCommand('ralph.start', async () => {
            const taskFile = config.taskFile;
            const progressFile = config.progressFile;
            const promptFile = config.promptFile || null;
            const mode = config.defaultMode;
            const model = config.defaultModel;
            const maxIterations = config.maxIterations;

            if (!taskFile) {
                const selected = await vscode.window.showOpenDialog({
                    canSelectMany: false,
                    openLabel: 'Select Task File',
                    filters: { 'Markdown': ['md'], 'All Files': ['*'] },
                });
                if (!selected || selected.length === 0) { return; }
                await config.set('taskFile', vscode.workspace.asRelativePath(selected[0]));
            }

            await loopEngine.startLoop({
                taskFile: config.taskFile,
                progressFile,
                promptFile,
                mode,
                model,
                maxIterations,
            });
        })
    );

    // Stop loop
    context.subscriptions.push(
        vscode.commands.registerCommand('ralph.stop', () => {
            loopEngine.stopLoop();
        })
    );

    // Pause/Resume
    context.subscriptions.push(
        vscode.commands.registerCommand('ralph.pause', () => {
            loopEngine.togglePause();
        })
    );

    // Emergency Stop
    context.subscriptions.push(
        vscode.commands.registerCommand('ralph.emergency', () => {
            loopEngine.emergencyStop();
        })
    );

    // Select task file
    context.subscriptions.push(
        vscode.commands.registerCommand('ralph.selectTaskFile', async () => {
            const selected = await vscode.window.showOpenDialog({
                canSelectMany: false,
                openLabel: 'Select Task File',
                filters: { 'Markdown': ['md', 'txt'], 'All Files': ['*'] },
            });
            if (selected && selected.length > 0) {
                const relative = vscode.workspace.asRelativePath(selected[0]);
                await config.set('taskFile', relative);
                sidebarProvider.refresh();
                logger.info(`Task file set to: ${relative}`);
            }
        })
    );

    // Configure max iterations
    context.subscriptions.push(
        vscode.commands.registerCommand('ralph.configureIterations', async () => {
            const input = await vscode.window.showInputBox({
                prompt: 'Maximum number of iterations',
                value: `${config.maxIterations}`,
                validateInput: (v) => {
                    const n = parseInt(v, 10);
                    if (isNaN(n) || n < 1 || n > 1000) { return 'Enter a number between 1 and 1000'; }
                    return null;
                },
            });
            if (input) {
                await config.set('maxIterations', parseInt(input, 10));
                sidebarProvider.refresh();
            }
        })
    );

    // Set mode
    context.subscriptions.push(
        vscode.commands.registerCommand('ralph.setConfigMode', async () => {
            const modes: AgentMode[] = ['Fast', 'Planning'];
            const selected = await vscode.window.showQuickPick(modes, { placeHolder: 'Select mode' });
            if (selected) {
                await config.set('defaultMode', selected);
                sidebarProvider.refresh();
            }
        })
    );

    // Set model
    context.subscriptions.push(
        vscode.commands.registerCommand('ralph.setConfigModel', async () => {
            const models = modelRegistry.getDisplayNames();
            const selected = await vscode.window.showQuickPick(models, { placeHolder: 'Select AI model' });
            if (selected) {
                await config.set('defaultModel', selected);
                sidebarProvider.refresh();
            }
        })
    );

    // Set prompt file
    context.subscriptions.push(
        vscode.commands.registerCommand('ralph.setConfigPromptFile', async () => {
            const items = [
                { label: '$(file) Select file...', value: 'select' },
                { label: '$(close) Clear prompt file', value: 'clear' },
            ];
            const choice = await vscode.window.showQuickPick(items, { placeHolder: 'Prompt file' });
            if (choice?.value === 'select') {
                const selected = await vscode.window.showOpenDialog({
                    canSelectMany: false,
                    openLabel: 'Select Prompt File',
                    filters: { 'Markdown': ['md'], 'All Files': ['*'] },
                });
                if (selected && selected.length > 0) {
                    const relative = vscode.workspace.asRelativePath(selected[0]);
                    await config.set('promptFile', relative);
                    sidebarProvider.refresh();
                }
            } else if (choice?.value === 'clear') {
                await config.set('promptFile', '');
                sidebarProvider.refresh();
            }
        })
    );

    // Set task file
    context.subscriptions.push(
        vscode.commands.registerCommand('ralph.setConfigTaskFile', async () => {
            const selected = await vscode.window.showOpenDialog({
                canSelectMany: false,
                openLabel: 'Select Task File',
                filters: { 'Markdown': ['md', 'txt'], 'All Files': ['*'] },
            });
            if (selected && selected.length > 0) {
                const relative = vscode.workspace.asRelativePath(selected[0]);
                await config.set('taskFile', relative);
                sidebarProvider.refresh();
                logger.info(`Task file set to: ${relative}`);
            }
        })
    );

    // Toggle git
    context.subscriptions.push(
        vscode.commands.registerCommand('ralph.toggleUseGit', async () => {
            await config.set('useGit', !config.useGit);
            sidebarProvider.refresh();
        })
    );

    // Toggle branch per session
    context.subscriptions.push(
        vscode.commands.registerCommand('ralph.toggleCreateBranchEverySession', async () => {
            await config.set('createBranchEverySession', !config.createBranchEverySession);
            sidebarProvider.refresh();
        })
    );

    // Report bug
    context.subscriptions.push(
        vscode.commands.registerCommand('ralph.reportBug', () => {
            vscode.env.openExternal(vscode.Uri.parse('https://github.com/GindaChen/ralph-loop-antigravity/issues'));
        })
    );

    // Toggle debug logging
    context.subscriptions.push(
        vscode.commands.registerCommand('ralph.toggleDebugLogging', () => {
            const enabled = logger.toggleDebug();
            vscode.window.showInformationMessage(`Debug logging ${enabled ? 'enabled' : 'disabled'}`);
        })
    );

    // Set initial context
    vscode.commands.executeCommand('setContext', 'ralph.isRunning', false);

    logger.info('✅ Ralph Loop extension activated');
}

/**
 * Extension cleanup — called when the extension is deactivated.
 */
export function deactivate(): void {
    logger.info('Ralph Loop extension deactivating...');
    loopEngine.emergencyStop();
    loopEngine.dispose();
    sidebarProvider?.dispose();
    statusBar?.dispose();
    logger.dispose();
}
