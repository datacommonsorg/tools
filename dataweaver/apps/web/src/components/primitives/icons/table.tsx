import type { ComponentPropsWithRef } from 'react';

export const IconTable = (props: ComponentPropsWithRef<'svg'>) => {
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
        d="M16.871 18.262H7.13c-.383 0-.713-.133-.992-.4a1.384 1.384 0 0 1-.4-.991V7.129c0-.382.134-.707.4-.974.279-.278.61-.417.992-.417h9.741c.383 0 .707.139.974.417.279.267.418.592.418.974v9.742c0 .382-.14.713-.418.991-.267.267-.591.4-.974.4ZM7.13 9.217h9.741V7.129H7.13v2.088Zm1.74 1.391H7.13v6.263h1.74v-6.263Zm6.262 0v6.263h1.74v-6.263h-1.74Zm-1.392 0h-3.479v6.263h3.479v-6.263Z"
      />
    </svg>
  );
};
