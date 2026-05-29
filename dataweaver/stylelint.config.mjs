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

    // Use 3-character hex notation where possible (e.g. #ebc)
    'color-hex-length': 'short',

    // Omit units after '0' values where allowed (e.g. margin: 0)
    'length-zero-no-unit': true,

    // Prefer selector specificity over '!important'. Disable per-line with a
    // comment when overriding third-party styles is genuinely unavoidable
    'declaration-no-important': true,

    // Avoid ID selectors; prefer classes
    'selector-max-id': 0,

    // Don't qualify classes with a type selector (e.g. 'ul.example' ->
    // '.example'). Attribute-qualified type selectors (e.g. 'a[href]') are
    // still allowed, as used in the reset
    'selector-no-qualifying-type': [true, { ignore: ['attribute', 'id'] }],

    // Hyphen-delimited (kebab-case) class names
    'selector-class-pattern': [
      '^[a-z][a-z0-9]*(-[a-z0-9]+)*$',
      {
        message: 'Use hyphen-delimited, lowercase class names (e.g. video-id)',
      },
    ],
  },
};

export default STYLELINT_CONFIG;
