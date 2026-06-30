import type { ComponentPropsWithRef } from 'react';

export const IconUndo = (props: ComponentPropsWithRef<'svg'>) => {
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
        d="M14.1 19.5c1.617 0 3.004-.525 4.162-1.575C19.421 16.875 20 15.567 20 14c0-1.567-.58-2.875-1.738-3.925C17.104 9.025 15.717 8.5 14.1 8.5H7.8l2.6-2.6L9 4.5l-5 5 5 5 1.4-1.4-2.6-2.6h6.3c1.05 0 1.963.333 2.737 1C17.613 12.167 18 13 18 14s-.387 1.833-1.163 2.5c-.774.667-1.687 1-2.737 1H7v2h7.1Z"
      />
    </svg>
  );
};
