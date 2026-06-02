/* ESLint config for the React + Vite frontend.
 * The react-hooks plugin is the important part — it catches Rules-of-Hooks
 * violations (e.g. a useMemo placed after a conditional return) at lint time. */
module.exports = {
  root: true,
  env: { browser: true, es2021: true, node: true },
  parserOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module',
    ecmaFeatures: { jsx: true },
  },
  settings: { react: { version: 'detect' } },
  extends: [
    'eslint:recommended',
    'plugin:react/recommended',
    'plugin:react/jsx-runtime',
    'plugin:react-hooks/recommended',
  ],
  rules: {
    // We don't use PropTypes in this codebase.
    'react/prop-types': 'off',
    // Intentional empty catch blocks (best-effort calls) are allowed.
    'no-empty': ['error', { allowEmptyCatch: true }],
    // Allow intentionally-unused args prefixed with _ and caught errors to be omitted.
    'no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
  },
  overrides: [
    {
      files: ['**/*.test.{js,jsx}', 'src/test/**'],
      globals: {
        describe: 'readonly',
        it: 'readonly',
        expect: 'readonly',
        vi: 'readonly',
        beforeEach: 'readonly',
        afterEach: 'readonly',
        beforeAll: 'readonly',
        afterAll: 'readonly',
      },
    },
  ],
  ignorePatterns: ['dist/', 'node_modules/'],
}
