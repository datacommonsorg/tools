import type { ComponentPropsWithRef, ComponentType, ReactNode } from 'react';
import { useEditor, useValue } from 'tldraw';
import { IconSelect } from '~/components/primitives/icons/select';
import { IconShapes } from '~/components/primitives/icons/shapes';
import { IS_APPLE } from '~/configs/environment_client';
import { EXPORT_OPTIONS } from './options';
import s from './status_empty.module.scss';

type IconComponent = ComponentType<ComponentPropsWithRef<'svg'>>;

interface CardProps {
  icon: IconComponent;
  title: string;
  description: string;
  children?: ReactNode;
}

const Card = ({ icon: Icon, title, description, children }: CardProps) => {
  return (
    <div className={s['card-container']} role="status">
      <Icon className={s['icon-status']} />
      <p className={s['card-title']}>{title}</p>
      <p className={s['card-description']}>{description}</p>
      {children}
    </div>
  );
};

export const StatusEmpty = () => {
  const editor = useEditor();

  const totalCards = useValue('atlas-card-count', () => {
    return editor
      .getCurrentPageShapes()
      .filter((shape) => shape.type === 'card').length;
  }, [editor]);

  const selectAllCards = () => {
    const cardIds = editor
      .getCurrentPageShapes()
      .filter((shape) => shape.type === 'card')
      .map((shape) => shape.id);
    editor.select(...cardIds);
  };

  return (
    <>
      {totalCards === 0 ? (
        <Card
          icon={IconShapes}
          title="No active cards"
          description="Ask a question to generate charts and structured data on the canvas. Once cards are added, select items to export."
        />
      ) : (
        <Card
          icon={IconSelect}
          title="No cards selected"
          description="Please select 1 or more cards to see options."
        >
          <button
            type="button"
            className={s['button-select-all']}
            onClick={selectAllCards}
          >
            <span className={s['select-all-label']}>Select All</span>
            <span className={s['select-all-keys']}>
              {IS_APPLE ? 'Cmd + A' : 'Ctrl + A'}
            </span>
          </button>
        </Card>
      )}

      <section className={s['preview-container']} aria-label="Export options">
        <h3 className={s['preview-title']}>Export options</h3>

        <ul className={s['options-container']}>
          {EXPORT_OPTIONS.map((option) => (
            <li key={option.title} className={s['option-container']}>
              <h4 className={s['option-title']}>{option.title}</h4>
              <p className={s['option-description']}>{option.description}</p>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
};
