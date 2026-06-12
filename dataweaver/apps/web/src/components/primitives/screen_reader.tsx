import type { ComponentPropsWithRef, ElementType } from 'react';
import s from './screen_reader.module.scss';

type ScreenReaderOnlyProps<TElement extends ElementType = 'span'> = {
  element?: TElement;
} & DistributiveOmit<
  WithRequired<ComponentPropsWithRef<TElement>, 'children'>,
  'className'
>;

export const ScreenReaderOnly = <TElement extends ElementType = 'span'>({
  element,
  children,
  ...rest
}: ScreenReaderOnlyProps<TElement>) => {
  const Container = element ?? 'span';

  return (
    <Container className={s['screen-reader-only']} {...rest}>
      {children}
    </Container>
  );
};
