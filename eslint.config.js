import globals from 'globals';

export default [
  {
    files: ['static/**/*.js'],
    ignores: ['static/app.test.js', 'static/test-setup.js'],
    languageOptions: {
      globals: {
        ...globals.browser,
        __TESTING__: 'readonly',
      },
    },
    rules: {
      'no-undef':       'error',
      'no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
      'semi':           ['error', 'always'],
    },
  },
];
