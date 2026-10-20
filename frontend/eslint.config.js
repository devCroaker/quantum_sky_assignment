import js from '@eslint/js';
import prettierConfig from 'eslint-config-prettier';
import prettier from 'eslint-plugin-prettier';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  {
    // The generated wire types are not hand-written source. They are checked for
    // staleness instead, by `npm run types:check` and by generated-types.test.ts.
    ignores: ['dist', 'node_modules', 'src/api/types.ts'],
  },
  js.configs.recommended,
  {
    // Typed linting only where there is a TypeScript program to type against.
    files: ['**/*.{ts,tsx,mts}'],
    extends: [tseslint.configs.strictTypeChecked, prettierConfig],
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
      prettier,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],

      // CLAUDE.md forbids `any` and non-null assertions in TypeScript. Both are pinned
      // to errors here rather than left at whatever the preset happens to choose.
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-non-null-assertion': 'error',
      '@typescript-eslint/consistent-type-imports': 'error',

      // Formatting is enforced through lint rather than through a separate `format`
      // script, because the Makefile and CI call a fixed set of script names.
      'prettier/prettier': 'error',
    },
  },
  {
    // The type generator and this file are plain Node ESM, outside the TS program.
    files: ['scripts/**/*.mjs', 'eslint.config.js'],
    extends: [prettierConfig],
    languageOptions: {
      globals: { console: 'readonly', process: 'readonly' },
    },
    plugins: { prettier },
    rules: { 'prettier/prettier': 'error' },
  },
);
