import * as http from 'http';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import { AntigravityConnection } from './types';
import { config } from './config';
import { logger } from './logger';

/**
 * HTTP client for communicating with Antigravity's local server.
 *
 * Antigravity (Windsurf/Codeium-based IDE) runs a local HTTP server that
 * accepts chat messages via its Cascade API. This client handles:
 * - Port auto-discovery (scanning ~/.codeium/ for port files)
 * - CSRF and OAuth token management
 * - Sending structured prompts to the AI agent
 * - Waiting for agent response completion
 */
export class AntigravityClient {
    private connection: AntigravityConnection | null = null;

    /**
     * Initialize the connection to Antigravity.
     * Discovers the port and extracts/validates tokens.
     */
    async connect(): Promise<boolean> {
        const port = await this.discoverPort();
        if (!port) {
            logger.error('Could not discover Antigravity server port. Set ralphLoop.antigravity.port manually.');
            return false;
        }

        const csrfToken = config.csrfToken;
        const oauthToken = config.oauthToken || await this.tryExtractOAuthToken();

        if (!csrfToken) {
            logger.warn('No CSRF token configured. Set ralphLoop.antigravity.csrfToken from DevTools Network tab.');
        }

        this.connection = { port, csrfToken, oauthToken };
        logger.info(`Connected to Antigravity on port ${port}`);
        return true;
    }

    /**
     * Send a chat message to Antigravity's Cascade agent.
     * This triggers a new agent turn with the given prompt.
     */
    async sendMessage(message: string, mode: string, model: string): Promise<boolean> {
        if (!this.connection) {
            logger.error('Not connected to Antigravity');
            return false;
        }

        const payload = JSON.stringify({
            message,
            mode,
            model,
            // These fields may vary by Antigravity version — update as API evolves
            includeFiles: true,
            codebase: true,
        });

        try {
            const response = await this.post('/api/chat/message', payload);
            logger.debug(`Sent message to Antigravity (${payload.length} chars), response status: ${response.statusCode}`);
            return response.statusCode === 200;
        } catch (err) {
            logger.error('Failed to send message to Antigravity', err as Error);
            return false;
        }
    }

    /**
     * Wait for the agent to finish its current turn.
     * Polls the status endpoint until the agent is idle.
     */
    async waitForCompletion(timeoutMs: number = 300_000): Promise<boolean> {
        if (!this.connection) { return false; }

        const startTime = Date.now();
        const pollInterval = 3000;

        while (Date.now() - startTime < timeoutMs) {
            try {
                const response = await this.get('/api/chat/status');
                if (response.body) {
                    const status = JSON.parse(response.body);
                    if (status.state === 'idle' || status.state === 'complete') {
                        logger.debug('Agent completed its turn');
                        return true;
                    }
                }
            } catch {
                // Status endpoint might not be available — fall back to timeout
                logger.debug('Status check failed, will retry...');
            }

            await this.sleep(pollInterval);
        }

        logger.warn(`Agent completion timeout after ${timeoutMs}ms`);
        return false;
    }

    /**
     * Auto-discover Antigravity's local server port.
     * Checks configured port, then scans known file locations.
     */
    private async discoverPort(): Promise<number | null> {
        // 1. Check explicit configuration
        const configPort = config.antigravityPort;
        if (configPort > 0) {
            logger.info(`Using configured port: ${configPort}`);
            return configPort;
        }

        // 2. Scan known Codeium/Antigravity port file locations
        const portFilePaths = [
            path.join(os.homedir(), '.codeium', 'port'),
            path.join(os.homedir(), '.windsurf', 'port'),
            path.join(os.homedir(), '.antigravity', 'port'),
        ];

        for (const portFile of portFilePaths) {
            try {
                const content = await fs.promises.readFile(portFile, 'utf-8');
                const port = parseInt(content.trim(), 10);
                if (port > 0 && port < 65536) {
                    logger.info(`Discovered port ${port} from ${portFile}`);
                    return port;
                }
            } catch {
                // File doesn't exist — try next location
            }
        }

        // 3. Try common ports
        const commonPorts = [42069, 42070, 42071, 42072, 12345];
        for (const port of commonPorts) {
            if (await this.isPortResponding(port)) {
                logger.info(`Found Antigravity responding on port ${port}`);
                return port;
            }
        }

        return null;
    }

