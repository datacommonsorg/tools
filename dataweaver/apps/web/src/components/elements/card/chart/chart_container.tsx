'use client';

import { type ReactElement, useEffect, useRef, useState } from 'react';
import s from './chart_container.module.scss';

interface ChartContainerProps {
  aspect: number;
  children: (width: number, height: number) => ReactElement;
}

/**
 * A replacement for Recharts' ResponsiveContainer that avoids the
 * "width(-1) and height(-1)" warning by deferring render until the
 * container has been measured with valid dimensions.
 */
export const ChartContainer = ({ aspect, children }: ChartContainerProps) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<{ width: number; height: number } | null>(
    null,
  );

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const width = entry.contentRect.width;
      if (width > 0) {
        setSize((prev) =>
          prev?.width === width ? prev : { width, height: width / aspect },
        );
      }
    });

    observer.observe(el);
    return () => observer.disconnect();
  }, [aspect]);

  return (
    <div ref={containerRef} className={s['chart-container']}>
      {size && children(size.width, size.height)}
    </div>
  );
};
