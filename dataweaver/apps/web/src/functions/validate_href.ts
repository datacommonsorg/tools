interface ValidLinkProps {
  href: string;
  target?: string;
  rel?: string;
}

export const validate_href = (href?: string): ValidLinkProps | false  => {
  if (!href) return false;

  const isHash = href.startsWith('#');
  const isHttp = /^https?:\/\//i.test(href);

  if (!isHash && !isHttp) {
    return false;
  }

  return {
    href,
    target: isHttp ? '_blank' : undefined,
    rel: isHttp ? 'noopener noreferrer' : undefined,
  };
}