import type { ComponentPropsWithRef } from 'react';
import { mergeClassNames } from '~/functions/merge_class_names';
import s from './radio.module.scss';

type RadioProps = Omit<ComponentPropsWithRef<'input'>, 'type'>;

export const Radio = ({ children, className, ...rest }: RadioProps) => {
  return (
    <label className={mergeClassNames(s.container, className)}>
      <input className={s.input} type="radio" {...rest} />
      <span className={s.indicator} aria-hidden="true" />
      {children}
    </label>
  );
};
