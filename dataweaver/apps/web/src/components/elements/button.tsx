import type { ComponentPropsWithRef, ComponentType } from 'react';
import { mergeClassNames } from '~/functions/merge_class_names';
import { mergeStyles } from '~/functions/merge_styles';
import s from './button.module.scss';

// Note: Here '(string & {})' is a trick to allow any string while still
// supporting 'transparent' as a distinct type
type Color = 'transparent' | (string & {});

interface ColorScheme {
  base: Color;
  'base-hover': Color;
  content: Color;
  'content-hover': Color;
}

/**
 * In the CSS we map all colors via `rgb(var(--foo))`. This means that we need
 * to convert `transparent` to a 'real' value to avoid passing invalid
 * `rgb(transparent)`. Instead mapped to `rgb(0 0 0 / 0%)` which is effectively
 * the same thing but valid CSS.
 */
const mapColor = (color: Color) => {
  return color === 'transparent' ? `0 0 0 / 0%` : color;
};

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
          '--color-button-base': mapColor(colorScheme.base),
          '--color-button-base-hover': mapColor(colorScheme['base-hover']),
          '--color-button-content': mapColor(colorScheme.content),
          '--color-button-content-hover': mapColor(
            colorScheme['content-hover'],
          ),
        },
        rest.style,
      )}
    >
      {Icon && <Icon className={s.icon} />}

      {children && <span className={s.children}>{children}</span>}
    </button>
  );
};
