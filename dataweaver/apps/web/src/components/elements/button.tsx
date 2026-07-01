import type { ComponentPropsWithRef, ComponentType, ReactNode } from 'react';
import { mergeClassNames } from '~/functions/merge_class_names';
import s from './button.module.scss';

/** These are the main button styles - unique based on the button's purpose. */
interface WithInternalTones {
  variant: 'flat' | 'border';
  tone:
    | 'prominent'
    | 'subtle'
    | 'subtle-highlight'
    | 'accent'
    | 'accent-subtle';
}

/** These inherit from the parent element based on use case. */
interface WithExternalTones {
  variant: 'flat';
  tone: 'control' | 'card-action';
}

interface WithIconOnly {
  icon: ComponentType<ComponentPropsWithRef<'svg'>>;
  size: 'extra-small' | 'small' | 'medium' | 'large';
  'aria-label': string;
  children?: never;
}

interface WithChildrenAndOptionalIcon {
  children: ReactNode;
  size: 'small' | 'medium' | 'large';
  icon?: ComponentType<ComponentPropsWithRef<'svg'>>;
}

type ButtonProps = {
  /** @default false */
  isDisabled?: boolean;
} & Omit<ComponentPropsWithRef<'button'>, 'disabled' | 'children'> &
  (WithInternalTones | WithExternalTones) &
  (WithIconOnly | WithChildrenAndOptionalIcon);

export const Button = ({
  icon: Icon,
  children,
  size,
  variant,
  tone,
  isDisabled = false,
  ...rest
}: ButtonProps) => {
  const hasChildren = Boolean(children);
  const shape = hasChildren ? 'pill' : 'circle';

  // Icon-only buttons have no visible label, so surface their required
  // `aria-label` as a native tooltip (unless an explicit `title` is provided)
  const title = rest.title ?? (!hasChildren ? rest['aria-label'] : undefined);
  return (
    <button
      type="button"
      {...rest}
      title={title}
      className={mergeClassNames(s.container, rest.className)}
      data-shape={shape}
      data-size={size}
      data-variant={variant}
      data-tone={tone}
      data-has-icon={Icon !== undefined}
      disabled={isDisabled}
    >
      {Icon && <Icon className={s.icon} />}

      {children && <span className={s.children}>{children}</span>}
    </button>
  );
};
