import type { ComponentPropsWithRef } from 'react';

export const IconRedo = (props: ComponentPropsWithRef<'svg'>) => {
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
        d="M9.9 19.5c-1.617 0-3.004-.525-4.163-1.575C4.58 16.875 4 15.567 4 14c0-1.567.58-2.875 1.737-3.925C6.896 9.025 8.284 8.5 9.9 8.5h6.3l-2.6-2.6L15 4.5l5 5-5 5-1.4-1.4 2.6-2.6H9.9c-1.05 0-1.963.333-2.738 1C6.388 12.167 6 13 6 14s.388 1.833 1.162 2.5c.776.667 1.688 1 2.738 1H17v2H9.9Z"
      />
    </svg>
  );
};
