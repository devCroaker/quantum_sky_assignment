/**
 * Types for generate-types.mjs, which is plain Node ESM and outside the TypeScript
 * program. Only the pieces the staleness test needs are declared.
 */
export declare const schemaPath: string;
export declare const outputPath: string;
export declare function renderTypes(): Promise<string>;
