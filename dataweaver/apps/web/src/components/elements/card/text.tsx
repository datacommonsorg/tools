import type { CardState } from '~/components/elements/card/base';
import { Skeleton } from '~/components/elements/skeleton';
import s from './text.module.scss';

export interface CardTextProps extends Pick<CardState, 'isLoading'> {
  title?: string;
  body?: string;
}

export const CardText = ({ title, body, isLoading }: CardTextProps) => {
  return (
    <>
      {title && <h2 className={s.title}>{title}</h2>}

      {isLoading ? <Skeleton /> : body && <div className={s.body}>{body}</div>}
    </>
  );
};
