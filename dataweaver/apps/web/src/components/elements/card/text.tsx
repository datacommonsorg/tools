import type { DOMNode } from 'html-react-parser';
import parse, { domToReact, Element } from 'html-react-parser';
import Link from 'next/link';
import { useMemo } from 'react';
import type { CardState } from '~/components/elements/card/base';
import { Skeleton } from '~/components/elements/skeleton';
import { validate_href } from '~/functions/validate_href';
import s from './text.module.scss';

export interface CardTextProps extends Pick<CardState, 'isLoading'> {
  title?: string;
  /** HTML string rendered via `html-react-parser` (sanitized/filtered). */
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
                  case 'script':
                  case 'style':
                  case 'iframe':
                    return null;
                  case 'a': {
                    const validLink = validate_href(domNode.attribs.href);
                    if (!validLink) {
                      return <>{domToReact(domNode.children as DOMNode[])}</>;
                    }

                    const { href, target, rel } = validLink;

                    return (
                      <Link href={href} target={target} rel={rel}>
                        {domToReact(domNode.children as DOMNode[])}
                      </Link>
                    );
                  }
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
