import type { ReactNode } from 'react';
import s from './footer.module.scss';

interface CardFooterProps {
  children: ReactNode;
}

export const CardFooter = ({ children }: CardFooterProps) => {
  return <footer className={s.container}>{children}</footer>;
};
