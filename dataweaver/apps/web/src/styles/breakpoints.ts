import {
	BREAKPOINT_DESKTOP,
	BREAKPOINT_LAPTOP,
	BREAKPOINT_TABLET,
} from './tokens/generated';

export type Target = 'mobile' | 'tablet' | 'laptop' | 'desktop';

type Breakpoint = {
	minWidth: number;
};

type Breakpoints = {
	[key in Target]: key extends 'mobile' ? undefined : Breakpoint;
};

export const BREAKPOINTS: Breakpoints = {
	mobile: undefined,
	tablet: { minWidth: BREAKPOINT_TABLET },
	laptop: { minWidth: BREAKPOINT_LAPTOP },
	desktop: { minWidth: BREAKPOINT_DESKTOP },
} as const;
