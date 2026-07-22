import { Button } from '~/components/elements/button';
import { IconImport } from '~/components/primitives/icons/import';
import s from './control.module.scss';

interface ControlProps {
  id: string;
  isOpen: boolean;
  onToggle(): void;
}

export const Control = ({ id, isOpen, onToggle }: ControlProps) => {
  return (
    <Button
      className={s['button-import']}
      icon={IconImport}
      size="large"
      variant="flat"
      tone="control"
      aria-haspopup="dialog"
      aria-expanded={isOpen}
      aria-controls={id}
      onClick={onToggle}
    >
      Import
    </Button>
  );
};
