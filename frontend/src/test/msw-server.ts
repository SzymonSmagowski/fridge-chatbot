/**
 * Node MSW server. Default handler set is empty; each test (or test file via
 * a shared module) registers `server.use(...)` with the handlers it needs.
 *
 * Shared canned handlers live in `msw-handlers.ts` — they encode Architect §5
 * response shapes verbatim so tests don't drift from the contract.
 */
import { setupServer } from "msw/node";

export const server = setupServer();
