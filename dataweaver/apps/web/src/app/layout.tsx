import '~/styles/layers.css';
import '~/styles/core.scss';
import type { ReactNode } from 'react';
import { MotionProvider } from '~/components/foundations/motion_provider';

interface LayoutProps {
  children: ReactNode;
}

const RootLayout = ({ children }: LayoutProps) => {
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
