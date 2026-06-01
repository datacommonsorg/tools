import type { ComponentPropsWithRef } from 'react';
import s from './screen_reader.module.scss';

type ScreenReaderOnlyProps = Omit<
  WithRequired<ComponentPropsWithRef<'span'>, 'children'>,
  'className'
>;

export const ScreenReaderOnly = ({
  children,
  ...rest
}: ScreenReaderOnlyProps) => {
  return (
    <span className={s.screenReaderOnly} {...rest}>
      {children}
    </span>
  );
};
