import * as crypto from 'crypto';
import { fileManager } from './fileManager';
import { logger } from './logger';

/**
 * Generates unique completion markers and detects them in progress files.
 *
 * When a loop starts, a unique marker (e.g., `ralph-done-a3x9k`) is generated.
 * The agent is instructed to append this marker when ALL tasks are complete.
 * Before each iteration, the detector scans the progress file's tail for the marker.
 */
export class CompletionDetector {
    /**
     * Generate a unique completion marker for a session.
     * Format: `ralph-done-<5 random alphanumeric chars>`
     */
    generateMarker(): string {
        const suffix = crypto.randomBytes(4).toString('hex').slice(0, 5);
        const marker = `ralph-done-${suffix}`;
        logger.info(`Generated completion marker: ${marker}`);
        return marker;
    }

    /**
     * Check if the completion marker exists in the tail of the progress file.
     * Scans the last 30 lines to avoid false negatives from long files.
     */
    async checkCompletion(progressFile: string, marker: string): Promise<boolean> {
        const tail = await fileManager.readLastLines(progressFile, 30);
        const found = tail.includes(marker);
        if (found) {
            logger.info(`✅ Completion marker detected: ${marker}`);
        } else {
            logger.debug(`Completion marker not found in tail of ${progressFile}`);
        }
        return found;
    }
}

export const completionDetector = new CompletionDetector();
