import { Button } from '~/components/elements/button';
import { IconExport } from '~/components/primitives/icons/export';
import s from './control.module.scss';

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
      variant="flat"
      tone="control"
      aria-haspopup="dialog"
      aria-expanded={isOpen}
      aria-controls={id}
      onClick={onToggle}
    >
      Export
    </Button>
  );
};
