import type { ComponentPropsWithRef } from 'react';

export const IconLineAxis = (props: ComponentPropsWithRef<'svg'>) => {
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
        d="m140-185-46-46 300-300 160 161 93-104-249-238-258 258-46-46 300-300 293 280 165-185 42 41-164 185 163 156-43 43-160-153-136 153-160-159-254 254Z"
      />
    </svg>
  );
};
