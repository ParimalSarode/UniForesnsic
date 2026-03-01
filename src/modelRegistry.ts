import * as https from 'https';
import * as http from 'http';
import { ModelEntry } from './types';
import { config } from './config';
import { logger } from './logger';

/**
 * Manages the list of available AI models.
 * Supports a bundled default list and optional remote registry fetch.
 */
export class ModelRegistry {
    private models: ModelEntry[] = [];
    private loaded = false;

    /** Bundled default models */
    private readonly defaults: ModelEntry[] = [
        { id: 'gemini-3-pro-low', displayName: 'Gemini 3 Pro (Low)', provider: 'google' },
        { id: 'gemini-3-flash', displayName: 'Gemini 3 Flash', provider: 'google' },
        { id: 'gemini-3-pro-high', displayName: 'Gemini 3 Pro (High)', provider: 'google' },
        { id: 'claude-sonnet-4.5', displayName: 'Claude Sonnet 4.5', provider: 'anthropic' },
        { id: 'claude-sonnet-4.5-thinking', displayName: 'Claude Sonnet 4.5 (Thinking)', provider: 'anthropic' },
        { id: 'claude-opus-4.5-thinking', displayName: 'Claude Opus 4.5 (Thinking)', provider: 'anthropic' },
        { id: 'gpt-oss-120b-medium', displayName: 'GPT-OSS-120B (Medium)', provider: 'openai' },
    ];

    /**
     * Load models from the registry. Tries remote URL first, falls back to bundled defaults.
     */
    async load(): Promise<ModelEntry[]> {
        const url = config.modelRegistryUrl;

        if (url) {
            try {
                logger.info(`Fetching model registry from: ${url}`);
                const data = await this.fetchJson(url);
                if (Array.isArray(data) && data.length > 0) {
                    this.models = data as ModelEntry[];
                    this.loaded = true;
                    logger.info(`Loaded ${this.models.length} models from remote registry`);
                    return this.models;
                }
            } catch (err) {
                logger.warn(`Failed to fetch remote model registry, using defaults: ${(err as Error).message}`);
            }
        }

        this.models = [...this.defaults];
        this.loaded = true;
        logger.info(`Using ${this.models.length} bundled default models`);
        return this.models;
    }

    /**
     * Get the list of available models.
     */
    getModels(): ModelEntry[] {
        if (!this.loaded) {
            this.models = [...this.defaults];
        }
        return this.models;
    }

    /**
     * Get display names for quick-pick menus.
     */
    getDisplayNames(): string[] {
        return this.getModels().map(m => m.displayName);
    }

    /**
     * Find a model by display name.
     */
    findByDisplayName(displayName: string): ModelEntry | undefined {
        return this.getModels().find(m => m.displayName === displayName);
    }

    private fetchJson(url: string): Promise<unknown> {
        return new Promise((resolve, reject) => {
            const client = url.startsWith('https') ? https : http;
            client.get(url, (res) => {
                let data = '';
                res.on('data', (chunk) => { data += chunk; });
                res.on('end', () => {
                    try {
                        resolve(JSON.parse(data));
                    } catch (err) {
                        reject(new Error(`Invalid JSON: ${(err as Error).message}`));
                    }
                });
            }).on('error', reject);
        });
    }
}

export const modelRegistry = new ModelRegistry();
