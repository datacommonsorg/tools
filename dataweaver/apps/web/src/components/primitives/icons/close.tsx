import type { ComponentPropsWithRef } from 'react';

export const IconClose = (props: ComponentPropsWithRef<'svg'>) => {
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
        d="m249-207-42-42 231-231-231-231 42-42 231 231 231-231 42 42-231 231 231 231-42 42-231-231-231 231Z"
      />
    </svg>
  );
};
