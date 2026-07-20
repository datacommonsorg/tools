/**
 * @fileoverview Shared inline SVG icon components and their size-token system.
 */

import type { SVGProps } from "react";

/**
 * Icon pixel sizes keyed by a semantic token. Centralised here so icon sizing
 * is consistent and adjustable in one place, rather than hard-coded as magic
 * numbers at each call site.
 *
 * TODO(theme): ideally these come from the branding/theme layer so a downstream
 * instance can rescale icons; kept local until the theme exposes a size scale.
 */
const ICON_SIZES = {
  xs: 16,
  sm: 20,
  md: 22,
  lg: 24,
} as const;

/** Semantic icon-size token; maps to a pixel dimension via {@link ICON_SIZES}. */
export type IconSizeToken = keyof typeof ICON_SIZES;

/**
 * Props shared by every icon: all standard SVG attributes (className, style,
 * event handlers, aria-*, …) plus a semantic `size` token. Rotation/animation
 * are the caller's responsibility via `className` — icons are not aware of it.
 */
export interface IconProps extends Omit<SVGProps<SVGSVGElement>, "size"> {
  size?: IconSizeToken;
}

/**
 * Builds the common <svg> attributes for an icon from a size token, spreading
 * any caller-supplied SVG props on top and composing their `className` with the
 * shared base classes.
 */
export function getSvgProps(
  size: IconSizeToken = "md",
  props: Omit<SVGProps<SVGSVGElement>, "size"> = {},
): SVGProps<SVGSVGElement> {
  const dimension = ICON_SIZES[size];
  return {
    width: dimension,
    height: dimension,
    fill: "currentColor",
    "aria-hidden": true,
    ...props,
    className: `shrink-0 select-none ${props.className ?? ""}`.trim(),
  };
}

/** `pen_spark` — New chat. */
export function NewChatIcon({ size = "md", ...props }: IconProps) {
  return (
    <svg viewBox="0 -960 960 960" {...getSvgProps(size, props)}>
      <path d="M240-200h57l391-391-57-57-391 391v57Zm-80 80v-170l528-527q12-11 26.5-17t30.5-6q16 0 31 6t26 18l55 56q12 11 17.5 26t5.5 30q0 16-5.5 30.5T857-647L330-120H160Zm640-584-56-56 56 56Zm-141 85-28-29 57 57-29-28Zm-439 59q-6 0-8-6-16-61-60.5-105.5T46-732q-6-2-6-8 0-7 6-8 61-16 105.5-60.5T212-914q2-6 8-6 7 0 8 6 17 61 61 105.5T394-748q6 1 6 8 0 6-6 8-61 16-105.5 60.5T228-566q-1 6-8 6Z" />
    </svg>
  );
}

/** `notes_spark` — Chats. */
export function ChatsIcon({ size = "md", ...props }: IconProps) {
  return (
    <svg viewBox="0 -960 960 960" {...getSvgProps(size, props)}>
      <path d="M740-40q-6 0-8-6-16-61-60.5-105.5T566-212q-6-2-6-8 0-7 6-8 61-16 105.5-60.5T732-394q2-6 8-6 7 0 8 6 17 61 61 105.5T914-228q6 1 6 8 0 6-6 8-61 16-105.5 60.5T748-46q-1 6-8 6ZM120-280v-80h360v80H120Zm0-200v-80h720v80H120Zm0-200v-80h720v80H120Z" />
    </svg>
  );
}

/** `menu` — hamburger / accordion toggle. */
export function MenuIcon({ size = "lg", ...props }: IconProps) {
  return (
    <svg viewBox="0 -960 960 960" {...getSvgProps(size, props)}>
      <path d="M120-240v-80h720v80H120Zm0-200v-80h720v80H120Zm0-200v-80h720v80H120Z" />
    </svg>
  );
}

/**
 * `expand_more` — downward chevron. Not responsible for its own rotation: the
 * caller rotates it via `className` (e.g. `-rotate-90` when collapsed).
 */
export function ChevronDownIcon({ size = "xs", ...props }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" {...getSvgProps(size, props)}>
      <path d="M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6z" />
    </svg>
  );
}

/**
 * `edit` (pencil) — leading glyph on the Export PDF button. Kept on its native
 * 24×24 viewBox; matches the Figma leading-icon slot (node 3427-16783).
 */
export function ExportIcon({ size = "sm", ...props }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" {...getSvgProps(size, props)}>
      <path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z" />
    </svg>
  );
}
