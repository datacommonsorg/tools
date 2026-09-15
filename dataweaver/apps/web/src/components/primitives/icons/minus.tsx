import type { ComponentPropsWithRef } from 'react';

export const IconMinus = (props: ComponentPropsWithRef<'svg'>) => {
  return (
    <svg
      {...props}
      viewBox="0 -960 960 960"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path fill="currentColor" d="M200-450v-60h560v60H200Z" />
    </svg>
  );
};
