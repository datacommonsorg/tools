'use client';

import dynamic from 'next/dynamic';

const Tldraw = dynamic(
  () => import('./tldraw').then((module) => module.Tldraw),
  { ssr: false },
);

interface PageHomeProps {
  licenseKey?: string;
}

export const PageHome = ({ licenseKey }: PageHomeProps) => {
  return <Tldraw licenseKey={licenseKey} />;
};
