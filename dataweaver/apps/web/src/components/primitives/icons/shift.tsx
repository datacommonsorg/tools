import type { ComponentPropsWithRef } from 'react';

export const IconShift = (props: ComponentPropsWithRef<'svg'>) => {
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
        d="m12 6.861-6 5.996h3.429v4.282h5.142v-4.282H18L12 6.86Zm1.714 5.14v4.282h-3.428V12H8.143L12 8.078 15.857 12h-2.143Z"
      />
    </svg>
  );
};
