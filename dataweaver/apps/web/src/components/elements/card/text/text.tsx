import { Skeleton } from './skeleton';
import s from './text.module.scss';

/** Skeleton line widths (% of the body) mirroring the loading design. */
const SKELETON_LINE_WIDTHS = [100, 84, 92, 72];

interface CardTextProps {
  title?: string;
  body?: string;

  /**
   * Renders skeleton lines in place of the body while content loads.
   *
   * @default false
   */
  isLoading?: boolean;
}

export const CardText = ({ title, body, isLoading = false }: CardTextProps) => {
  return (
    <>
      {title && <h2 className={s.title}>{title}</h2>}

      {isLoading && <Skeleton widths={SKELETON_LINE_WIDTHS} />}

      {body && <div className={s.body}>{body}</div>}
    </>
  );
};
