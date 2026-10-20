/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "fixture" or "live". See frontend/README.md. Absent means fixture. */
  readonly VITE_DATA_SOURCE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
