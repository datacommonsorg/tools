import type { ReactNode } from 'react';
import s from './footer.module.scss';

interface CardFooterProps {
  title?: ReactNode;
  children: ReactNode;
}

export const CardFooter = ({ title, children }: CardFooterProps) => {
  return (
    <footer className={s.container}>
      {title && <h3 className={s.title}>{title}</h3>}
      <div className={s.items}>{children}</div>
    </footer>
  );
};
