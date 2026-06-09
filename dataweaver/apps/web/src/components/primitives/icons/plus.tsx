import type { ComponentPropsWithRef } from 'react';

export const IconPlus = (props: ComponentPropsWithRef<'svg'>) => {
  return (
    <svg
      {...props}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        fill="currentcolor"
        d="M11.074 7.531h1.852v3.542h3.562v1.852h-3.562v3.542h-1.852v-3.542H7.512v-1.852h3.562V7.531Z"
      />
    </svg>
  );
};
