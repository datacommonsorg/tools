import type { ComponentPropsWithRef } from 'react';

export const IconBarChartVertical = (props: ComponentPropsWithRef<'svg'>) => {
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
        d="M16 20v-7h4v7h-4Zm-6 0V4h4v16h-4Zm-6 0V9h4v11H4Z"
      />
    </svg>
  );
};
