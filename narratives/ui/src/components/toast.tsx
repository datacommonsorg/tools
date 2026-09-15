/**
 * @fileoverview Material 3 snackbar shown after an action completes.
 */

import { useEffect } from "react";

const COLOR_SURFACE = "#322F35";
const COLOR_TEXT = "#F5EFF7";
const FONT_STACK =
  '"Google Sans Text", "Google Sans", Inter, system-ui, sans-serif';

/** How long the snackbar stays up. M3 guidance is 4-10s for a short message. */
const VISIBLE_MS = 5000;

interface ToastProps {
  message: string;
  /** Optional trailing action, e.g. "Open file". */
  actionLabel?: string;
  onAction?: () => void;
  onDismiss: () => void;
}

/**
 * A single snackbar, pinned bottom-centre above the prompt box.
 *
 * Deliberately self-dismissing rather than a queue: the only caller is the PDF
 * export, one message at a time. `role="status"` rather than `alert` — this
 * confirms something the user asked for, so it should not interrupt them.
 */
export function Toast({ message, actionLabel, onAction, onDismiss }: ToastProps) {
  useEffect(() => {
    const timer = window.setTimeout(onDismiss, VISIBLE_MS);
    return () => window.clearTimeout(timer);
  }, [onDismiss]);

  return (
    <div
      role="status"
      aria-live="polite"
      data-non-print="true"
      className="fixed left-1/2 bottom-24 z-50 flex items-center shadow-lg"
      style={{
        transform: "translateX(-50%)",
        background: COLOR_SURFACE,
        color: COLOR_TEXT,
        borderRadius: 4,
        padding: actionLabel ? "6px 8px 6px 16px" : "14px 16px",
        gap: 8,
        minHeight: 48,
        maxWidth: "min(560px, calc(100vw - 32px))",
        fontFamily: FONT_STACK,
        fontSize: 14,
        lineHeight: "20px",
      }}
    >
      <span className="flex-1">{message}</span>
      {actionLabel && (
        <button
          type="button"
          onClick={() => {
            onAction?.();
            onDismiss();
          }}
          style={{
            background: "transparent",
            border: 0,
            color: "#D0BCFF",
            fontFamily: FONT_STACK,
            fontSize: 14,
            fontWeight: 500,
            padding: "10px 12px",
            borderRadius: 4,
          }}
        >
          {actionLabel}
        </button>
      )}
    </div>
  );
}
