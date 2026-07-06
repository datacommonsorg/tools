'use client';

import { type ReactNode, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';

interface PortalProps {
  className?: string;
  children: ReactNode;
}

/**
 * Renders its children into a fresh 'div' appended to 'document.body', escaping
 * any ancestor stacking or overflow context while staying in the React tree.
 *
 * The primitive is unopinionated: it applies no styling of its own.
 */
export const Portal = ({ className, children }: PortalProps) => {
  const [mountedElement, setMountedElement] = useState<HTMLDivElement | null>(
    null,
  );

  useEffect(() => {
    const element = document.createElement('div');
    if (className) element.className = className;
    document.body.appendChild(element);
    setMountedElement(element);
    return () => {
      element.remove();
      setMountedElement(null);
    };
  }, [className]);

  return mountedElement ? createPortal(children, mountedElement) : null;
};
