import type { ComponentPropsWithRef } from 'react';

export const IconCursor = (props: ComponentPropsWithRef<'svg'>) => {
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
        d="M8 13.75 9.975 11h4.25L8 6.1v7.65ZM13.775 22l-3.625-7.8L6 20V2l14 11h-7.1l3.6 7.725L13.775 22Z"
      />
    </svg>
  );
};
