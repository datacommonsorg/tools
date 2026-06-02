import {
  BREAKPOINT_DESKTOP,
  BREAKPOINT_LAPTOP,
  BREAKPOINT_TABLET,
} from '@package/tokens/ts';

export type Target = 'mobile' | 'tablet' | 'laptop' | 'desktop';

interface Breakpoint {
  minWidth: number;
}

type Breakpoints = {
  [Key in Target]: Key extends 'mobile' ? undefined : Breakpoint;
};

export const BREAKPOINTS: Breakpoints = {
  mobile: undefined,
  tablet: { minWidth: BREAKPOINT_TABLET },
  laptop: { minWidth: BREAKPOINT_LAPTOP },
  desktop: { minWidth: BREAKPOINT_DESKTOP },
} as const;
