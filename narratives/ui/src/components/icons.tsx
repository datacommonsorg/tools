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

/**
 * `send` — the paper-plane glyph inside the query input's action button. Only
 * the glyph: the 40px circle behind it is button chrome in JSX, themed via
 * `bg-surface-blue`, so it is not duplicated here.
 */
export function SendIcon({ size = "xs", ...props }: IconProps) {
  // The source asset was a 40x40 button, so its coordinate space includes the
  // circular background; the glyph itself only spans x 13-26.7, y 14.4-25.7.
  // The viewBox is tightened to a 16-unit square centred on that, otherwise the
  // arrow renders at roughly a third of the requested size inside its button.
  //
  // Size defaults to `xs` (16px) because the asset draws the arrow at 34% of
  // its 40px button; a 16px render reproduces that ratio in the 40px chrome.
  return (
    <svg viewBox="11.85 12.05 16 16" {...getSvgProps(size, props)}>
      <path d="M14.0208 25.5833C13.7708 25.6806 13.5347 25.6597 13.3125 25.5208C13.1042 25.3681 13 25.1597 13 24.8958V22L19 20L13 18V15.1042C13 14.8403 13.1042 14.6389 13.3125 14.5C13.5347 14.3472 13.7708 14.3194 14.0208 14.4167L26.25 19.3125C26.5694 19.4375 26.7292 19.6667 26.7292 20C26.7292 20.3333 26.5694 20.5625 26.25 20.6875L14.0208 25.5833Z" />
    </svg>
  );
}

/**
 * `gemini-info` — the info glyph on the AI-generated-content disclaimer.
 */
export function GeminiInfoIcon({ size = "sm", ...props }: IconProps) {
  return (
    <svg viewBox="0 0 14 14" {...getSvgProps(size, props)}>
      <path d="M6 10.6667V6.66667H7.33333V10.6667H6ZM6.66667 6C6.47778 6 6.31944 5.93611 6.19167 5.80833C6.06389 5.68056 6 5.52222 6 5.33333C6 5.14444 6.06389 4.98611 6.19167 4.85833C6.31944 4.73056 6.47778 4.66667 6.66667 4.66667C6.85556 4.66667 7.01389 4.73056 7.14167 4.85833C7.26944 4.98611 7.33333 5.14444 7.33333 5.33333C7.33333 5.52222 7.26944 5.68056 7.14167 5.80833C7.01389 5.93611 6.85556 6 6.66667 6ZM11.9 6.33333L13 5.23333C13.1111 5.56667 13.1944 5.90833 13.25 6.25833C13.3056 6.60833 13.3333 6.96667 13.3333 7.33333C13.3333 8.25556 13.1583 9.12222 12.8083 9.93333C12.4583 10.7444 11.9833 11.45 11.3833 12.05C10.7833 12.65 10.0778 13.125 9.26667 13.475C8.45556 13.825 7.58889 14 6.66667 14C5.74444 14 4.87778 13.825 4.06667 13.475C3.25556 13.125 2.55 12.65 1.95 12.05C1.35 11.45 0.875 10.7444 0.525 9.93333C0.175 9.12222 0 8.25556 0 7.33333C0 6.41111 0.175 5.54444 0.525 4.73333C0.875 3.92222 1.35 3.21667 1.95 2.61667C2.55 2.01667 3.25556 1.54167 4.06667 1.19167C4.87778 0.841667 5.74444 0.666667 6.66667 0.666667C7.03333 0.666667 7.39167 0.694444 7.74167 0.75C8.09167 0.805556 8.43333 0.888889 8.76667 1L7.66667 2.1C7.5 2.06667 7.33611 2.04167 7.175 2.025C7.01389 2.00833 6.84444 2 6.66667 2C5.17778 2 3.91667 2.51667 2.88333 3.55C1.85 4.58333 1.33333 5.84444 1.33333 7.33333C1.33333 8.82222 1.85 10.0833 2.88333 11.1167C3.91667 12.15 5.17778 12.6667 6.66667 12.6667C8.15556 12.6667 9.41667 12.15 10.45 11.1167C11.4833 10.0833 12 8.82222 12 7.33333C12 7.15556 11.9917 6.98611 11.975 6.825C11.9583 6.66389 11.9333 6.5 11.9 6.33333ZM10.3333 7.33333C10.3333 6.31111 9.97778 5.44444 9.26667 4.73333C8.55556 4.02222 7.68889 3.66667 6.66667 3.66667C7.68889 3.66667 8.55556 3.31111 9.26667 2.6C9.97778 1.88889 10.3333 1.02222 10.3333 0C10.3333 1.02222 10.6889 1.88889 11.4 2.6C12.1111 3.31111 12.9778 3.66667 14 3.66667C12.9778 3.66667 12.1111 4.02222 11.4 4.73333C10.6889 5.44444 10.3333 6.31111 10.3333 7.33333Z" />
    </svg>
  );
}

