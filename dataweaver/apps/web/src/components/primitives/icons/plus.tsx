import type { ComponentPropsWithRef } from 'react';

export const IconPlus = (props: ComponentPropsWithRef<'svg'>) => {
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
        d="M450-450H200v-60h250v-250h60v250h250v60H510v250h-60v-250Z"
      />
    </svg>
  );
};
