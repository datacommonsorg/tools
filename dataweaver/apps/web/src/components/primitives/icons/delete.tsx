import type { ComponentPropsWithRef } from 'react';

export const IconDelete = (props: ComponentPropsWithRef<'svg'>) => {
  return (
    <svg
      {...props}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        fill="currentcolor"
        d="M6.167 22.5a2.247 2.247 0 0 1-1.648-.685 2.247 2.247 0 0 1-.685-1.648V5H2.667V2.667H8.5V1.5h7v1.167h5.834V5h-1.167v15.167c0 .641-.229 1.19-.685 1.648a2.247 2.247 0 0 1-1.648.685H6.167ZM17.834 5H6.167v15.167h11.667V5ZM8.5 17.833h2.334v-10.5H8.5v10.5Zm4.667 0H15.5v-10.5h-2.333v10.5Z"
      />
    </svg>
  );
};
