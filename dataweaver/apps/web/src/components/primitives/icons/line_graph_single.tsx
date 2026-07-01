import type { ComponentPropsWithRef } from 'react';

export const IconLineGraphSingle = (props: ComponentPropsWithRef<'svg'>) => {
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
        d="m6.086 16.523-1.044-1.044 5.219-5.218 2.783 2.783 4.94-5.567.974.974-5.914 6.68-2.784-2.783-4.174 4.175Z"
      />
    </svg>
  );
};
