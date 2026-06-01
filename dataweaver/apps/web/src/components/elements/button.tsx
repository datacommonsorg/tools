import type { ComponentPropsWithRef, ComponentType } from 'react';
import { mergeClassNames } from '~/functions/merge_class_names';
import { mergeStyles } from '~/functions/merge_styles';
import s from './button.module.scss';

interface WithIconOnly {
  icon: ComponentType<ComponentPropsWithRef<'svg'>>;
  children?: never;
}

interface WithChildrenAndIcon {
  icon: ComponentType<ComponentPropsWithRef<'svg'>>;
  children: React.ReactNode;
}

interface ColorScheme {
  base: string;
  'base-hover': string;
  content: string;
  'content-hover': string;
}

type ButtonProps = {
  /** If left `undefined`, the button will use the default app color scheme. */
  colorScheme?: ColorScheme;
} & Omit<ComponentPropsWithRef<'button'>, 'children'> &
  (WithIconOnly | WithChildrenAndIcon);

export const Button = ({
  icon: Icon,
  children,
  colorScheme,
  ...rest
}: ButtonProps) => {
  const hasChildren = Boolean(children);
  const shape = hasChildren ? 'pill' : 'square';

  return (
    <button
      type="button"
      {...rest}
      className={mergeClassNames(s.container, rest.className)}
      data-shape={shape}
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
      <Icon className={s.icon} />

      {children && <span className={s.children}>{children}</span>}
    </button>
  );
};
