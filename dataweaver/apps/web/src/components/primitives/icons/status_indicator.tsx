import type { ComponentPropsWithRef } from 'react';
import { mergeClassNames } from '~/functions/merge_class_names';
import s from './status_indicator.module.scss';

type StatusIndicatorProps = ComponentPropsWithRef<'div'>;

export const IconStatusIndicator = ({
  className,
  ...rest
}: StatusIndicatorProps) => {
  return <div {...rest} className={mergeClassNames(s.container, className)} />;
};
