import type { NextConfig } from 'next';

const NEXT_CONFIG: NextConfig = {
	reactStrictMode: true,
	reactCompiler: true,
	devIndicators: false,

	// Auto-inject the shared Sass includes (breakpoints, helpers, keyframes,
	// typography, z-indices, tokens) into every Sass entry module. Includes
	// only '@forwards' definitions, so this emits no CSS; it removes the need to
	// repeat `@use "~/styles/includes" as *;` at the top of each component file
	sassOptions: {
		additionalData: '@use "~/styles/includes" as *;\n',
	},

	compiler: {
		removeConsole:
			// Only allow the following console calls in production
			process.env.NODE_ENV === 'production'
				? { exclude: ['warn', 'error', 'info'] }
				: false,
	},

	images: {
		imageSizes: [384],
		deviceSizes: [768, 1280, 1600],
		qualities: [90],
		remotePatterns: [
			{
				protocol: 'https',
				hostname: 'fonts.googleapis.com',
				pathname: '/**',
			},
		],
	},
};

export default NEXT_CONFIG;
