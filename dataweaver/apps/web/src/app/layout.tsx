import '~/styles/layers.css';
import '~/styles/core.scss';
import { domMax, LazyMotion } from 'motion/react';
import type { ReactNode } from 'react';

type Props = {
	children: ReactNode;
};

const RootLayout = ({ children }: Props) => {
	return (
		<html lang="en">
			<body>
				<LazyMotion strict features={domMax}>
					<main>{children}</main>
				</LazyMotion>
			</body>
		</html>
	);
};

export default RootLayout;
