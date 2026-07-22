import type { ComponentPropsWithRef, ComponentType, ReactNode } from 'react';
import s from './card.module.scss';

type IconComponent = ComponentType<ComponentPropsWithRef<'svg'>>;

interface CardProps {
  icon: IconComponent;
  title: string;
  description: string;
  includeMaxWidth?: boolean;
  children?: ReactNode;
}

export const Card = ({
  icon: Icon,
  title,
  description,
  includeMaxWidth,
  children,
}: CardProps) => {
  return (
    <div
      className={s.container}
      role="status"
      data-has-max-width={includeMaxWidth}
    >
      <Icon className={s['icon-status']} />
      <p className={s.title}>{title}</p>
      <p className={s.description}>{description}</p>
      {children}
    </div>
  );
};
