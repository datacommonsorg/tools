import type { ReactNode } from 'react';
import { Toaster } from '~/components/foundations/toaster/toaster';
import { AtlasProvider } from '~/components/scopes/atlas/atlas';

interface AtlasLayoutProps {
  children: ReactNode;
}

const AtlasLayout = ({ children }: AtlasLayoutProps) => {
  return (
    <>
      <AtlasProvider>{children}</AtlasProvider>
      <Toaster />
    </>
  );
};

export default AtlasLayout;
