import { ScreenReaderOnly } from '~/components/primitives/screen_reader';
import s from './skeleton.module.scss';

interface SkeletonProps {
  /** One line per entry; each value is the line's width as a % of the row. */
  widths: number[];

  /** Announced to assistive tech while content loads. @default 'Loading…' */
  label?: string;
}

/** Animated placeholder lines shown in place of content while it loads. */
export const Skeleton = ({ widths, label = 'Loading…' }: SkeletonProps) => {
  return (
    <div className={s.container} role="status">
      {widths.map((width, index) => (
        <span
          key={index}
          className={s.line}
          style={{
            width: `${width}%`,
            animationDelay: index === 0 ? undefined : `${index * 0.15}s`,
          }}
        />
      ))}

      <ScreenReaderOnly>{label}</ScreenReaderOnly>
    </div>
  );
};
