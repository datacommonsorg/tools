import type { LinkProps } from 'next/link';
import NextLink from 'next/link';
import type { ComponentPropsWithRef, Ref } from 'react';

type Props = {
	ref?: Ref<HTMLAnchorElement>;
	href: string | undefined;

	/** @default false */
	isExternal?: boolean;
} & ComponentPropsWithRef<'a'> &
	Pick<LinkProps, 'replace'>;

export const Link = ({
	ref,
	href,
	isExternal = false,
	replace,
	children,
	...rest
}: Props) => {
	// If theres no 'href' render this without it (this is equivalent to a span)
	if (!href) {
		return (
			<a ref={ref} {...rest}>
				{children}
			</a>
		);
	}

	// If external link, render standard anchor (open in new tab)
	if (isExternal) {
		return (
			<a
				ref={ref}
				href={href}
				target="_blank"
				rel="noopener noreferrer"
				{...rest}
			>
				{children}
			</a>
		);
	}

	// If internal link, render Next/Link
	return (
		<NextLink ref={ref} href={href} scroll={false} replace={replace} {...rest}>
			{children}
		</NextLink>
	);
};
