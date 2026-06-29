import type { ComponentPropsWithRef } from 'react';

export const IconNarrative = (props: ComponentPropsWithRef<'svg'>) => {
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
        d="M2 22v-2h12v2H2Zm0-5v-2h18v2H2Zm0-5v-2h11v2H2Zm15.5-1c-.1 0-.167-.05-.2-.15a5.589 5.589 0 0 0-1.525-2.625A5.588 5.588 0 0 0 13.15 6.7c-.1-.033-.15-.1-.15-.2 0-.117.05-.183.15-.2a5.685 5.685 0 0 0 2.625-1.5A5.75 5.75 0 0 0 17.3 2.15c.033-.1.1-.15.2-.15.117 0 .183.05.2.15a6.056 6.056 0 0 0 1.525 2.65 5.685 5.685 0 0 0 2.625 1.5c.1.017.15.083.15.2 0 .1-.05.167-.15.2a5.75 5.75 0 0 0-2.65 1.525 5.686 5.686 0 0 0-1.5 2.625c-.017.1-.083.15-.2.15Z"
      />
    </svg>
  );
};
