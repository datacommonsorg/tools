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

  // Colors
  lines.push('');
  lines.push('export const COLORS = {');
  for (const [name, values] of Object.entries(COLORS)) {
    const constName = name.includes('-') ? `'${name}'` : name;
    lines.push(`  ${constName}: '${values.join(', ')}',`);
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

// Runtime, themable colors as ':root' custom properties. Kept in a standalone
// 'colors.css' (rather than the SCSS partial) so the file's purpose is clear
// and partners can override the semantic theme at runtime.
const generateColorsCss = (): string => {
  const lines: string[] = [
    `/* ⚠️ ${DO_NOT_EDIT_COMMENT_BANNER} */`,
    '',
    ':root {',
  ];

  // Exposed as space-separated channels so they can be consumed as
  // `rgb(var(--color-x))` (and rgba via `rgb(var(--color-x) / <alpha-value>)`)
  for (const [name, values] of Object.entries(COLORS)) {
    lines.push(`  --color-${name}: ${values.join(' ')};`);
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