    /**
     * Check if a port is responding to HTTP requests.
     */
    private isPortResponding(port: number): Promise<boolean> {
        return new Promise((resolve) => {
            const req = http.request({ host: '127.0.0.1', port, path: '/', method: 'HEAD', timeout: 1000 }, (res) => {
                resolve(res.statusCode !== undefined);
            });
            req.on('error', () => resolve(false));
            req.on('timeout', () => { req.destroy(); resolve(false); });
            req.end();
        });
    }

    /**
     * Try to extract the OAuth token from known credential storage locations.
     */
    private async tryExtractOAuthToken(): Promise<string> {
        const credPaths = [
            path.join(os.homedir(), '.codeium', 'credentials.json'),
            path.join(os.homedir(), '.windsurf', 'credentials.json'),
            path.join(os.homedir(), '.antigravity', 'credentials.json'),
        ];

        for (const credPath of credPaths) {
            try {
                const content = await fs.promises.readFile(credPath, 'utf-8');
                const creds = JSON.parse(content);
                if (creds.api_key || creds.oauth_token || creds.token) {
                    const token = creds.api_key || creds.oauth_token || creds.token;
                    logger.info(`Extracted OAuth token from ${credPath}`);
                    return token;
                }
            } catch {
                // File doesn't exist or invalid JSON
            }
        }

        logger.debug('No OAuth token found in known locations');
        return '';
    }

    /**
     * Make an HTTP POST request to the Antigravity server.
     */
    private post(urlPath: string, body: string): Promise<{ statusCode: number; body: string }> {
        return new Promise((resolve, reject) => {
            if (!this.connection) {
                reject(new Error('Not connected'));
                return;
            }

            const options: http.RequestOptions = {
                host: '127.0.0.1',
                port: this.connection.port,
                path: urlPath,
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Content-Length': Buffer.byteLength(body),
                    ...(this.connection.csrfToken ? { 'x-codeium-csrf-token': this.connection.csrfToken } : {}),
                    ...(this.connection.oauthToken ? { 'Authorization': `Bearer ${this.connection.oauthToken}` } : {}),
                },
                timeout: 30_000,
            };

            const req = http.request(options, (res) => {
                let responseBody = '';
                res.on('data', (chunk) => { responseBody += chunk; });
                res.on('end', () => {
                    resolve({ statusCode: res.statusCode || 0, body: responseBody });
                });
            });

            req.on('error', reject);
            req.on('timeout', () => { req.destroy(); reject(new Error('Request timeout')); });
            req.write(body);
            req.end();
        });
    }

    /**
     * Make an HTTP GET request to the Antigravity server.
     */
    private get(urlPath: string): Promise<{ statusCode: number; body: string }> {
        return new Promise((resolve, reject) => {
            if (!this.connection) {
                reject(new Error('Not connected'));
                return;
            }

            const options: http.RequestOptions = {
                host: '127.0.0.1',
                port: this.connection.port,
                path: urlPath,
                method: 'GET',
                headers: {
                    ...(this.connection.csrfToken ? { 'x-codeium-csrf-token': this.connection.csrfToken } : {}),
                    ...(this.connection.oauthToken ? { 'Authorization': `Bearer ${this.connection.oauthToken}` } : {}),
                },
                timeout: 10_000,
            };

            const req = http.request(options, (res) => {
                let body = '';
                res.on('data', (chunk) => { body += chunk; });
                res.on('end', () => {
                    resolve({ statusCode: res.statusCode || 0, body });
                });
            });

            req.on('error', reject);
            req.on('timeout', () => { req.destroy(); reject(new Error('Request timeout')); });
            req.end();
        });
    }

    private sleep(ms: number): Promise<void> {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}

export const antigravityClient = new AntigravityClient();
