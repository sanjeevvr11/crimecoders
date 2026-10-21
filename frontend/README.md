# Trace360 frontend

React + Vite + TypeScript. A functional UI for understanding the project, built so it can be
replaced by a redesigned UI without touching the backend.

```
src/api/         KEEP     generated types (schema.gen.ts), aliases (types.ts), client (client.ts)
src/hooks/       KEEP     useLeads(), useAccount(id), … → { data, error, loading, reload }
src/pages/       REPLACE  screens: Overview, Leads, Account, Network, Complaints, Models
src/components/  REPLACE  presentational pieces (tables, charts, graph, badges)
```

```bash
npm install
npm run dev        # http://localhost:5173, /api proxied to http://localhost:8000
npm run build      # typecheck + production build into dist/
npm run gen:api    # regenerate src/api/schema.gen.ts from ../docs/openapi.json
npm run check:api  # fail if the generated types differ from the committed ones
```

Full guide for redesigning the UI: [../docs/FRONTEND_INTEGRATION.md](../docs/FRONTEND_INTEGRATION.md).
