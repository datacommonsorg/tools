import { Button } from '~/components/elements/button';
import { IconExport } from '~/components/primitives/icons/export';
import s from './control.module.scss';

const BUTTON_EXPORT_COLOR_SCHEME = {
  base: 'var(--color-control-surface)',
  'base-hover': 'var(--color-control-surface-hover)',
  content: 'var(--color-control-accent)',
  'content-hover': 'var(--color-control-accent)',
};

interface ControlProps {
  id: string;
  isOpen: boolean;
  onToggle(): void;
}

export const Control = ({ id, isOpen, onToggle }: ControlProps) => {
  return (
    <Button
      className={s['button-export']}
      icon={IconExport}
      size="large"
      colorScheme={BUTTON_EXPORT_COLOR_SCHEME}
      aria-haspopup="dialog"
      aria-expanded={isOpen}
      aria-controls={id}
      onClick={onToggle}
    >
      Export
    </Button>
  );
};
