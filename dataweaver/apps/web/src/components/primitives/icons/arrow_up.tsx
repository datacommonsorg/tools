import type { ComponentPropsWithRef } from 'react';

export const IconArrowUp = (props: ComponentPropsWithRef<'svg'>) => {
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
        d="M19.66 11.288a1.14 1.14 0 0 1-1.617 0l-4.9-4.9v13.99a1.142 1.142 0 1 1-2.284 0V6.387l-4.902 4.9A1.144 1.144 0 1 1 4.339 9.67l6.852-6.852a1.142 1.142 0 0 1 1.618 0L19.66 9.67a1.14 1.14 0 0 1 0 1.618Z"
      />
    </svg>
  );
};
