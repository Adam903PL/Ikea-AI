declare module "occt-import-js" {
  type OcctImportFactory = (options?: {
    locateFile?: (path: string) => string;
  }) => Promise<unknown>;

  const occtimportjs: OcctImportFactory;

  export default occtimportjs;
}

declare module "*.wasm" {
  const wasmUrl: string;
  export default wasmUrl;
}