/** `pen_spark` — New chat. */
export function NewChatIcon({ size = "md", ...props }: IconProps) {
  return (
    <svg viewBox="0 0 15 15" {...getSvgProps(size, props)}>
      <path d="M1.55547 14.5691C1.11797 14.5691 0.749219 14.4191 0.449219 14.1191C0.149219 13.8191 -0.000781 13.4504 -0.000781 13.0129V3.22539C-0.000781 2.78789 0.149219 2.41914 0.449219 2.11914C0.749219 1.81914 1.11797 1.66914 1.55547 1.66914H6.01797C6.28047 1.66914 6.47422 1.75039 6.59922 1.91289C6.73672 2.07539 6.80547 2.25039 6.80547 2.43789C6.80547 2.63789 6.73672 2.81914 6.59922 2.98164C6.47422 3.14414 6.28047 3.22539 6.01797 3.22539H1.55547V13.0129H11.343V9.00039C11.343 8.73789 11.4242 8.54414 11.5867 8.41914C11.7492 8.29414 11.9305 8.23164 12.1305 8.23164C12.318 8.23164 12.493 8.29414 12.6555 8.41914C12.818 8.54414 12.8992 8.73789 12.8992 9.00039V13.0129C12.8992 13.4504 12.7492 13.8191 12.4492 14.1191C12.1492 14.4191 11.7805 14.5691 11.343 14.5691H1.55547ZM4.57422 9.22539V7.66914C4.57422 7.46914 4.61172 7.27539 4.68672 7.08789C4.76172 6.90039 4.87422 6.72539 5.02422 6.56289L11.1555 0.45039C11.3055 0.28789 11.4742 0.17539 11.6617 0.112889C11.8492 0.0378898 12.043 0.000390053 12.243 0.000390053C12.443 0.000390053 12.6367 0.0378898 12.8242 0.112889C13.0117 0.17539 13.1867 0.28789 13.3492 0.45039L14.118 1.21914C14.2805 1.38164 14.393 1.55664 14.4555 1.74414C14.5305 1.93164 14.568 2.12539 14.568 2.32539C14.568 2.52539 14.5305 2.71914 14.4555 2.90664C14.393 3.09414 14.2805 3.26914 14.118 3.43164L8.00547 9.54414C7.84297 9.69414 7.66797 9.80664 7.48047 9.88164C7.29297 9.95664 7.09922 9.99414 6.89922 9.99414H5.36172C5.14922 9.99414 4.96172 9.91914 4.79922 9.76914C4.64922 9.61914 4.57422 9.43789 4.57422 9.22539ZM13.143 2.32539L12.243 1.42539L13.143 2.32539ZM6.03672 8.53164H6.93672L11.2305 4.23789L10.7992 3.76914L10.3305 3.33789L6.03672 7.63164V8.53164ZM10.7992 3.76914L10.3305 3.33789L10.7992 3.76914L11.2305 4.23789L10.7992 3.76914Z" />
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
    <svg viewBox="0 0 24 24" {...getSvgProps(size, props)}>
      <path d="M4.25 17.625C4.03333 17.625 3.85 17.5583 3.7 17.425C3.56667 17.275 3.5 17.1 3.5 16.9C3.5 16.6833 3.56667 16.5 3.7 16.35C3.85 16.2 4.03333 16.125 4.25 16.125H19.75C19.9667 16.125 20.1417 16.2 20.275 16.35C20.425 16.5 20.5 16.6833 20.5 16.9C20.5 17.1 20.425 17.275 20.275 17.425C20.1417 17.5583 19.9667 17.625 19.75 17.625H4.25ZM4.25 12.75C4.03333 12.75 3.85 12.6833 3.7 12.55C3.56667 12.4 3.5 12.2167 3.5 12C3.5 11.7833 3.56667 11.6083 3.7 11.475C3.85 11.325 4.03333 11.25 4.25 11.25H19.75C19.9667 11.25 20.1417 11.325 20.275 11.475C20.425 11.6083 20.5 11.7833 20.5 12C20.5 12.2167 20.425 12.4 20.275 12.55C20.1417 12.6833 19.9667 12.75 19.75 12.75H4.25ZM4.25 7.875C4.03333 7.875 3.85 7.8 3.7 7.65C3.56667 7.5 3.5 7.325 3.5 7.125C3.5 6.90833 3.56667 6.73333 3.7 6.6C3.85 6.45 4.03333 6.375 4.25 6.375H19.75C19.9667 6.375 20.1417 6.45 20.275 6.6C20.425 6.73333 20.5 6.90833 20.5 7.125C20.5 7.325 20.425 7.5 20.275 7.65C20.1417 7.8 19.9667 7.875 19.75 7.875H4.25Z" />
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
      <path d="M12 15.4L6 9.4L7.4 8L12 12.6L16.6 8L18 9.4L12 15.4Z" />
    </svg>
  );
}

