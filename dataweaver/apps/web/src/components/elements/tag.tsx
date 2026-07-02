import s from './tag.module.scss';

interface TagProps {
  label: string;
}

export const Tag = ({ label }: TagProps) => {
  return (
    <span className={s.container}>
      <span className={s.label}>{label}</span>
    </span>
  );
};
