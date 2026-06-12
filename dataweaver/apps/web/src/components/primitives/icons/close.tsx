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
        fillRule="evenodd"
        clipRule="evenodd"
        d="m12.893 12.001 7.553-7.554-.892-.892L12 11.108 4.446 3.555l-.892.892 7.553 7.554-7.553 7.554.892.892L12 12.894l7.554 7.553.892-.892L12.893 12Z"
      />
    </svg>
  );
};
