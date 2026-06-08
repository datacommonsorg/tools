import type { ComponentPropsWithRef, ComponentType } from 'react';
import { mergeClassNames } from '~/functions/merge_class_names';
import { mergeStyles } from '~/functions/merge_styles';
import s from './button.module.scss';

interface ColorScheme {
  base: string;
  'base-hover': string;
  content: string;
  'content-hover': string;
}

interface WithIconOnly {
  icon: ComponentType<ComponentPropsWithRef<'svg'>>;
  size: 'small' | 'medium' | 'large';
  'aria-label': string;
  children?: never;
}

interface WithChildrenAndOptionalIcon {
  children: React.ReactNode;
  size: 'small' | 'large';
  icon?: ComponentType<ComponentPropsWithRef<'svg'>>;
}

type ButtonProps = {
  /** If left `undefined`, the button will use the default app color scheme. */
  colorScheme?: ColorScheme;

  /** @default false */
  isDisabled?: boolean;
} & Omit<ComponentPropsWithRef<'button'>, 'disabled' | 'children'> &
  (WithIconOnly | WithChildrenAndOptionalIcon);

export const Button = ({
  icon: Icon,
  children,
  size,
  colorScheme,
  isDisabled = false,
  ...rest
}: ButtonProps) => {
  const hasChildren = Boolean(children);
  const shape = hasChildren ? 'pill' : 'circle';

  return (
    <button
      type="button"
      {...rest}
      className={mergeClassNames(s.container, rest.className)}
      data-shape={shape}
      data-size={size}
      data-has-icon={Icon !== undefined}
      disabled={isDisabled}
      style={mergeStyles(
        colorScheme && {
          '--color-button-base': colorScheme.base,
          '--color-button-base-hover': colorScheme['base-hover'],
          '--color-button-content': colorScheme.content,
          '--color-button-content-hover': colorScheme['content-hover'],
        },
        rest.style,
      )}
    >
      {Icon && <Icon className={s.icon} />}

      {children && <span className={s.children}>{children}</span>}
    </button>
  );
};
