'use client';

import { type TLShapeId, useEditor } from 'tldraw';
import { Button } from '~/components/elements/button';
import { Card } from '~/components/elements/card';
import type { CardState } from '~/components/elements/card/base';
import { Skeleton } from '~/components/elements/skeleton';
import { IconDelete } from '~/components/primitives/icons/delete';
import { IconExport } from '~/components/primitives/icons/export';
import { IconPencil } from '~/components/primitives/icons/pencil';
import { useExportActions } from '~/components/scopes/atlas/export_provider';
import { useQueryActions } from '~/components/scopes/atlas/query_provider';
import s from './text.module.scss';

export interface CardTextProps extends CardState {
  id: TLShapeId;
  title?: string;
  body?: string;
  followUp?: string;
}

export const CardText = ({
  id,
  isLoading,
  selection,
  title,
  body,
  followUp,
}: CardTextProps) => {
  const editor = useEditor();

  const { open: openExport } = useExportActions();
  const { runPrompt } = useQueryActions();

  return (
    <Card.Base
      isLoading={isLoading}
      selection={selection}
      actions={[
        {
          icon: IconExport,
          label: 'Export',
          isDisabled: isLoading,
          onClick: () => {
            editor.select(id);
            openExport();
          },
        },
        {
          icon: IconDelete,
          label: 'Delete',
          onClick: () => editor.deleteShapes([id]),
        },
      ]}
    >
      <div className={s.container}>
        {title && <h2 className={s.title}>{title}</h2>}

        {isLoading ? (
          <Skeleton />
        ) : (
          body && <div className={s.body}>{body}</div>
        )}
      </div>

      {followUp && !isLoading && (
        <Card.Footer>
          <Button
            size="small"
            variant="flat"
            tone="accent-subtle"
            icon={IconPencil}
            onPointerDown={(event) => event.stopPropagation()}
            onClick={() => runPrompt(followUp)}
          >
            {followUp}
          </Button>
        </Card.Footer>
      )}
    </Card.Base>
  );
};
