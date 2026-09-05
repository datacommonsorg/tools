import type { ComponentPropsWithRef } from 'react';

export const IconPlay = (props: ComponentPropsWithRef<'svg'>) => {
  return (
    <svg
      {...props}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path fill="currentColor" d="M8 19V5l11 7-11 7Z" />
    </svg>
  );
};
