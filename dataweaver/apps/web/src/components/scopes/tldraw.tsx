'use client';

import { Tldraw as PrimitiveTldraw } from 'tldraw';
import s from './tldraw.module.scss';

interface TldrawProps {
  licenseKey?: string;
}

export const Tldraw = ({ licenseKey }: TldrawProps) => {
  return <PrimitiveTldraw className={s.canvas} hideUi licenseKey={licenseKey} />;
};
