import type { ComponentPropsWithRef } from 'react';

export const IconPencil = (props: ComponentPropsWithRef<'svg'>) => {
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
        d="M8.5 15.5h.713l4.887-4.887-.713-.713L8.5 14.787v.713Zm-1 1v-2.125l6.6-6.588c.1-.091.21-.162.331-.212a1.034 1.034 0 0 1 .769 0 .88.88 0 0 1 .325.225l.687.7c.1.092.173.2.22.325a1.084 1.084 0 0 1 0 .756.938.938 0 0 1-.22.332L9.625 16.5H7.5Zm6.238-6.238-.35-.362.712.713-.362-.35Z"
      />
    </svg>
  );
};
