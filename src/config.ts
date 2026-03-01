import * as vscode from 'vscode';
import { AgentMode, BackpressureType } from './types';

/**
 * Typed wrapper around VS Code workspace configuration for ralphLoop settings.
 */
export class Config {
    private get cfg(): vscode.WorkspaceConfiguration {
        return vscode.workspace.getConfiguration('ralphLoop');
    }

    get maxIterations(): number {
        return this.cfg.get<number>('maxIterations', 50);
    }

    get defaultMode(): AgentMode {
        return this.cfg.get<AgentMode>('defaultMode', 'Fast');
    }

    get defaultModel(): string {
        return this.cfg.get<string>('defaultModel', 'Gemini 3 Flash');
    }

    get modelRegistryUrl(): string {
        return this.cfg.get<string>('modelRegistryUrl', '');
    }

    get promptFile(): string {
        return this.cfg.get<string>('promptFile', '');
    }

    get taskFile(): string {
        return this.cfg.get<string>('taskFile', 'PRD.md');
    }

    get progressFile(): string {
        return this.cfg.get<string>('progressFile', 'progress.txt');
    }

    get testCommand(): string {
        return this.cfg.get<string>('testCommand', 'npm run test');
    }

    get lintCommand(): string {
        return this.cfg.get<string>('lintCommand', 'npm run lint');
    }

    get buildCommand(): string {
        return this.cfg.get<string>('buildCommand', 'npm run build');
    }

    get packageCommand(): string {
        return this.cfg.get<string>('packageCommand', '');
    }

    get enabledBackpressure(): BackpressureType[] {
        return this.cfg.get<BackpressureType[]>('enabledBackpressure', []);
    }

    get useGit(): boolean {
        return this.cfg.get<boolean>('useGit', true);
    }

    get createBranchEverySession(): boolean {
        return this.cfg.get<boolean>('createBranchEverySession', false);
    }

    get notificationsEnabled(): boolean {
        return this.cfg.get<boolean>('notifications.enabled', true);
    }

    get notifyOnCompletion(): boolean {
        return this.cfg.get<boolean>('notifications.onCompletion', true);
    }

    get notifyOnError(): boolean {
        return this.cfg.get<boolean>('notifications.onError', true);
    }

    get notifyOnStop(): boolean {
        return this.cfg.get<boolean>('notifications.onStop', true);
    }

    get showProgressModal(): boolean {
        return this.cfg.get<boolean>('notifications.showProgressModal', false);
    }

    get includeStats(): boolean {
        return this.cfg.get<boolean>('notifications.includeStats', true);
    }

    get antigravityPort(): number {
        return this.cfg.get<number>('antigravity.port', 0);
    }

    get csrfToken(): string {
        return this.cfg.get<string>('antigravity.csrfToken', '');
    }

    get oauthToken(): string {
        return this.cfg.get<string>('antigravity.oauthToken', '');
    }

    get debugLogging(): boolean {
        return this.cfg.get<boolean>('debugLogging', false);
    }

    /** Update a setting value */
    async set<T>(key: string, value: T, global = true): Promise<void> {
        await this.cfg.update(key, value, global);
    }
}

export const config = new Config();
