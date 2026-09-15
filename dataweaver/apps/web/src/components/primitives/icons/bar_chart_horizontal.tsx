import type { ComponentPropsWithRef } from 'react';

export const IconBarChartHorizontal = (props: ComponentPropsWithRef<'svg'>) => {
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
        d="M160-320h280v160H160v-160Zm0-240h640v160H160v-160Zm0-240h440v160H160v-160Z"
      />
    </svg>
  );
};
