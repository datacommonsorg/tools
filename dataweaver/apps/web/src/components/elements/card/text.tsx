'use client';

import { useRef } from 'react';
import { type TLShapeId, useEditor } from 'tldraw';
import { Button } from '~/components/elements/button';
import { Card } from '~/components/elements/card';
import type { CardState } from '~/components/elements/card/base';
import { useCardAutoHeight } from '~/components/elements/card/use_card_auto_height';
import { Skeleton } from '~/components/elements/skeleton';
import { HtmlParsed } from '~/components/primitives/html_parsed';
import { IconDelete } from '~/components/primitives/icons/delete';
import { IconExport } from '~/components/primitives/icons/export';
import { IconPencil } from '~/components/primitives/icons/pencil';
import { CARD_VARIANT_SIZE_DEFAULT } from '~/components/scopes/atlas/config';
import { useExportActions } from '~/components/scopes/atlas/export_provider';
import { useQueryActions } from '~/components/scopes/atlas/query_provider';
import { useAtlasStore } from '~/store';
import s from './text.module.scss';

/**
 * Tags we provide styles for in `text.module.scss`. Anything else is stripped
 * during sanitization. (`tr`/`thead`/`tbody` are unstyled but required for the
 * styled `table`/`th`/`td` to render correctly.)
 */
const ALLOWED_BODY_TAGS: string[] = [
  'h3',
  'p',
  'ul',
  'li',
  'a',
  'strong',
  'table',
  'thead',
  'tbody',
  'tr',
  'th',
  'td',
  'br',
] as const;

export interface CardTextProps extends CardState {
  id: TLShapeId;
  title?: string;

  /** HTML string rendered via `html-react-parser` (sanitized/filtered). */
  body?: string;
  relatedQuery?: string;
}

export const CardText = ({
  id,
  isLoading,
  selection,
  title,
  body,
  relatedQuery,
}: CardTextProps) => {
  const editor = useEditor();

  const { cardRegisterChart } = useAtlasStore.getState();
  const { open: openExport } = useExportActions();
  const { runPrompt } = useQueryActions();

  const containerRef = useRef<HTMLDivElement>(null);
  const contentContainerRef = useRef<HTMLDivElement>(null);

  useCardAutoHeight(
    id,
    containerRef,
    contentContainerRef,
    CARD_VARIANT_SIZE_DEFAULT.text.h,
  );

  return (
    <Card.Base
      id={id}
      childrenContainerRef={containerRef}
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
      <Card.Content
        contentContainerRef={contentContainerRef}
        title={title && <h2 className={s.title}>{title}</h2>}
      >
        {isLoading && !body && <Skeleton />}

        {body && (
          <HtmlParsed
            className={s.body}
            html={body}
            allowedTags={ALLOWED_BODY_TAGS}
            // For now we only support actions that are formatted as a href via
            // '#fetch=VARIABLE&place=PLACE'. Rework if we support more actions
            onAction={(href) => {
              const hrefWithoutHash = href.replace(/^#/, '');
              const params = new URLSearchParams(hrefWithoutHash);
              const variableDcid = params.get('fetch');
              const placeDcid = params.get('place');
              if (!variableDcid || !placeDcid) return;

              cardRegisterChart(id, placeDcid, variableDcid);
            }}
          />
        )}

        {relatedQuery && !isLoading && (
          <Card.Footer>
            <Button
              size="small"
              variant="flat"
              tone="accent-subtle"
              icon={IconPencil}
              onPointerDown={(event) => event.stopPropagation()}
              onClick={() => runPrompt(relatedQuery)}
            >
              {relatedQuery}
            </Button>
          </Card.Footer>
        )}
      </Card.Content>
    </Card.Base>
  );
};
