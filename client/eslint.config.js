import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import importPlugin from 'eslint-plugin-import'
import unusedImports from 'eslint-plugin-unused-imports'
import prettierPlugin from 'eslint-plugin-prettier'
import reactPlugin from 'eslint-plugin-react'

export default tseslint.config(
  { ignores: ['dist'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
      parserOptions: {
        ecmaFeatures: {
          jsx: true
        }
      }
    },
    plugins: {
      'react': reactPlugin,
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
      'import': importPlugin,
      'unused-imports': unusedImports,
      'prettier': prettierPlugin
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': [
        'warn',
        { allowConstantExport: true },
      ],
      '@typescript-eslint/no-empty-function': ['error', { 'allow': ['arrowFunctions'] }],
      '@typescript-eslint/no-empty-interface': ['error', { 'allowSingleExtends': true }],
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-redeclare': 'error',
      '@typescript-eslint/no-unused-vars': 'off',
      'curly': 'error',
      'no-console': 'error',
      'no-empty-function': 'off',
      'no-redeclare': 'off',
      'no-undef': 'off',
      'no-unused-vars': 'off',
      'unused-imports/no-unused-imports': 'error',
      'unused-imports/no-unused-vars': [
        'error',
        {
          'vars': 'all',
          'varsIgnorePattern': '^',
          'args': 'after-used',
          'argsIgnorePattern': '^'
        }
      ],
      'import/order': [
        'error',
        {
          'newlines-between': 'always',
          'alphabetize': {
            'order': 'asc',
            'caseInsensitive': true
          },
          'pathGroups': [
            {
              'pattern': '@/**',
              'group': 'external',
              'position': 'after'
            }
          ]
        }
      ],
      'react-hooks/exhaustive-deps': 'error',
      'react/jsx-no-bind': 'error',
      'prettier/prettier': 'error',
      'react/jsx-uses-react': 'error',
      'react/jsx-uses-vars': 'error'
    },
  },
  {
    files: ['src/components/**/*', 'src/screens/**/*', 'src/hasura/cache/keys.ts'],
    rules: {
      'no-console': 'off'
    }
  }
)
