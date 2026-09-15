/**
 * @fileoverview Renders a Material Design 3 tooltip (Plain or Rich) anchored to its trigger element.
 * @see https://m3.material.io/components/tooltips/overview
 */

import {
  cloneElement,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactElement,
  type ReactNode,
  type Ref,
} from "react";
import { createPortal } from "react-dom";

/**
 * Material 3 Tooltips (https://m3.material.io/components/tooltips/overview).
 *
 * Supports both M3 variants:
 * 1. Plain tooltips:
 *    - Container: Inverse surface (#313033), 4dp corner radius, 24dp min height, 4dp/8dp padding
 *    - Label: Inverse on surface (#F4EFF4), body-small / label-small (12sp/16sp), 500 weight
 *    - Offset: 4dp from the anchor
 * 2. Rich tooltips:
 *    - Container: Surface container, 12dp corner radius, elevation level 2, 12dp/16dp/8dp padding
 *    - Subhead: Title small (14sp, 500 weight)
 *    - Body: Body small/medium (12sp/14sp, 400 weight)
 *    - Actions: Label large buttons (14sp, 500 weight)
 */

/** Gap between the anchor's edge and the tooltip, in px (M3: 4dp). */
const OFFSET = 4;
/** Keep this many px clear of the viewport edge when clamping. */
const VIEWPORT_PAD = 8;

/**
 * Hover time before the tooltip appears.
 *
 * Short on purpose. The native `title` delay is roughly a second, which reads
 * as the tooltip being broken; this is long enough that tooltips don't flash
 * up while the pointer merely crosses a control.
 */
const ENTER_DELAY_MS = 150;

/**
 * How long after one tooltip hides that the next opens with no delay.
 *
 * Moving along a row of icons should feel like one continuous gesture rather
 * than paying {@link ENTER_DELAY_MS} again at every stop.
 */
const WARM_MS = 400;

/** When the last tooltip closed — drives the {@link WARM_MS} grace period. */
let lastHiddenAt = 0;

export type Placement = "top" | "bottom" | "left" | "right";

/** The part of a DOMRect the placement maths actually reads. */
export interface Box {
  top: number;
  bottom: number;
  left: number;
  right: number;
  width: number;
  height: number;
}

export interface TooltipProps {
  /** The label to show for plain tooltips, or supporting body text for rich tooltips. */
  label?: string;
  /** Optional subhead/title for M3 Rich Tooltips (m3.material.io/components/tooltips). */
  title?: string;
  /** Optional primary action label for M3 Rich Tooltips. */
  actionLabel?: string;
  /** Optional primary action callback for M3 Rich Tooltips. */
  onAction?: () => void;
  /** Optional secondary action label for M3 Rich Tooltips. */
  secondaryActionLabel?: string;
  /** Optional secondary action callback for M3 Rich Tooltips. */
  onSecondaryAction?: () => void;
  /** Optional custom rich content for M3 Rich Tooltips. */
  content?: ReactNode;
  /** Tooltip variant: "plain" (default for short labels) or "rich". Auto-inferred if title, actionLabel, or content is provided. */
  variant?: "plain" | "rich";
  /** Preferred side. Flips to the opposite side when there is no room. */
  placement?: Placement;
  /** The trigger. Must be a host element (button, a, …) so it can take a ref. */
  children: ReactElement<Record<string, unknown>>;
}

interface Coords {
  top: number;
  left: number;
}

