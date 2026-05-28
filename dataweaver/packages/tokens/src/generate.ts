/**
 * Generates _generated.module.scss and generated.ts from JSON token files.
 *
 * Usage: tsx src/generate.ts <output-directory>
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

import COLORS from './colors.json' with { type: 'json' };
import EASES from './eases.json' with { type: 'json' };
import VARIABLES from './variables.json' with { type: 'json' };

const [OUTPUT_DIRECTORY] = process.argv
	.slice(2)
	.filter((argument) => argument !== '--');

if (!OUTPUT_DIRECTORY) {
	console.error(
		'❌ Output directory argument is required. Usage: tsx src/generate.ts <output-directory>',
	);
	process.exit(1);
}

const RESOLVED_OUTPUT_DIRECTORY = resolve(process.cwd(), OUTPUT_DIRECTORY);

const DO_NOT_EDIT_COMMENT_BANNER =
	"// ⚠️ AUTO-GENERATED — Do not edit. Modify the JSON tokens in 'packages/tokens/src/' and run 'pnpm generate:tokens'";

const generateScss = (): string => {
	const lines: string[] = [DO_NOT_EDIT_COMMENT_BANNER];

	// Variables
	lines.push('');
	lines.push('// Variables');
	for (const [name, value] of Object.entries(VARIABLES)) {
		const formattedValue = name.startsWith('gutter-') ? `${value}px` : value;
		lines.push(`$${name}: ${formattedValue};`);
	}

	// Colors
	lines.push('');
	lines.push('// Colors');
	for (const [name, values] of Object.entries(COLORS)) {
		const formattedValue = values.join(' ');
		lines.push(`$color-${name}: rgb(${formattedValue});`);
	}

	// Eases
	lines.push('');
	lines.push('// Eases');
	for (const [name, values] of Object.entries(EASES)) {
		const formattedValue = values.join(', ');
		lines.push(`$ease-${name}: cubic-bezier(${formattedValue});`);
	}

	lines.push('');
	return lines.join('\n');
};

const generateTypeScript = (): string => {
	const lines: string[] = [
		DO_NOT_EDIT_COMMENT_BANNER,
		'',
		'import type { BezierDefinition } from "motion/react";',
	];

	// Variables
	lines.push('');
	for (const [name, value] of Object.entries(VARIABLES)) {
		const constName = name.replaceAll('-', '_').toUpperCase();
		lines.push(`export const ${constName} = ${value};`);
	}

	// Colors
	lines.push('');
	lines.push('export const COLORS = {');
	for (const [name, values] of Object.entries(COLORS)) {
		const constName = name.includes('-') ? `"${name}"` : name;
		const formattedValue = values.join(', ');
		lines.push(`\t${constName}: "${formattedValue}",`);
	}
	lines.push('} as const;');

	// Eases
	lines.push('');
	for (const [name, values] of Object.entries(EASES)) {
		const constName = `EASE_${name.toUpperCase().replaceAll('-', '_')}`;
		const formattedValue = values.join(', ');
		lines.push(
			`export const ${constName}: BezierDefinition = [${formattedValue}];`,
		);
	}

	lines.push('');
	return lines.join('\n');
};

console.info(`🟦 Starting token generations...`);

mkdirSync(RESOLVED_OUTPUT_DIRECTORY, { recursive: true });
writeFileSync(
	resolve(RESOLVED_OUTPUT_DIRECTORY, '_generated.module.scss'),
	generateScss(),
);
writeFileSync(
	resolve(RESOLVED_OUTPUT_DIRECTORY, 'generated.ts'),
	generateTypeScript(),
);

console.info('✅ Generated _generated.module.scss and generated.ts! \n');
