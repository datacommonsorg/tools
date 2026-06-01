import '~/styles/layers.css';
import '~/styles/core.scss';
import type { ReactNode } from 'react';
import { MotionProvider } from '~/components/foundations/motion_provider';

interface RootLayoutProps {
  children: ReactNode;
}

const RootLayout = ({ children }: RootLayoutProps) => {
  return (
    <html lang="en">
      <body>
        <MotionProvider>
          <main>{children}</main>
        </MotionProvider>
      </body>
    </html>
  );
};

export default RootLayout;