/** Wraps a control so hovering or keyboard-focusing it shows an M3 tooltip. */
export function Tooltip({
  label,
  title,
  actionLabel,
  onAction,
  secondaryActionLabel,
  onSecondaryAction,
  content,
  variant,
  placement,
  children,
}: TooltipProps) {
  const isRich =
    variant === "rich" ||
    Boolean(title || actionLabel || secondaryActionLabel || content);
  const preferredSide: Placement = placement ?? (isRich ? "bottom" : "top");

  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState<Coords | null>(null);
  const anchorRef = useRef<HTMLElement | null>(null);
  const tooltipRef = useRef<HTMLDivElement | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const isOverTipRef = useRef(false);

  const hide = useCallback(() => {
    window.clearTimeout(timer.current);
    setOpen((wasOpen) => {
      if (wasOpen) lastHiddenAt = Date.now();
      return false;
    });
    setCoords(null);
  }, []);

  const show = useCallback(() => {
    window.clearTimeout(timer.current);
    const delay = Date.now() - lastHiddenAt < WARM_MS ? 0 : ENTER_DELAY_MS;
    timer.current = window.setTimeout(() => setOpen(true), delay);
  }, []);

  // Clear a pending open if the trigger unmounts mid-hover (e.g. the send
  // button swapping for the stop button when a turn starts streaming).
  useEffect(() => () => window.clearTimeout(timer.current), []);

  // Position after the tooltip has been laid out, so its real measured size
  // decides whether the preferred side fits. Runs before paint, so the
  // tooltip is never visible at the wrong spot.
  useLayoutEffect(() => {
    if (!open) return;
    const anchor = anchorRef.current;
    const tip = tooltipRef.current;
    if (!anchor || !tip) return;
    setCoords(
      place(
        anchor.getBoundingClientRect(),
        tip.getBoundingClientRect(),
        preferredSide,
      ),
    );
  }, [open, preferredSide, label, title, content]);

  // A tooltip pinned to viewport coordinates goes stale the moment anything
  // moves, and there is no sensible "follow" behaviour for a hover affordance
  // — so close instead. Escape closes it without moving the pointer.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") hide();
    };
    const onDocPointerDown = (e: PointerEvent) => {
      if (
        isRich &&
        tooltipRef.current &&
        tooltipRef.current.contains(e.target as Node)
      ) {
        return;
      }
      hide();
    };
    window.addEventListener("scroll", hide, true);
    window.addEventListener("resize", hide);
    window.addEventListener("keydown", onKey);
    if (isRich) {
      document.addEventListener("pointerdown", onDocPointerDown);
    }
    return () => {
      window.removeEventListener("scroll", hide, true);
      window.removeEventListener("resize", hide);
      window.removeEventListener("keydown", onKey);
      if (isRich) {
        document.removeEventListener("pointerdown", onDocPointerDown);
      }
    };
  }, [open, hide, isRich]);

  const childProps = children.props;
  const trigger = cloneElement(children, {
    ref: (node: HTMLElement | null) => {
      anchorRef.current = node;
      // Cloning replaces whatever ref the child declared, so hand the node on.
      // React 19 passes ref as an ordinary prop; the element field is the
      // pre-19 location, kept as a fallback.
      applyRef(
        (childProps.ref ?? (children as { ref?: Ref<HTMLElement> }).ref) as
          | Ref<HTMLElement>
          | undefined,
        node,
      );
    },
    onPointerEnter: (e: React.PointerEvent) => {
      callHandler(childProps.onPointerEnter, e);
      // Touch would leave the tooltip stuck open with no hover-out; the
      // control's own aria-label carries the same text for that case.
      if (e.pointerType !== "touch") show();
    },
    onPointerLeave: (e: React.PointerEvent) => {
      callHandler(childProps.onPointerLeave, e);
      if (isRich) {
        // Brief grace period allowing pointer to bridge the 4dp gap into rich tooltip
        window.clearTimeout(timer.current);
        timer.current = window.setTimeout(() => {
          if (!isOverTipRef.current) hide();
        }, 120);
      } else {
        hide();
      }
    },
    // Clicking has committed the action — the plain label is just in the way now.
    onPointerDown: (e: React.PointerEvent) => {
      callHandler(childProps.onPointerDown, e);
      if (!isRich) hide();
    },
    onFocus: (e: React.FocusEvent<HTMLElement>) => {
      callHandler(childProps.onFocus, e);
      // Only keyboard focus. Showing on click-focus duplicates a tooltip the
      // pointer already triggered, and leaves it up after the click.
      if (e.target.matches(":focus-visible")) show();
    },
    onBlur: (e: React.FocusEvent<HTMLElement>) => {
      callHandler(childProps.onBlur, e);
      hide();
    },
  } as Record<string, unknown>);

  const isMultiline =
    !isRich && ((label?.length ?? 0) > 36 || Boolean(label?.includes("\n")));

  return (
    <>
      {trigger}
      {open &&
        createPortal(
          <div
            ref={tooltipRef}
            // Screen readers announce trigger aria-label, but rich tooltips with
            // interactive content should have an accessible role.
            aria-hidden={!isRich}
            role={isRich ? "tooltip" : undefined}
            data-non-print="true"
            className={
              isRich
                ? "dc-tooltip-rich"
                : `dc-tooltip${isMultiline ? " dc-tooltip-multiline" : ""}`
            }
            onPointerEnter={
              isRich
                ? () => {
                    isOverTipRef.current = true;
                  }
                : undefined
            }
            onPointerLeave={
              isRich
                ? () => {
                    isOverTipRef.current = false;
                    hide();
                  }
                : undefined
            }
            style={{
              position: "fixed",
              top: coords?.top ?? 0,
              left: coords?.left ?? 0,
              // Hidden for the single frame between mount and measurement.
              visibility: coords ? "visible" : "hidden",
            }}
          >
            {isRich ? (
              <>
                {title && <div className="dc-tooltip-rich-subhead">{title}</div>}
                {label && <div className="dc-tooltip-rich-body">{label}</div>}
                {content}
                {(actionLabel || secondaryActionLabel) && (
                  <div className="dc-tooltip-rich-actions">
                    {secondaryActionLabel && (
                      <button
                        type="button"
                        className="dc-tooltip-rich-action-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          onSecondaryAction?.();
                          hide();
                        }}
                      >
                        {secondaryActionLabel}
                      </button>
                    )}
                    {actionLabel && (
                      <button
                        type="button"
                        className="dc-tooltip-rich-action-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          onAction?.();
                          hide();
                        }}
                      >
                        {actionLabel}
                      </button>
                    )}
                  </div>
                )}
              </>
            ) : (
              label
            )}
          </div>,
          document.body,
        )}
    </>
  );
}

