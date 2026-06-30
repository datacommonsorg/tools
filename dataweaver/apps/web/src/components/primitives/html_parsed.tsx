import DOMPurify from 'dompurify';
import type { DOMNode } from 'html-react-parser';
import parse, { domToReact, Element } from 'html-react-parser';
import { type ComponentPropsWithRef, useMemo } from 'react';
import { Link } from '~/components/primitives/link';

/** List of disallowed tags for HTML parsing. All other tags will be allowed. */
const FORBID_TAGS: string[] = ['style'] as const;

interface HtmlParsedProps extends ComponentPropsWithRef<'div'> {
  html: string;
  onAction: (href: string) => void;
}

export const HtmlParsed = ({ html, onAction, ...rest }: HtmlParsedProps) => {
  const parsedHtml = useMemo(() => {
    return parse(DOMPurify.sanitize(html, { FORBID_TAGS }), {
      replace: (domNode) => {
        if (domNode instanceof Element) {
          switch (domNode.name) {
            case 'a': {
              const { href } = domNode.attribs;
              const isAction = href && href.startsWith('#fetch');
              const isExternal = href ? /^https?:\/\//i.test(href) : false;
              const children = domToReact(domNode.children as DOMNode[]);

              // Only allow action links and absolute http(s) links
              if (!href || (!isAction && !isExternal)) return children;

              // Internal action links — use button with callback instead
              if (isAction) {
                return (
                  <button
                    type="button"
                    onPointerDown={(event) => event.stopPropagation()}
                    onClick={() => onAction(href)}
                  >
                    {children}
                  </button>
                );
              }

              return (
                <Link href={href} isExternal={isExternal}>
                  {children}
                </Link>
              );
            }
          }
        }
      },
    });
  }, [html, onAction]);

  return <div {...rest}>{parsedHtml}</div>;
};
