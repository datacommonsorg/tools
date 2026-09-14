import type { ComponentPropsWithRef } from 'react';

export const IconLineGraphSingle = (props: ComponentPropsWithRef<'svg'>) => {
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
        d="m126-220-46-46 300-300 160 161 298-335 42 41-340 384-160-159-254 254Z"
      />
    </svg>
  );
};
