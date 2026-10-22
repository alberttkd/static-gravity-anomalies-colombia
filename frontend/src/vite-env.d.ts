/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_STATIC_MODE: string;
}

declare module "plotly.js-basic-dist-min";
