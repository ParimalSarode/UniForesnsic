import * as vscode from 'vscode';
import * as crypto from 'crypto';
import { LoopSession, LoopState, IterationResult, AgentMode, BackpressureResult } from './types';
import { config } from './config';
import { logger } from './logger';
import { fileManager } from './fileManager';
import { completionDetector } from './completionDetector';
import { backpressure } from './backpressure';
import { antigravityClient } from './antigravityClient';
import { gitManager } from './gitManager';

/**
 * Core loop orchestrator — manages the iterative execution cycle.
 *
 * State machine: idle → running ↔ paused → stopped → idle
 *
 * Each iteration:
 * 1. Check completion marker → stop if found
 * 2. Read task file, progress file, prompt file
 * 3. Compose structured prompt
 * 4. Send to Antigravity agent
 * 5. Wait for agent to complete
 * 6. Run backpressure checks (if enabled)
 * 7. Auto-commit (if enabled)
 * 8. Update UI
 * 9. Repeat or stop
 */
export class LoopEngine extends vscode.EventEmitter<string> {
    private session: LoopSession | null = null;
    private _abortController: AbortController | null = null;
    private _onStateChange = new vscode.EventEmitter<LoopState>();
    private _onIterationEnd = new vscode.EventEmitter<IterationResult>();
    private _onSessionEnd = new vscode.EventEmitter<LoopSession>();

    readonly onStateChange = this._onStateChange.event;
    readonly onIterationEnd = this._onIterationEnd.event;
    readonly onSessionEnd = this._onSessionEnd.event;

    get currentSession(): LoopSession | null {
        return this.session;
    }

    get state(): LoopState {
        return this.session?.state ?? 'idle';
    }

    /**
     * Start a new loop session.
     */
    async startLoop(options: {
        taskFile: string;
        progressFile: string;
        promptFile: string | null;
        mode: AgentMode;
        model: string;
        maxIterations: number;
    }): Promise<void> {
        if (this.session?.state === 'running') {
            vscode.window.showWarningMessage('Ralph Loop is already running');
            return;
        }

        // Validate task file exists
        if (!await fileManager.fileExists(options.taskFile)) {
            vscode.window.showErrorMessage(`Task file not found: ${options.taskFile}`);
            return;
        }

        // Connect to Antigravity
        logger.info('Connecting to Antigravity...');
        const connected = await antigravityClient.connect();
        if (!connected) {
            vscode.window.showErrorMessage(
                'Could not connect to Antigravity. Check port configuration (ralphLoop.antigravity.port).'
            );
            return;
        }

        // Generate session
        const sessionId = crypto.randomBytes(4).toString('hex');
        const marker = completionDetector.generateMarker();

        this.session = {
            id: sessionId,
            taskFile: options.taskFile,
            progressFile: options.progressFile,
            promptFile: options.promptFile,
            mode: options.mode,
            model: options.model,
            maxIterations: options.maxIterations,
            completionMarker: marker,
            startTime: Date.now(),
            currentIteration: 0,
            state: 'running',
            branchName: null,
        };

        // Create session branch if configured
        if (config.createBranchEverySession) {
            this.session.branchName = await gitManager.createSessionBranch(sessionId);
        }

        // Open task file in editor to anchor workspace context
        await fileManager.openFileInEditor(options.taskFile);

        this._abortController = new AbortController();
        this.setState('running');

        logger.info(`🚀 Starting Ralph Loop session ${sessionId}`);
        logger.info(`  Task file: ${options.taskFile}`);
        logger.info(`  Progress file: ${options.progressFile}`);
        logger.info(`  Mode: ${options.mode} | Model: ${options.model}`);
        logger.info(`  Max iterations: ${options.maxIterations}`);
        logger.info(`  Completion marker: ${marker}`);
        logger.show();

        // Run the loop
        await this.runLoop();
    }

