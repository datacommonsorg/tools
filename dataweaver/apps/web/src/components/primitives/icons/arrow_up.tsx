import type { ComponentPropsWithRef } from 'react';

export const IconArrowUp = (props: ComponentPropsWithRef<'svg'>) => {
  return (
    <svg
      {...props}
      viewBox="0 -960 960 960"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        fill="currentColor"
        d="M450-160v-526L202-438l-42-42 320-320 320 320-42 42-248-248v526h-60Z"
      />
    </svg>
  );
};
