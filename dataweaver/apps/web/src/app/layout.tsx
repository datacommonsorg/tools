import '~/styles/layers.css';
import '~/styles/core.scss';
import type { ReactNode } from 'react';
import { MotionProvider } from '~/components/foundations/motion_provider';

const FONT_URL =
  'https://fonts.googleapis.com/css?family=Google+Sans:400,500,700&display=swap&lang=en';

interface RootLayoutProps {
  children: ReactNode;
}

const RootLayout = ({ children }: RootLayoutProps) => {
  return (
    <html lang="en">
      <head>
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com/"
          crossOrigin="anonymous"
        />
        <link rel="preload" as="font" href={FONT_URL} crossOrigin="anonymous" />
        <link href={FONT_URL} rel="stylesheet" />
      </head>
      <body>
        <MotionProvider>
          <main>{children}</main>
        </MotionProvider>
      </body>
    </html>
  );
};

export default RootLayout;
