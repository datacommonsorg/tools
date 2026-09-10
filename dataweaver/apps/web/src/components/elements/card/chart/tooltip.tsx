import { type ReactNode, useCallback, useRef } from 'react';
import { formatChartValue } from '~/functions/format_chart_value';
import { mergeClassNames } from '~/functions/merge_class_names';
import s from './tooltip.module.scss';

export interface TooltipCoordinates {
  x: number;
  y: number;
  containerWidth?: number;
  containerHeight?: number;
}

export interface TooltipProps {
  coords?: TooltipCoordinates | null;
  className?: string;
  children?: ReactNode;
}

// Vertical safety buffer between tooltip and container top boundary before flipping below cursor.
const CLEARANCE_Y_PX = 12;
// Horizontal safety buffer between tooltip edges and container boundaries before shifting alignment.
const CLEARANCE_X_PX = 8;

/**
 * Universal tooltip scaffolding.
 * Handles surface styling, DOM measurement, and dynamic boundary positioning.
 * Completely agnostic of content.
 */
export const Tooltip = ({ coords, className, children }: TooltipProps) => {
  const measuredSizeRef = useRef({ width: 140, height: 50 });

  const measureRef = useCallback((el: HTMLDivElement | null) => {
    if (el) {
      const rect = el.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        measuredSizeRef.current = { width: rect.width, height: rect.height };
      }
    }
  }, []);

  if (!children) return null;

  let flipY = false;
  let alignLeft = false;
  let alignRight = false;

  if (coords) {
    const { width, height } = measuredSizeRef.current;
    flipY = coords.y < height + CLEARANCE_Y_PX;
    alignLeft = coords.x < width / 2 + CLEARANCE_X_PX;
    alignRight =
      coords.containerWidth !== undefined &&
      coords.x > coords.containerWidth - width / 2 - CLEARANCE_X_PX;
  }

  return (
    <div
      ref={coords ? measureRef : undefined}
      className={mergeClassNames(
        s.tooltip,
        coords && s.floating,
        coords && flipY && s['align-bottom'],
        coords && alignLeft && s['align-left'],
        coords && alignRight && s['align-right'],
        className,
      )}
      style={coords ? { left: coords.x, top: coords.y } : undefined}
    >
      {children}
    </div>
  );
};

export interface TooltipContentItem {
  name?: string;
  value: number | string | null;
  color?: string;
  unit?: string;
}

export interface TooltipContentProps {
  title?: string;
  subtitle?: string;
  items?: TooltipContentItem[];
  hint?: string;
  emptyMessage?: string;
  children?: ReactNode;
}

/**
 * Standard content layout for chart tooltips.
 * Formats title, series items with swatches, subtitle, interaction hint, and empty messages.
 */
export const TooltipContent = ({
  title,
  subtitle,
  items,
  hint,
  emptyMessage,
  children,
}: TooltipContentProps) => {
  const hasItems = items && items.length > 0;
  if (!hasItems && !title && !emptyMessage && !children) {
    return null;
  }

  return (
    <div className={s.content}>
      {title && <div className={s.title}>{title}</div>}

      {items?.map((item, index) => {
        const isValueValid =
          item.value !== null &&
          item.value !== undefined &&
          !Number.isNaN(Number(item.value));

        return (
          <div key={index} className={s.entry}>
            {item.color && (
              <span
                className={s.swatch}
                style={{ backgroundColor: item.color }}
              />
            )}
            {item.name && <span className={s.name}>{item.name}</span>}
            <span className={s.value}>
              {isValueValid
                ? typeof item.value === 'string'
                  ? item.value
                  : formatChartValue(Number(item.value), item.unit, 'standard')
                : '—'}
            </span>
          </div>
        );
      })}

      {emptyMessage && !hasItems && (
        <div className={s.empty}>{emptyMessage}</div>
      )}

      {subtitle && <p className={s.subtitle}>{subtitle}</p>}
      {hint && <div className={s.hint}>{hint}</div>}
      {children}
    </div>
  );
};
