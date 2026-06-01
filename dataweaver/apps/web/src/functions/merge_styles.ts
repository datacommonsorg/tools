import type { CSSProperties } from "react";

/**
 * Helper to merge multiple style objects into one, filtering out any invalid
 * values to avoid overwriting existing styles when none is provided.
 *
 * @example
 * const mergedStyles = mergeStyles(
 *   { color: 'red', aspectRatio: '16 / 9' },
 *   { color: 'blue', aspectRatio: undefined },
 * );
 *
 * // Result: { color: 'blue', aspectRatio: '16 / 9' }
 */
export const mergeStyles = (...styles: Array<CSSProperties | undefined>) => {
	const merged: CSSProperties = {};

	for (const style of styles) {
		// Ignore if style isn't set
		if (!style) continue;

		// Iterate over each style property and only assign it if it's defined
		for (const [key, value] of Object.entries(style)) {
			if (value !== undefined) merged[key as keyof CSSProperties] = value;
		}
	}

	return merged;
};
