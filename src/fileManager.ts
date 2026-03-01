import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import { logger } from './logger';

/**
 * Manages reading and writing of task, progress, and prompt files.
 * All file operations are relative to the current workspace root.
 */
export class FileManager {
    /**
     * Resolve a filename to an absolute path within the workspace.
     */
    resolvePath(filename: string): string | null {
        const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
        if (!workspaceFolder) {
            logger.error('No workspace folder open');
            return null;
        }
        if (path.isAbsolute(filename)) {
            return filename;
        }
        return path.join(workspaceFolder.uri.fsPath, filename);
    }

    /**
     * Read the task file contents.
     */
    async readTaskFile(filename: string): Promise<string | null> {
        const filePath = this.resolvePath(filename);
        if (!filePath) { return null; }

        try {
            const content = await fs.promises.readFile(filePath, 'utf-8');
            logger.debug(`Read task file: ${filePath} (${content.length} chars)`);
            return content;
        } catch (err) {
            logger.error(`Failed to read task file: ${filePath}`, err as Error);
            return null;
        }
    }

    /**
     * Read the progress file contents.
     */
    async readProgressFile(filename: string): Promise<string> {
        const filePath = this.resolvePath(filename);
        if (!filePath) { return ''; }

        try {
            const content = await fs.promises.readFile(filePath, 'utf-8');
            logger.debug(`Read progress file: ${filePath} (${content.length} chars)`);
            return content;
        } catch {
            // File might not exist yet — that's fine
            logger.debug(`Progress file does not exist yet: ${filePath}`);
            return '';
        }
    }

    /**
     * Read the optional prompt file contents.
     */
    async readPromptFile(filename: string): Promise<string | null> {
        if (!filename) { return null; }

        const filePath = this.resolvePath(filename);
        if (!filePath) { return null; }

        try {
            const content = await fs.promises.readFile(filePath, 'utf-8');
            logger.debug(`Read prompt file: ${filePath} (${content.length} chars)`);
            return content;
        } catch {
            logger.debug(`Prompt file not found: ${filePath}`);
            return null;
        }
    }

    /**
     * Append an entry to the progress file (never delete existing content).
     */
    async appendToProgressFile(filename: string, entry: string): Promise<boolean> {
        const filePath = this.resolvePath(filename);
        if (!filePath) { return false; }

        try {
            // Ensure the file exists
            const dir = path.dirname(filePath);
            await fs.promises.mkdir(dir, { recursive: true });

            await fs.promises.appendFile(filePath, entry + '\n', 'utf-8');
            logger.debug(`Appended to progress file: ${filePath}`);
            return true;
        } catch (err) {
            logger.error(`Failed to append to progress file: ${filePath}`, err as Error);
            return false;
        }
    }

    /**
     * Read the last N lines of a file (for completion marker detection).
     */
    async readLastLines(filename: string, lineCount: number = 20): Promise<string> {
        const filePath = this.resolvePath(filename);
        if (!filePath) { return ''; }

        try {
            const content = await fs.promises.readFile(filePath, 'utf-8');
            const lines = content.split('\n');
            return lines.slice(-lineCount).join('\n');
        } catch {
            return '';
        }
    }

    /**
     * Check if a file exists relative to workspace.
     */
    async fileExists(filename: string): Promise<boolean> {
        const filePath = this.resolvePath(filename);
        if (!filePath) { return false; }

        try {
            await fs.promises.access(filePath);
            return true;
        } catch {
            return false;
        }
    }

    /**
     * Open a file in the editor (used to anchor workspace context).
     */
    async openFileInEditor(filename: string): Promise<void> {
        const filePath = this.resolvePath(filename);
        if (!filePath) { return; }

        try {
            const doc = await vscode.workspace.openTextDocument(filePath);
            await vscode.window.showTextDocument(doc, { preview: false });
        } catch (err) {
            logger.error(`Failed to open file: ${filePath}`, err as Error);
        }
    }
}

export const fileManager = new FileManager();