/**
 * `output` — an arrow leaving a container; leading glyph on the Export PDF
 * button. Supersedes the `edit` pencil Figma had left in as a placeholder.
 */
/**
 * `inspect` — a magnifier over a document, used for the provenance inspector.
 * A magnifier rather than an info glyph: this opens a detailed audit view, it is
 * not a tooltip. GeminiInfoIcon already carries the "explanatory note" meaning
 * on the disclaimer, so reusing it here would blur the two.
 */
export function InspectIcon({ size = "sm", ...props }: IconProps) {
  return (
    <svg viewBox="0 0 20 20" {...getSvgProps(size, props)}>
      {/* Document */}
      <path d="M3 1.5C3 0.947715 3.44772 0.5 4 0.5H11.5L15.5 4.5V9.2C15.0374 8.94341 14.5327 8.75558 14 8.64957V5.5H10.5V2H4.5V16H8.14957C8.25558 16.5327 8.44341 17.0374 8.7 17.5H4C3.44772 17.5 3 17.0523 3 16.5V1.5Z" />
      {/* Magnifier over its lower-right corner */}
      <path d="M13 10C11.067 10 9.5 11.567 9.5 13.5C9.5 15.433 11.067 17 13 17C13.7418 17 14.4297 16.7692 14.9963 16.3748L17.4393 18.8178C17.7322 19.1107 18.2071 19.1107 18.5 18.8178C18.7929 18.5249 18.7929 18.05 18.5 17.7571L16.0748 15.3319C16.4692 14.7653 16.7 14.0774 16.7 13.3356C16.7 11.4026 15.133 9.83564 13.2 9.83564L13 10ZM11 13.5C11 12.3954 11.8954 11.5 13 11.5C14.1046 11.5 15 12.3954 15 13.5C15 14.6046 14.1046 15.5 13 15.5C11.8954 15.5 11 14.6046 11 13.5Z" />
    </svg>
  );
}

export function ExportIcon({ size = "sm", ...props }: IconProps) {
  return (
    <svg viewBox="0 0 15 14" {...getSvgProps(size, props)}>
      <path d="M1.5 14C1.08333 14 0.729167 13.8542 0.4375 13.5625C0.145834 13.2708 1.19209e-07 12.9167 1.19209e-07 12.5V1.5C1.19209e-07 1.08333 0.145834 0.729166 0.4375 0.437499C0.729167 0.145833 1.08333 -4.76837e-07 1.5 -4.76837e-07H12.5C12.9167 -4.76837e-07 13.2708 0.145833 13.5625 0.437499C13.8542 0.729166 14 1.08333 14 1.5V3H12.5V1.5H1.5V12.5H12.5V11H14V12.5C14 12.9167 13.8542 13.2708 13.5625 13.5625C13.2708 13.8542 12.9167 14 12.5 14H1.5ZM11 11L9.9375 9.9375L12.125 7.75H5V6.25H12.125L9.9375 4.0625L11 3L15 7L11 11Z" />
    </svg>
  );
}
