import type { ComponentPropsWithRef } from 'react';

export const IconBarChart = (props: ComponentPropsWithRef<'svg'>) => {
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
        d="M6.167 17.833H8.5V9.667H6.167v8.166Zm4.666 0h2.334V6.167h-2.334v11.666Zm4.667 0h2.333v-4.666H15.5v4.666ZM3.833 22.5a2.247 2.247 0 0 1-1.648-.685 2.247 2.247 0 0 1-.685-1.648V3.833c0-.641.228-1.19.685-1.648A2.247 2.247 0 0 1 3.833 1.5h16.334c.641 0 1.19.228 1.648.685.456.457.685 1.007.685 1.648v16.334c0 .641-.229 1.19-.685 1.648a2.247 2.247 0 0 1-1.648.685H3.833Zm0-2.333h16.334V3.833H3.833v16.334Z"
      />
    </svg>
  );
};
