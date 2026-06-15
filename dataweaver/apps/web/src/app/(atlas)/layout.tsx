import type { ReactNode } from 'react';
import { Toaster } from '~/components/foundations/toaster/toaster';
import { AtlasProvider } from '~/components/scopes/atlas/atlas_provider';

export const dynamic = 'force-dynamic';

interface AtlasLayoutProps {
  children: ReactNode;
}

const AtlasLayout = ({ children }: AtlasLayoutProps) => {
  return (
    <>
      <AtlasProvider licenseKey={process.env.TLDRAW_LICENSE_KEY}>
        {children}
      </AtlasProvider>
      <Toaster />
    </>
  );
};

export default AtlasLayout;
