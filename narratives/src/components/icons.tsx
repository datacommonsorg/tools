/**
 * @fileoverview Provides shared inline SVG icon components used across the UI.
 */

/**
 * Google Material Symbols icons used across the chat UI.
 *
 * These are the real `pen_spark` (New chat), `notes_spark` (Chats) and
 * `menu` (accordion / hamburger) glyphs. They use the Material Symbols
 * 0 -960 960 960 viewBox and fill `currentColor` so they inherit text color.
 */

interface IconProps {
  readonly size?: number;
  readonly className?: string;
}

/**
 * `pen_spark` — New chat.
 */
export function NewChatIcon({ size = 22, className = "" }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 -960 960 960"
      fill="currentColor"
      aria-hidden="true"
      className={className}
    >
      <path d="M240-200h57l391-391-57-57-391 391v57Zm-80 80v-170l528-527q12-11 26.5-17t30.5-6q16 0 31 6t26 18l55 56q12 11 17.5 26t5.5 30q0 16-5.5 30.5T857-647L330-120H160Zm640-584-56-56 56 56Zm-141 85-28-29 57 57-29-28Zm-439 59q-6 0-8-6-16-61-60.5-105.5T46-732q-6-2-6-8 0-7 6-8 61-16 105.5-60.5T212-914q2-6 8-6 7 0 8 6 17 61 61 105.5T394-748q6 1 6 8 0 6-6 8-61 16-105.5 60.5T228-566q-1 6-8 6Z" />
    </svg>
  );
}

/**
 * `notes_spark` — Chats.
 */
export function ChatsIcon({ size = 22, className = "" }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 -960 960 960"
      fill="currentColor"
      aria-hidden="true"
      className={className}
    >
      <path d="M740-40q-6 0-8-6-16-61-60.5-105.5T566-212q-6-2-6-8 0-7 6-8 61-16 105.5-60.5T732-394q2-6 8-6 7 0 8 6 17 61 61 105.5T914-228q6 1 6 8 0 6-6 8-61 16-105.5 60.5T748-46q-1 6-8 6ZM120-280v-80h360v80H120Zm0-200v-80h720v80H120Zm0-200v-80h720v80H120Z" />
    </svg>
  );
}

/**
 * `menu` — hamburger / accordion toggle.
 */
export function MenuIcon({ size = 24, className = "" }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 -960 960 960"
      fill="currentColor"
      aria-hidden="true"
      className={className}
    >
      <path d="M120-240v-80h720v80H120Zm0-200v-80h720v80H120Zm0-200v-80h720v80H120Z" />
    </svg>
  );
}
