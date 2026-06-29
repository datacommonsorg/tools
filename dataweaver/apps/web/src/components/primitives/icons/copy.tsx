import type { ComponentPropsWithRef } from 'react';

export const IconCopy = (props: ComponentPropsWithRef<'svg'>) => {
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
        d="M9.917 17c-.459 0-.85-.164-1.177-.49a1.605 1.605 0 0 1-.49-1.177v-10c0-.459.163-.851.49-1.177.326-.327.718-.49 1.177-.49h7.5c.458 0 .85.163 1.177.49.326.326.49.718.49 1.177v10c0 .458-.164.85-.49 1.177-.327.326-.719.49-1.177.49h-7.5Zm0-1.667h7.5v-10h-7.5v10Zm-3.334 5c-.458 0-.85-.163-1.177-.49a1.605 1.605 0 0 1-.49-1.177V6.999h1.667v11.667h9.167v1.667H6.583Z"
      />
    </svg>
  );
};
