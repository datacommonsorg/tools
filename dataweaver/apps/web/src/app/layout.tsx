import '~/styles/layers.css';
import '~/styles/core.scss';
import { domMax, LazyMotion } from 'motion/react';
import type { ReactNode } from 'react';

interface LayoutProps {
  children: ReactNode;
}

const RootLayout = ({ children }: LayoutProps) => {
  return (
    <html lang="en">
      <body>
        <LazyMotion strict features={domMax}>
          <main>{children}</main>
        </LazyMotion>
      </body>
    </html>
  );
};

export default RootLayout;
