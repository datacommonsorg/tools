import type { ComponentPropsWithRef } from 'react';

export const IconDownload = (props: ComponentPropsWithRef<'svg'>) => {
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
        d="m12 15.334-4.167-4.167L9 9.96l2.167 2.167V5.334h1.666v6.792L15 9.959l1.167 1.208L12 15.334Zm-5 3.333c-.458 0-.85-.163-1.177-.49a1.605 1.605 0 0 1-.49-1.176v-2.5H7V17h10v-2.5h1.667V17c0 .458-.164.85-.49 1.177-.326.326-.719.49-1.177.49H7Z"
      />
    </svg>
  );
};
