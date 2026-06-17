import type { DOMNode } from 'html-react-parser';
import parse, { domToReact, Element } from 'html-react-parser';
import Link from 'next/link';
import { useMemo } from 'react';
import type { CardState } from '~/components/elements/card/base';
import { Skeleton } from '~/components/elements/skeleton';
import s from './text.module.scss';

export interface CardTextProps extends Pick<CardState, 'isLoading'> {
  title?: string;
  /** HTML string rendered via dangerouslySetInnerHTML. */
  body?: string;
}

export const CardText = ({ title, body, isLoading }: CardTextProps) => {
  const parsedHtml = useMemo(
    () =>
      body
        ? parse(body, {
            replace: (domNode) => {
              if (domNode instanceof Element) {
                switch (domNode.name) {
                  case 'a':
                    return (
                      <Link
                        href={domNode.attribs.href ?? '#'}
                        target={domNode.attribs.target}
                      >
                        {domToReact(domNode.children as DOMNode[])}
                      </Link>
                    );
                  case 'hr':
                    return (
                      <hr
                        key={
                          'startIndex' in domNode
                            ? domNode.startIndex
                            : undefined
                        }
                      />
                    );
                }
              }
            },
          })
        : null,
    [body],
  );

  return (
    <>
      {title && <h2 className={s.title}>{title}</h2>}

      {isLoading ? (
        <Skeleton />
      ) : (
        parsedHtml && <div className={s.body}>{parsedHtml}</div>
      )}
    </>
  );
};
