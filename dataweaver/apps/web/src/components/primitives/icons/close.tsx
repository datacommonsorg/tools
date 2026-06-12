import type { ComponentPropsWithRef } from 'react';

export const IconClose = (props: ComponentPropsWithRef<'svg'>) => {
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
        d="m20.446 4.447-7.553 7.554 7.553 7.554-.892.892L12 12.894l-7.554 7.553-.892-.892L11.107 12 3.554 4.447l.892-.892L12 11.108l7.554-7.553.892.892Z"
      />
    </svg>
  );
};
