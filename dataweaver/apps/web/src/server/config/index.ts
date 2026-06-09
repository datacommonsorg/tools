import fs from 'node:fs';
import path from 'node:path';
import matter from 'gray-matter';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/**
 * External service configuration loaded from `default_services.json`.
 *
 * Defines API endpoints, model identifiers, and SDK settings consumed by
 * server-side clients. Values in the JSON file act as defaults; each field can
 * be overridden at runtime by the corresponding environment variable (see
 * `getServiceConfig` for the mapping).
 */
export interface ServiceConfig {
  /** API endpoint configuration for external data services. */
  api: {
    /** Data Commons API settings. */
    dataCommons: {
      /** Base URL for REST requests. Override: `DC_API_BASE`. */
      baseUrl: string;
      /** MCP (Model Context Protocol) endpoint URL. Override: `DC_MCP_ENDPOINT`. */
      mcpEndpoint: string;
    };
  };
  /** Gemini model identifiers used for each pipeline stage. */
  models: {
    /** Model for parsing raw user queries. Override: `MODEL_PARSE_QUERY`. */
    parseQuery: string;
    /** Model for discovering relevant data variables. Override: `MODEL_DATA_DISCOVERY`. */
    dataDiscovery: string;
    /** Model for content-safety classification. Override: `MODEL_SAFETY`. */
    safety: string;
    /** Model for image generation. Override: `MODEL_IMAGE`. */
    image: string;
  };
  /** Gemini SDK configuration. */
  gemini: {
    /** API version string (e.g. `"v1alpha"`). Override: `GEMINI_API_VERSION`. */
    apiVersion: string;
  };
}

/**
 * Configuration for a single skill, parsed from a Markdown file with YAML
 * frontmatter (located in `config/skills/{name}.md`).
 *
 * The Markdown body becomes the `systemPrompt`; optional YAML fields supply
 * execution constraints.
 */
export interface SkillConfig {
  /** The prompt body (markdown content without frontmatter). */
  systemPrompt: string;
  /** Maximum number of tool-call rounds the model may perform for this skill. */
  maxToolCalls?: number;
  /** Regex patterns used to match user queries to this skill. */
  regexPatterns?: string[];
}

// ---------------------------------------------------------------------------
// Loaders
// ---------------------------------------------------------------------------

const CONFIG_DIR = path.join(process.cwd(), 'src/server/config');

let _services: ServiceConfig | null = null;

/**
 * Load service config with environment variable overrides.
 * Env vars take precedence over JSON defaults.
 */
export const getServiceConfig = (): ServiceConfig => {
  if (_services) return _services;

  const raw = JSON.parse(
    fs.readFileSync(path.join(CONFIG_DIR, 'default_services.json'), 'utf-8'),
  );

  _services = {
    api: {
      dataCommons: {
        baseUrl: process.env.DC_API_BASE || raw.api.dataCommons.baseUrl,
        mcpEndpoint:
          process.env.DC_MCP_ENDPOINT || raw.api.dataCommons.mcpEndpoint,
      },
    },
    models: {
      parseQuery: process.env.MODEL_PARSE_QUERY || raw.models.parseQuery,
      dataDiscovery:
        process.env.MODEL_DATA_DISCOVERY || raw.models.dataDiscovery,
      safety: process.env.MODEL_SAFETY || raw.models.safety,
      image: process.env.MODEL_IMAGE || raw.models.image,
    },
    gemini: {
      apiVersion: process.env.GEMINI_API_VERSION || raw.gemini.apiVersion,
    },
  };

  return _services;
};

const _skillCache = new Map<string, SkillConfig>();

/**
 * Load a skill config by name (maps to config/skills/{name}.md).
 * Markdown body becomes `systemPrompt`; YAML frontmatter supplies other fields.
 * Skill files are cached after first load.
 */
export const getSkillConfig = (name: string): SkillConfig => {
  const cached = _skillCache.get(name);
  if (cached) return cached;

  // Co-located skill: server/{name}/skill.md — falls back to config/skills/{name}.md
  const filePath = path.join(CONFIG_DIR, 'skills', `${name}.md`);
  const raw = fs.readFileSync(filePath, 'utf-8');
  const { data, content } = matter(raw);

  const skill: SkillConfig = {
    systemPrompt: content.trim(),
    ...(data.maxToolCalls != null && { maxToolCalls: data.maxToolCalls }),
    ...(data.regexPatterns != null && { regexPatterns: data.regexPatterns }),
  };

  _skillCache.set(name, skill);
  return skill;
};

/**
 * Reset caches (useful for testing or hot-reload scenarios).
 */
export const resetConfigCache = (): void => {
  _services = null;
  _skillCache.clear();
};
