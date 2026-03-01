/**
 * Shared types and interfaces for Ralph Loop extension.
 */

/** Loop execution states */
export type LoopState = 'idle' | 'running' | 'paused' | 'stopped';

/** Antigravity operating modes */
export type AgentMode = 'Fast' | 'Planning';

/** Backpressure check types */
export type BackpressureType = 'test' | 'lint' | 'build' | 'package';

/** Session configuration for a loop run */
export interface LoopSession {
    id: string;
    taskFile: string;
    progressFile: string;
    promptFile: string | null;
    mode: AgentMode;
    model: string;
    maxIterations: number;
    completionMarker: string;
    startTime: number;
    currentIteration: number;
    state: LoopState;
    branchName: string | null;
}

/** Result from a single iteration */
export interface IterationResult {
    iteration: number;
    success: boolean;
    durationMs: number;
    completionDetected: boolean;
    backpressureResults: BackpressureResult[];
    error?: string;
}

/** Result from a backpressure check */
export interface BackpressureResult {
    type: BackpressureType;
    passed: boolean;
    output: string;
    exitCode: number;
}

/** Model entry from the registry */
export interface ModelEntry {
    id: string;
    displayName: string;
    provider: string;
}

/** Antigravity API connection config */
export interface AntigravityConnection {
    port: number;
    csrfToken: string;
    oauthToken: string;
}

/** Events emitted by the loop engine */
export interface LoopEvents {
    onStateChange: (state: LoopState) => void;
    onIterationStart: (iteration: number) => void;
    onIterationEnd: (result: IterationResult) => void;
    onComplete: (session: LoopSession) => void;
    onError: (error: Error) => void;
}
