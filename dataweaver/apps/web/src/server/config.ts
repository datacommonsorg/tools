import fs from 'node:fs';
import path from 'node:path';
import matter from 'gray-matter';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ServiceConfig {
  api: {
    dataCommons: {
      baseUrl: string;
      mcpEndpoint: string;
    };
  };
  models: {
    parseQuery: string;
    dataDiscovery: string;
    safety: string;
    image: string;
  };
  gemini: {
    apiVersion: string;
  };
}

export interface SkillConfig {
  /** The prompt body (markdown content without frontmatter). */
  systemPrompt: string;
  maxToolCalls?: number;
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
    fs.readFileSync(path.join(CONFIG_DIR, 'services.json'), 'utf-8'),
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
  const serverDir = path.join(process.cwd(), 'src/server');
  const colocatedPath = path.join(serverDir, name, 'skill.md');
  const legacyPath = path.join(CONFIG_DIR, 'skills', `${name}.md`);
  const filePath = fs.existsSync(colocatedPath) ? colocatedPath : legacyPath;
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
