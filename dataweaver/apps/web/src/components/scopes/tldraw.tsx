'use client';

import { Tldraw as PrimitiveTldraw } from 'tldraw';
import s from './tldraw.module.scss';

export const Tldraw = () => {
	return <PrimitiveTldraw className={s.canvas} hideUi />;
};
