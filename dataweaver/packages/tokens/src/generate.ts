/**
 * Generates the design tokens into this package's `dist/` directory so they can
 * be consumed by any application that depends on `@package/tokens`:
 *
 * - `tokens.css`  CSS custom properties for colors (themable at runtime).
 * - `_tokens.scss` Build-time SCSS values (breakpoints) for `@media` queries.
 * - `tokens.ts`   TypeScript exports (breakpoints, eases, colors).
 *
 * Usage: tsx src/generate.ts
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

import COLORS from './colors.json' with { type: 'json' };
import EASES from './eases.json' with { type: 'json' };
import VARIABLES from './variables.json' with { type: 'json' };

const DIST_DIRECTORY = resolve(import.meta.dirname, '../dist');

const DO_NOT_EDIT_COMMENT_BANNER =
  "AUTO-GENERATED — Do not edit. Modify the JSON tokens in 'packages/tokens/src/' and run 'pnpm generate:tokens'";

/**
 * A color is either an RGB (triplet or with a 4th alpha element) or an alias
 * '$other-token'. Aliases let component-scoped tokens (e.g. 'card-surface')
 * point at a single generic role (e.g. '$surface-raised') so there's one source
 * of truth per value.
 */
type ColorValue = number[] | string;

const COLOR_MAP: Record<string, ColorValue> = COLORS;

const isAlias = (value: ColorValue): value is string => {
  return typeof value === 'string';
};

/** The const name for a token, e.g. 'card-surface' → 'COLOR_CARD_SURFACE'. */
const colorConst = (name: string): string => {
  return `COLOR_${name.replaceAll('-', '_').toUpperCase()}`;
};

/** Follows an alias chain to its source (non-alias) token name. */
const resolveName = (name: string): string => {
  const value = COLOR_MAP[name];
  if (value === undefined) {
    throw new Error(`Unknown color token referenced: '${name}'`);
  }

  return isAlias(value) ? resolveName(value.slice(1)) : name;
};

/**
 * Channels are space-separated for the modern 'rgb(r g b / a)' syntax; a 4th
 * element is the alpha, emitted after a slash so 'rgb(var(--color-x))' alone
 * already carries the opacity.
 */
const toCssChannels = (channels: number[]): string => {
  if (channels.length > 3) {
    const [red, green, blue, alpha] = channels;
    if (alpha === undefined) {
      throw new Error(
        `Color token doesn't have valid alpha channel for '${channels}'.`,
      );
    }

    const alphaString = alpha.toString();
    const formattedAlpha = alphaString.startsWith('.')
      ? `0${alphaString}`
      : alphaString;

    return `${red} ${green} ${blue} / ${formattedAlpha}`;
  }

  return channels.join(' ');
};

// Build-time SCSS values ($-variables). These emit no CSS, so the partial is
// safe to '@use' / auto-inject into every Sass module.
const generateScss = (): string => {
  const lines: string[] = [`// ⚠️ ${DO_NOT_EDIT_COMMENT_BANNER}`, ''];

  // Breakpoints are build-time values (CSS variables can't be used in '@media'
  // conditions), so they are emitted as SCSS rather than CSS custom properties
  lines.push('// Variables');
  for (const [name, value] of Object.entries(VARIABLES)) {
    const formattedValue = name.startsWith('gutter-') ? `${value}px` : value;
    lines.push(`$${name}: ${formattedValue};`);
  }

  // Eases as ready-to-use 'cubic-bezier()' timing functions
  lines.push('', '// Eases');
  for (const [name, values] of Object.entries(EASES)) {
    lines.push(`$ease-${name}: cubic-bezier(${values.join(', ')});`);
  }

  lines.push('');
  return lines.join('\n');
};

const generateTypeScript = (): string => {
  const lines: string[] = [`// ⚠️ ${DO_NOT_EDIT_COMMENT_BANNER}`, ''];

  // Variables
  for (const [name, value] of Object.entries(VARIABLES)) {
    const constName = name.replaceAll('-', '_').toUpperCase();
    lines.push(`export const ${constName} = ${value};`);
  }

  // Each distinct source value is declared once as a const; aliases then
  // reference it, so a shared color (e.g. accent) lives in a single place
  lines.push('');
  for (const [name, value] of Object.entries(COLOR_MAP)) {
    if (!isAlias(value)) {
      lines.push(`const ${colorConst(name)} = '${toCssChannels(value)}';`);
    }
  }

  // Colors — each token references the const of its resolved source value.
  lines.push('');
  lines.push('export const COLORS = {');
  for (const name of Object.keys(COLOR_MAP)) {
    const key = name.includes('-') ? `'${name}'` : name;
    lines.push(`  ${key}: ${colorConst(resolveName(name))},`);
  }
  lines.push('} as const;');

  // Eases: Typed as a cubic-bezier tuple so the package stays free of any
  // animation-library dependency; it is structurally compatible with consumers
  // such as motion's 'BezierDefinition'
  lines.push('');
  lines.push('export type Easing = [number, number, number, number];');
  lines.push('');
  for (const [name, values] of Object.entries(EASES)) {
    const constName = `EASE_${name.toUpperCase().replaceAll('-', '_')}`;
    lines.push(`export const ${constName}: Easing = [${values.join(', ')}];`);
  }

  lines.push('');
  return lines.join('\n');
};

// Runtime, themeable colors as ':root' custom properties. Kept in a standalone
// 'colors.css' (rather than the SCSS partial) so the file's purpose is clear
// and partners can override the semantic theme at runtime.
const generateColorsCss = (): string => {
  const lines: string[] = [
    `/* ⚠️ ${DO_NOT_EDIT_COMMENT_BANNER} */`,
    '',
    ':root {',
  ];

  for (const [name, value] of Object.entries(COLOR_MAP)) {
    // Aliases reference the canonical token via 'var()' so a single edit to a
    // generic role cascades to every component token pointing at it
    const channels = isAlias(value)
      ? `var(--color-${value.slice(1)})`
      : toCssChannels(value);
    lines.push(`  --color-${name}: ${channels};`);
  }

  lines.push('}', '');
  return lines.join('\n');
};

console.info('🟦 Starting token generation...');

mkdirSync(DIST_DIRECTORY, { recursive: true });
writeFileSync(resolve(DIST_DIRECTORY, '_tokens.scss'), generateScss());
writeFileSync(resolve(DIST_DIRECTORY, 'tokens.ts'), generateTypeScript());
writeFileSync(resolve(DIST_DIRECTORY, 'colors.css'), generateColorsCss());

console.info('✅ Generated _tokens.scss, tokens.ts and colors.css!\n');