    /**
     * Graceful stop — finish current iteration then halt.
     */
    stopLoop(): void {
        if (!this.session || this.session.state === 'idle') { return; }
        logger.info('🛑 Stop requested — will halt after current iteration');
        this.setState('stopped');
    }

    /**
     * Toggle pause/resume.
     */
    togglePause(): void {
        if (!this.session) { return; }

        if (this.session.state === 'paused') {
            logger.info('▶️ Resuming loop');
            this.setState('running');
        } else if (this.session.state === 'running') {
            logger.info('⏸️ Pausing loop');
            this.setState('paused');
        }
    }

    /**
     * Emergency stop — immediate termination.
     */
    emergencyStop(): void {
        if (!this.session) { return; }
        logger.warn('🔴 EMERGENCY STOP — terminating immediately');
        this._abortController?.abort();
        this.setState('idle');
        this.endSession('Emergency stop');
    }

    /**
     * The main loop body.
     */
    private async runLoop(): Promise<void> {
        if (!this.session) { return; }

        let lastBackpressureFailures: BackpressureResult[] = [];

        for (let i = 1; i <= this.session.maxIterations; i++) {
            // Check for abort
            if (this._abortController?.signal.aborted) {
                break;
            }

            // Wait while paused
            while (this.session.state === 'paused') {
                await this.sleep(1000);
                if (this._abortController?.signal.aborted) { break; }
            }

            // Check for stop
            if (this.session.state === 'stopped' || this._abortController?.signal.aborted) {
                break;
            }

            // Check completion marker before each iteration
            if (i > 1) {
                const completed = await completionDetector.checkCompletion(
                    this.session.progressFile,
                    this.session.completionMarker
                );
                if (completed) {
                    logger.info('🎉 All tasks completed! Loop ending automatically.');
                    this.endSession('All tasks completed');
                    return;
                }
            }

            // Run iteration
            this.session.currentIteration = i;
            const result = await this.runIteration(i, lastBackpressureFailures);
            this._onIterationEnd.fire(result);

            // Track backpressure failures for next iteration
            lastBackpressureFailures = result.backpressureResults.filter(r => !r.passed);

            if (!result.success && result.error) {
                logger.error(`Iteration ${i} failed: ${result.error}`);
                if (config.notificationsEnabled && config.notifyOnError) {
                    vscode.window.showErrorMessage(`Ralph Loop error on iteration ${i}: ${result.error}`);
                }
            }
        }

        // Loop finished
        if (this.session.state !== 'idle') {
            const reason = this.session.state === 'stopped'
                ? 'Stopped by user'
                : `Reached max iterations (${this.session.maxIterations})`;
            this.endSession(reason);
        }
    }

    /**
     * Execute a single iteration.
     */
    private async runIteration(iteration: number, prevFailures: BackpressureResult[]): Promise<IterationResult> {
        if (!this.session) {
            return { iteration, success: false, durationMs: 0, completionDetected: false, backpressureResults: [], error: 'No session' };
        }

        const startTime = Date.now();
        logger.iterationBoundary(iteration, this.session.maxIterations);

        try {
            // 1. Read files
            const taskContent = await fileManager.readTaskFile(this.session.taskFile);
            if (!taskContent) {
                return { iteration, success: false, durationMs: Date.now() - startTime, completionDetected: false, backpressureResults: [], error: 'Could not read task file' };
            }

            const progressContent = await fileManager.readProgressFile(this.session.progressFile);
            const promptContent = this.session.promptFile
                ? await fileManager.readPromptFile(this.session.promptFile)
                : null;

            // 2. Compose the prompt
            const prompt = this.composePrompt(taskContent, progressContent, promptContent, prevFailures);

            // 3. Send to Antigravity
            logger.info(`Sending iteration ${iteration} prompt to Antigravity...`);
            const sent = await antigravityClient.sendMessage(prompt, this.session.mode, this.session.model);
            if (!sent) {
                return { iteration, success: false, durationMs: Date.now() - startTime, completionDetected: false, backpressureResults: [], error: 'Failed to send message to Antigravity' };
            }

            // 4. Wait for completion
            logger.info('Waiting for agent to complete...');
            await antigravityClient.waitForCompletion();

            // 5. Run backpressure checks
            const bpResults = await backpressure.runChecks();

            // 6. Auto-commit
            await gitManager.commitIteration(iteration);

            // 7. Check completion marker
            const completed = await completionDetector.checkCompletion(
                this.session.progressFile,
                this.session.completionMarker
            );

            const durationMs = Date.now() - startTime;
            logger.info(`Iteration ${iteration} complete (${(durationMs / 1000).toFixed(1)}s)`);

            return {
                iteration,
                success: true,
                durationMs,
                completionDetected: completed,
                backpressureResults: bpResults,
            };
        } catch (err) {
            return {
                iteration,
                success: false,
                durationMs: Date.now() - startTime,
                completionDetected: false,
                backpressureResults: [],
                error: (err as Error).message,
            };
        }
    }

