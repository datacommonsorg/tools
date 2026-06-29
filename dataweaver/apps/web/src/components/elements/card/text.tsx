import type { CardState } from '~/components/elements/card/base';
import { Skeleton } from '~/components/elements/skeleton';
import { HtmlParsed } from '~/components/primitives/html_parsed';
import s from './text.module.scss';

export interface CardTextProps extends Pick<CardState, 'isLoading'> {
  title?: string;
  /** HTML string rendered via `html-react-parser` (sanitized/filtered). */
  body?: string;
  /** Callback fired when an internal `#hash` action link is clicked. */
  onAction?: (href: string) => void;
}

export const CardText = ({
  title,
  body,
  isLoading,
  onAction,
}: CardTextProps) => {
  return (
    <>
      {title && <h2 className={s.title}>{title}</h2>}

      {isLoading ? (
        <Skeleton />
      ) : body ? (
        <HtmlParsed html={body} onAction={onAction} className={s.body} />
      ) : null}
    </>
  );
};
