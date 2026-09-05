import type { ComponentPropsWithRef } from 'react';

export const IconMap = (props: ComponentPropsWithRef<'svg'>) => {
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
        d="m15 21-6-2.1-4.65 1.8q-.5.2-.925-.088T3 19.75V5.45q0-.325.188-.587t.512-.363L9 3l6 2.1 4.65-1.8q.5-.2.925.088t.425.862v14.3q0 .325-.187.588t-.513.362L15 21Zm-5-3.15 4 1.4V6.15l-4-1.4v13.1ZM5 18.6l3-1.15V4.6L5 5.65v12.95Zm11 0 3-1.05V4.6l-3 1.15v12.85Z"
      />
    </svg>
  );
};
