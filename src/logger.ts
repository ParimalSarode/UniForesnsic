import * as vscode from 'vscode';
import { config } from './config';

/**
 * Centralized logging to the Ralph Loop output channel.
 */
export class Logger {
    private channel: vscode.OutputChannel;
    private _debugEnabled: boolean;

    constructor() {
        this.channel = vscode.window.createOutputChannel('Ralph Loop');
        this._debugEnabled = config.debugLogging;
    }

    get debugEnabled(): boolean {
        return this._debugEnabled;
    }

    set debugEnabled(value: boolean) {
        this._debugEnabled = value;
    }

    toggleDebug(): boolean {
        this._debugEnabled = !this._debugEnabled;
        this.info(`Debug logging ${this._debugEnabled ? 'enabled' : 'disabled'}`);
        return this._debugEnabled;
    }

    info(message: string): void {
        const line = `[${this.timestamp()}] ${message}`;
        this.channel.appendLine(line);
    }

    debug(message: string): void {
        if (this._debugEnabled) {
            const line = `[${this.timestamp()}] [DEBUG] ${message}`;
            this.channel.appendLine(line);
        }
    }

    warn(message: string): void {
        const line = `[${this.timestamp()}] [WARN] ${message}`;
        this.channel.appendLine(line);
    }

    error(message: string, error?: Error): void {
        const line = `[${this.timestamp()}] [ERROR] ${message}`;
        this.channel.appendLine(line);
        if (error?.stack) {
            this.channel.appendLine(error.stack);
        }
    }

    /** Log an iteration boundary marker */
    iterationBoundary(iteration: number, maxIterations: number): void {
        this.channel.appendLine('');
        this.channel.appendLine(`${'═'.repeat(60)}`);
        this.channel.appendLine(`  ITERATION ${iteration} / ${maxIterations}`);
        this.channel.appendLine(`${'═'.repeat(60)}`);
        this.channel.appendLine('');
    }

    /** Show the output channel */
    show(): void {
        this.channel.show(true);
    }

    dispose(): void {
        this.channel.dispose();
    }

    private timestamp(): string {
        return new Date().toISOString().replace('T', ' ').replace('Z', '');
    }
}

export const logger = new Logger();
