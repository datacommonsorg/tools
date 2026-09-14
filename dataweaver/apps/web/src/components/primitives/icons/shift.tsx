import type { ComponentPropsWithRef } from 'react';

export const IconShift = (props: ComponentPropsWithRef<'svg'>) => {
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
        d="M480-685.6 240-445.76h137.16v171.28h205.68v-171.28H720L480-685.6Zm68.56 205.6v171.28h-137.12V-480H325.72L480-636.88 634.28-480h-85.72Z"
      />
    </svg>
  );
};
