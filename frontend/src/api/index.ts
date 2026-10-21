/**
 * KEEP when replacing the UI: the backend contract.
 *   client.ts      one function per endpoint (the only code that calls fetch)
 *   types.ts       response types, aliases of the generated schema
 *   schema.gen.ts  GENERATED from docs/openapi.json by `npm run gen:api`; do not edit
 */
export { api, apiUrl, ApiError } from "./client";
export type * from "./types";
