import type { ComponentPropsWithRef } from 'react';

export const IconBarChartHorizontal = (props: ComponentPropsWithRef<'svg'>) => {
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
        d="M4 16h7v4H4v-4Zm0-6h16v4H4v-4Zm0-6h11v4H4V4Z"
      />
    </svg>
  );
};
