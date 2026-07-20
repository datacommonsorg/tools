import type { ComponentPropsWithRef } from 'react';

export const IconExport = (props: ComponentPropsWithRef<'svg'>) => {
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
        d="M5.778 20c-.49 0-.908-.174-1.256-.522A1.712 1.712 0 0 1 4 18.222v-3.555h1.778v3.555h12.444V5.778H5.778v3.555H4V5.778c0-.49.174-.908.522-1.256A1.712 1.712 0 0 1 5.778 4h12.444c.49 0 .908.174 1.256.522.348.348.522.767.522 1.256v12.444c0 .49-.174.908-.522 1.256a1.712 1.712 0 0 1-1.256.522H5.778Zm4.889-3.556-1.245-1.288 2.267-2.267H4V11.11h7.689L9.422 8.844l1.245-1.288L15.11 12l-4.444 4.444Z"
      />
    </svg>
  );
};
