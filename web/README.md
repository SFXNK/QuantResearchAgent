# QRA Monitor (SPA)

React + Vite dashboard for QuantResearchAgent: data capture, research runs, and surviving strategies.

## Dev

Terminal 1 — API:

```bash
uv run qra dashboard --db runs/quant_research_agent.sqlite --data-root data/raw
```

Terminal 2 — UI (proxies `/api` → `:8000`):

```bash
cd web
npm install
npm run dev
```

Open http://127.0.0.1:5173

## Actions (from the UI)

- **Data Capture**: start OKX recording (short/long), delete datasets/segments
- **Runs**: start research (synthetic or crypto_l2), delete runs
- **Survivors**: mark/unmark, delete evaluations
- **Jobs**: poll background jobs, cancel in-flight capture/research

## Production (served by FastAPI)

```bash
cd web && npm install && npm run build
uv run qra dashboard --web-dir web/dist
```

Open http://127.0.0.1:8000