/**
 * Picks the tooltip's viewport position.
 *
 * Flips to the opposite side when the preferred one would be clipped, then
 * clamps along the cross axis so a tooltip on an edge control stays on screen.
 */
export function place(
  anchor: Box,
  tip: Box,
  preferred: Placement,
): Coords {
  const side = fit(anchor, tip, preferred);
  const vertical = side === "top" || side === "bottom";

  const top = vertical
    ? side === "top"
      ? anchor.top - tip.height - OFFSET
      : anchor.bottom + OFFSET
    : anchor.top + anchor.height / 2 - tip.height / 2;

  const left = vertical
    ? anchor.left + anchor.width / 2 - tip.width / 2
    : side === "left"
      ? anchor.left - tip.width - OFFSET
      : anchor.right + OFFSET;

  return {
    top: clamp(top, tip.height, window.innerHeight),
    left: clamp(left, tip.width, window.innerWidth),
  };
}

/** Returns the preferred side, or its opposite when that side has no room. */
function fit(anchor: Box, tip: Box, preferred: Placement): Placement {
  const room: Record<Placement, number> = {
    top: anchor.top,
    bottom: window.innerHeight - anchor.bottom,
    left: anchor.left,
    right: window.innerWidth - anchor.right,
  };
  const opposite: Record<Placement, Placement> = {
    top: "bottom",
    bottom: "top",
    left: "right",
    right: "left",
  };
  const needed =
    (preferred === "top" || preferred === "bottom" ? tip.height : tip.width) +
    OFFSET;
  if (room[preferred] >= needed) return preferred;
  const other = opposite[preferred];
  return room[other] > room[preferred] ? other : preferred;
}

/** Keeps a position within the viewport, allowing for the tooltip's own size. */
function clamp(value: number, size: number, viewport: number): number {
  return Math.max(
    VIEWPORT_PAD,
    Math.min(value, viewport - size - VIEWPORT_PAD),
  );
}

/** Invokes a cloned child's original handler, when it had one. */
function callHandler(handler: unknown, event: unknown) {
  if (typeof handler === "function") {
    (handler as (e: unknown) => void)(event);
  }
}

/** Forwards the node to a ref the child already carried, in either form. */
function applyRef(ref: Ref<HTMLElement> | undefined, node: HTMLElement | null) {
  if (typeof ref === "function") ref(node);
  else if (ref && typeof ref === "object") {
    (ref as { current: HTMLElement | null }).current = node;
  }
}
