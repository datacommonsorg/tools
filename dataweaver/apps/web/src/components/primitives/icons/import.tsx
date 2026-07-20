import type { ComponentPropsWithRef } from 'react';

export const IconImport = (props: ComponentPropsWithRef<'svg'>) => {
  return (
    <svg
      {...props}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        fill="currentColor"
        d="M6.625 20.5c-.447 0-.83-.157-1.148-.47A1.529 1.529 0 0 1 5 18.9v-2.4h1.625v2.4h9.75v-2.4H18v2.4c0 .44-.16.817-.477 1.13a1.58 1.58 0 0 1-1.148.47h-9.75Zm5.975-16v8.15l2.86-2.6L17 11.5l-5.5 5-5.5-5 1.54-1.45 2.86 2.6V4.5h2.2Z"
      />
    </svg>
  );
};
