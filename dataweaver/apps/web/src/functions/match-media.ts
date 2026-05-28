import { BREAKPOINTS, type Target } from '~/styles/breakpoints';

/** List of media query keys with their custom query. */
const MISC_QUERIES = {
	coarse: '(hover: none) and (pointer: coarse)',
	fine: '(hover: hover) and (pointer: fine)',
	'prefers-motion': '(prefers-reduced-motion: no-preference)',
	'prefers-reduced-motion': '(prefers-reduced-motion: reduce)',
};

export type MatchMediaKey = Target | keyof typeof MISC_QUERIES | (string & {});

/**
 * Helper function to get CSS media query for given shorthand `key`.
 *
 * @param key - The shorthand key to match for.
 *
 * @example
 * getMatchMediaQuery('coarse') -> Checks if the browser matches coarse; device
 * of limited accuracy (touch).
 *
 * @example
 * getMatchMediaQuery('fine') -> Checks if the browser matches fine; accurate
 * pointing device (mouse).
 *
 * @example
 * getMatchMediaQuery('prefers-motion') -> Checks if the browser has
 * `no-preference` for 'prefers-reduced-motion'.
 *
 * @example
 * getMatchMediaQuery('tablet') -> Checks if the browser is at or above our
 * tablet `min-width` breakpoint.
 *
 * @example
 * getMatchMediaQuery('laptop') -> Checks if the browser is at or above our
 * laptop `min-width` breakpoint.
 */
export const getMatchMediaQuery = (key: MatchMediaKey) => {
	// If the key is mobile, return 'max-width' query instead. Note: We use the
	// tablet breakpoint as the 'max-width' for mobile, as we don't have a mobile
	// breakpoint + the negative 1 ensures 'max-width' fires at same point as
	// 'min-width' breakpoint
	if (key === 'mobile') {
		const tabletMinWidth = BREAKPOINTS.tablet.minWidth;
		return `(max-width: ${tabletMinWidth - 1}px)`;
	}

	// If the key is a valid breakpoint, return the min-width query
	if (key in BREAKPOINTS) {
		const minWidth = BREAKPOINTS[key as Target]?.minWidth;
		if (minWidth) return `(min-width: ${minWidth}px)`;
	}

	// If key in misc queries - return the corresponding query
	if (key in MISC_QUERIES) {
		return MISC_QUERIES[key as keyof typeof MISC_QUERIES];
	}

	return key;
};

/**
 * Helper function to get CSS media query result for given shorthand `key`.
 *
 * @param key - The shorthand key to match for (see `getMatchMediaQuery`).
 */
export const getMatchMediaMatch = (key: MatchMediaKey) => {
	const query = getMatchMediaQuery(key);
	return window.matchMedia(query).matches;
};
