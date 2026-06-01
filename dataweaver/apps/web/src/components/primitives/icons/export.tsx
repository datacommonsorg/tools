import type { ComponentPropsWithRef } from 'react';

export const IconExport = (props: ComponentPropsWithRef<'svg'>) => {
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
        d="M3.833 22.5a2.247 2.247 0 0 1-1.648-.685 2.247 2.247 0 0 1-.685-1.648V15.5h2.333v4.667h16.334V3.833H3.833V8.5H1.5V3.833c0-.641.228-1.19.685-1.648A2.247 2.247 0 0 1 3.833 1.5h16.334c.641 0 1.19.228 1.648.685.456.457.685 1.007.685 1.648v16.334c0 .641-.229 1.19-.685 1.648a2.247 2.247 0 0 1-1.648.685H3.833Zm6.417-4.667-1.633-1.691 2.975-2.975H1.5v-2.334h10.092L8.617 7.858l1.633-1.691L16.083 12l-5.833 5.833Z"
      />
    </svg>
  );
};
