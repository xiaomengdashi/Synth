/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_SHARE_SHORTCUT_ICLOUD_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
