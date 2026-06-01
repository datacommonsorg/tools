import { domMax, LazyMotion } from 'motion/react';
import type { ReactNode } from 'react';

interface MotionProviderProps {
  children: ReactNode;
}

/**
 * Lazily loads motion's DOM features behind `m.*` (strict mode disallows the
 * heavier `motion.*` API). Mounted once at the root.
 */
export const MotionProvider = ({ children }: MotionProviderProps) => {
  return (
    <LazyMotion strict features={domMax}>
      {children}
    </LazyMotion>
  );
};
