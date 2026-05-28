/** @type {import('stylelint').Config} */

const STYLELINT_CONFIG = {
	extends: [
		// Base rules. Note: This installs and uses 'postcss-scs' out of the box
		'stylelint-config-standard-scss',

		// CSS modules syntax support
		'stylelint-config-css-modules',

		// Enforce a logical order for CSS properties
		'stylelint-config-recess-order',
	],

	plugins: [
		// Block ignored properties in CSS
		'stylelint-declaration-block-no-ignored-properties',

		// Prettier integration
		'stylelint-prettier',
	],

	rules: {
		// Enable prettier (inherits config from .prettierrc.json)
		'prettier/prettier': true,

		// Enable plugin
		'plugin/declaration-block-no-ignored-properties': true,

		// Ignore select properties in the redundant longhand properties rule
		'declaration-block-no-redundant-longhand-properties': [
			true,
			{ ignoreShorthands: ['/flex/', '/grid/'] },
		],

		// Prevent redundant nesting selectors
		'scss/selector-no-redundant-nesting-selector': true,

		// Ignore position declarations inside '@supports' rules - it was causing
		// issues that IMO weren't valid concerns
		'no-invalid-position-declaration': [true, { ignoreAtRules: ['supports'] }],

		// Disable some default rules
		'selector-id-pattern': null,
		'selector-class-pattern': null,
		'scss/operator-no-newline-after': null,
	},
};

export default STYLELINT_CONFIG;
