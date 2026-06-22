import { IconClose } from '~/components/primitives/icons/close';
import { Button } from './button';
import s from './tag.module.scss';

interface TagProps {
  label: string;
  onRemove: () => void;
}

export const Tag = ({ label, onRemove }: TagProps) => {
  return (
    <span className={s.container}>
      <span className={s.label}>{label}</span>
      <Button
        size="extra-small"
        variant="flat"
        tone="subtle"
        icon={IconClose}
        aria-label={`Remove ${label}`}
        onClick={onRemove}
      />
    </span>
  );
};
