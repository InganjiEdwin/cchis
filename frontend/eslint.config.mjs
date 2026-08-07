import nextConfig from "eslint-config-next";

const config = [
  ...nextConfig,
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "coverage/**",
      "dist/**",
      "build/**",
      "test-artifacts/**",
      "tsconfig.tsbuildinfo",
    ],
    rules: {
      // The application is React 18; these React Compiler rules are emitted by
      // the patched Next 16 preset but are not applicable to this codebase yet.
      "react-hooks/static-components": "off",
      "react-hooks/set-state-in-effect": "off",
      "react-hooks/purity": "off",
      "react-hooks/preserve-manual-memoization": "off",
    },
  },
];

export default config;
