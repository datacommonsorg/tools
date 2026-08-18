import type { ComponentPropsWithRef } from 'react';
import { mergeClassNames } from '~/functions/merge_class_names';
import s from './status_indicator.module.scss';

interface IconStatusIndicatorProps extends ComponentPropsWithRef<'div'> {}

export const IconStatusIndicator = ({
  className,
  ...rest
}: IconStatusIndicatorProps) => {
  return (
    <div
      {...rest}
      aria-hidden="true"
      className={mergeClassNames(s.container, className)}
    />
  );
};
