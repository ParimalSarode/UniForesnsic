import * as vscode from 'vscode';
import * as cp from 'child_process';
import { config } from './config';
import { logger } from './logger';

/**
 * Manages git operations for the Ralph Loop session.
 * Auto-commits after each iteration and optionally creates branches per session.
 */
export class GitManager {
    /**
     * Create a new branch for the session.
     */
    async createSessionBranch(sessionId: string): Promise<string | null> {
        if (!config.createBranchEverySession) {
            return null;
        }

        const branchName = `ralph/${sessionId}`;
        try {
            await this.exec(`git checkout -b ${branchName}`);
            logger.info(`Created session branch: ${branchName}`);
            return branchName;
        } catch (err) {
            logger.error(`Failed to create branch: ${branchName}`, err as Error);
            return null;
        }
    }

    /**
     * Auto-commit all changes after an iteration.
     */
    async commitIteration(iteration: number): Promise<boolean> {
        if (!config.useGit) {
            return false;
        }

        try {
            // Check if there are changes to commit
            const status = await this.exec('git status --porcelain');
            if (!status.trim()) {
                logger.debug(`Iteration ${iteration}: no changes to commit`);
                return false;
            }

            await this.exec('git add -A');
            const message = `ralph: iteration ${iteration} auto-commit`;
            await this.exec(`git commit -m "${message}"`);
            logger.info(`Committed iteration ${iteration}`);
            return true;
        } catch (err) {
            logger.warn(`Failed to commit iteration ${iteration}: ${(err as Error).message}`);
            return false;
        }
    }

    /**
     * Check if the workspace is a git repository.
     */
    async isGitRepo(): Promise<boolean> {
        try {
            await this.exec('git rev-parse --is-inside-work-tree');
            return true;
        } catch {
            return false;
        }
    }

    private exec(command: string): Promise<string> {
        return new Promise((resolve, reject) => {
            const cwd = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
            if (!cwd) {
                reject(new Error('No workspace folder'));
                return;
            }

            cp.exec(command, { cwd, timeout: 30_000 }, (err, stdout, stderr) => {
                if (err) {
                    reject(new Error(stderr || err.message));
                } else {
                    resolve(stdout);
                }
            });
        });
    }
}

export const gitManager = new GitManager();
