import type { ReactNode } from 'react';
import { AtlasProvider } from '~/components/scopes/atlas/atlas_provider';

interface AtlasLayoutProps {
  children: ReactNode;
}

const AtlasLayout = ({ children }: AtlasLayoutProps) => {
  return <AtlasProvider>{children}</AtlasProvider>;
};

export default AtlasLayout;
