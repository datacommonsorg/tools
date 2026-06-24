import DOMPurify from 'dompurify';
import type { DOMNode } from 'html-react-parser';
import parse, { domToReact, Element } from 'html-react-parser';
import Link from 'next/link';
import { useMemo } from 'react';
import { validateHref } from '~/functions/validate_href';

export const HtmlParsed = ({
  html,
  onAction,
  className,
}: {
  html: string;
  onAction?: (href: string) => void;
  className?: string;
}) => {
  DOMPurify.setConfig({ FORBID_TAGS: ['style'] });

  const parsedHtml = useMemo(
    () =>
      html
        ? parse(DOMPurify.sanitize(html), {
            replace: (domNode) => {
              if (domNode instanceof Element) {
                switch (domNode.name) {
                  case 'a': {
                    const validLink = validateHref(domNode.attribs.href);
                    if (!validLink) {
                      return <>{domToReact(domNode.children as DOMNode[])}</>;
                    }

                    const { href, target, rel } = validLink;

                    // Internal action links — fire callback instead of navigating.
                    if (href.startsWith('#fetch') && onAction) {
                      return (
                        <Link
                          href={href}
                          onPointerDown={(e) => e.stopPropagation()}
                          onClick={(e) => {
                            e.preventDefault();
                            onAction(href);
                          }}
                        >
                          {domToReact(domNode.children as DOMNode[])}
                        </Link>
                      );
                    }

                    return (
                      <Link href={href} target={target} rel={rel}>
                        {domToReact(domNode.children as DOMNode[])}
                      </Link>
                    );
                  }
                }
              }
            },
          })
        : null,
    [html, onAction],
  );

  return <div className={className}>{parsedHtml}</div>;
};
