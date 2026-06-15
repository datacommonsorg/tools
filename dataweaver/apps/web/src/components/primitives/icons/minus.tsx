import type { ComponentPropsWithRef } from 'react';

export const IconMinus = (props: ComponentPropsWithRef<'svg'>) => {
  return (
    <svg
      {...props}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path fill="currentColor" d="M8.7 12.926v-1.852h6.6v1.852H8.7Z" />
    </svg>
  );
};
