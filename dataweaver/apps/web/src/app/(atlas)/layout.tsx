import type { ReactNode } from 'react';
import { AtlasProvider } from '~/components/scopes/atlas/atlas';

interface AtlasLayoutProps {
  children: ReactNode;
}

const AtlasLayout = ({ children }: AtlasLayoutProps) => {
  return <AtlasProvider>{children}</AtlasProvider>;
};

export default AtlasLayout;
