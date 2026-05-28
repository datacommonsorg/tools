'use client';

import dynamic from 'next/dynamic';

const Tldraw = dynamic(
	() => import('./tldraw').then((module) => module.Tldraw),
	{ ssr: false },
);

export const PageHome = () => {
	return <Tldraw />;
};
