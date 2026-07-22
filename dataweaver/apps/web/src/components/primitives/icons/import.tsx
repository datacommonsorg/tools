import type { ComponentPropsWithRef } from 'react';

export const IconImport = (props: ComponentPropsWithRef<'svg'>) => {
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
        d="M5.602 22.5a2.07 2.07 0 0 1-1.507-.617A2.007 2.007 0 0 1 3.47 20.4v-3.15h2.333v2.917h12.396V17.25h2.333v3.15c0 .578-.209 1.072-.626 1.483a2.07 2.07 0 0 1-1.507.617H5.602Zm.565-12.25 1.691-1.633 2.975 2.975V1.5h2.334v10.092l2.975-2.975 1.691 1.633L12 16.083 6.167 10.25Z"
      />
    </svg>
  );
};