    /**
     * Compose the structured prompt sent to the agent each iteration.
     */
    private composePrompt(
        taskContent: string,
        progressContent: string,
        promptContent: string | null,
        prevFailures: BackpressureResult[]
    ): string {
        const marker = this.session?.completionMarker ?? 'ralph-done';

        let prompt = `You are an autonomous AI coding agent executing tasks iteratively.

## Instructions
1. Read the TASK FILE below to understand all pending tasks
2. Read the PROGRESS FILE below to see what has already been completed
3. Complete exactly ONE task that has not been completed yet
4. After completing the task, APPEND your progress to the progress file (file: "${this.session?.progressFile}"). Format: \`[timestamp] Completed: <task description>\`. NEVER delete or modify existing progress entries.
5. If ALL tasks are complete, append the completion marker \`${marker}\` to the progress file on its own line.
6. Commit your changes to version control.

## TASK FILE
\`\`\`
${taskContent}
\`\`\`

## PROGRESS FILE
\`\`\`
${progressContent || '(empty — no tasks completed yet)'}
\`\`\``;

        if (promptContent) {
            prompt += `\n\n## CUSTOM INSTRUCTIONS\n\`\`\`\n${promptContent}\n\`\`\``;
        }

        // Inject backpressure failures from previous iteration
        const failureReport = backpressure.formatFailures(prevFailures);
        if (failureReport) {
            prompt += `\n\n${failureReport}`;
        }

        return prompt;
    }

    private setState(state: LoopState): void {
        if (this.session) {
            this.session.state = state;
        }
        this._onStateChange.fire(state);
        vscode.commands.executeCommand('setContext', 'ralph.isRunning', state === 'running' || state === 'paused');
    }

    private endSession(reason: string): void {
        if (!this.session) { return; }

        const elapsed = Date.now() - this.session.startTime;
        const minutes = Math.floor(elapsed / 60000);
        const seconds = Math.floor((elapsed % 60000) / 1000);

        logger.info('');
        logger.info(`${'═'.repeat(60)}`);
        logger.info(`  SESSION COMPLETE`);
        logger.info(`  Reason: ${reason}`);
        logger.info(`  Iterations: ${this.session.currentIteration}`);
        logger.info(`  Duration: ${minutes}m ${seconds}s`);
        logger.info(`${'═'.repeat(60)}`);

        if (config.notificationsEnabled && config.notifyOnCompletion) {
            const stats = config.includeStats
                ? ` (${this.session.currentIteration} iterations, ${minutes}m ${seconds}s)`
                : '';
            vscode.window.showInformationMessage(`Ralph Loop finished: ${reason}${stats}`);
        }

        const session = this.session;
        this.session = { ...this.session, state: 'idle' };
        this.setState('idle');
        this._onSessionEnd.fire(session);
    }

    private sleep(ms: number): Promise<void> {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    dispose(): void {
        this._abortController?.abort();
        this._onStateChange.dispose();
        this._onIterationEnd.dispose();
        this._onSessionEnd.dispose();
    }
}

export const loopEngine = new LoopEngine();
