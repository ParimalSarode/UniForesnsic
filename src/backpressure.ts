import * as vscode from 'vscode';
import * as cp from 'child_process';
import { BackpressureType, BackpressureResult } from './types';
import { config } from './config';
import { logger } from './logger';

/**
 * Runs backpressure validation commands (test/lint/build/package) after each iteration.
 * If a check fails, the error output is captured and can be injected into the next prompt.
 */
export class Backpressure {
    private getCommand(type: BackpressureType): string {
        switch (type) {
            case 'test': return config.testCommand;
            case 'lint': return config.lintCommand;
            case 'build': return config.buildCommand;
            case 'package': return config.packageCommand;
        }
    }

    /**
     * Run all enabled backpressure checks.
     * Returns results for each check, including pass/fail status and output.
     */
    async runChecks(): Promise<BackpressureResult[]> {
        const enabled = config.enabledBackpressure;
        if (enabled.length === 0) {
            logger.debug('No backpressure checks enabled');
            return [];
        }

        const results: BackpressureResult[] = [];

        for (const type of enabled) {
            const command = this.getCommand(type);
            if (!command) {
                logger.debug(`Skipping ${type}: no command configured`);
                continue;
            }

            logger.info(`Running backpressure check: ${type} → ${command}`);
            const result = await this.runCommand(type, command);
            results.push(result);

            if (!result.passed) {
                logger.warn(`Backpressure ${type} FAILED (exit ${result.exitCode})`);
            } else {
                logger.info(`Backpressure ${type} passed`);
            }
        }

        return results;
    }

    /**
     * Format backpressure failures into a string for prompt injection.
     */
    formatFailures(results: BackpressureResult[]): string | null {
        const failures = results.filter(r => !r.passed);
        if (failures.length === 0) { return null; }

        const sections = failures.map(f => {
            return `### ${f.type.toUpperCase()} FAILED (exit code ${f.exitCode})\n\`\`\`\n${f.output.slice(-2000)}\n\`\`\``;
        });

        return `## ⚠️ Backpressure Validation Failures\nThe following checks failed after the previous iteration. Please fix these issues:\n\n${sections.join('\n\n')}`;
    }

    private runCommand(type: BackpressureType, command: string): Promise<BackpressureResult> {
        return new Promise((resolve) => {
            const cwd = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
            if (!cwd) {
                resolve({
                    type,
                    passed: false,
                    output: 'No workspace folder open',
                    exitCode: -1,
                });
                return;
            }

            const proc = cp.exec(command, { cwd, timeout: 120_000, maxBuffer: 5 * 1024 * 1024 });
            let output = '';

            proc.stdout?.on('data', (data) => { output += data; });
            proc.stderr?.on('data', (data) => { output += data; });

            proc.on('close', (code) => {
                resolve({
                    type,
                    passed: code === 0,
                    output,
                    exitCode: code ?? -1,
                });
            });

            proc.on('error', (err) => {
                resolve({
                    type,
                    passed: false,
                    output: err.message,
                    exitCode: -1,
                });
            });
        });
    }
}

export const backpressure = new Backpressure();
