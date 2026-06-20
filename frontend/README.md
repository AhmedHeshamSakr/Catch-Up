# Catch-Up Console ("Signal")

The web console for the **Catch-Up** news intelligence agent. It is a read/write
control surface for the FastAPI backend: browse the latest digest runs, drill
into per-run news items, filter the news feed, and manage sources and the
watchlist.

Built with Next.js 16 (App Router), React 19, TypeScript (strict), Tailwind v4,
`@base-ui/react`, `next-themes`, and SWR. API responses are validated at the
boundary with zod (`lib/schemas.ts`).

## Prerequisites

- Node.js 20+ and npm
- The Catch-Up FastAPI backend running locally (see below) — the console has no
  data of its own; it talks to the backend API.

## Backend dependency

The console reads from and writes to the FastAPI backend. Start it from the
**repo root** (one level up from this directory):

```bash
uv run python -m app.cli serve
```

By default the backend listens on `http://localhost:8000`.

## Environment

`NEXT_PUBLIC_API_BASE` configures the backend URL **for two-port dev** (`next dev`
on :3000 talking to the backend on :8000). Copy the example for dev:

```bash
cp .env.local.example .env.local
```

```env
# .env.local — DEV ONLY
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

When **unset**, a `next dev` build defaults to `http://localhost:8000`, while a
**production / static-export build defaults to same-origin** (`""`) — which is how
the single-port desktop app serves the console and `/api` from one origin. Leave
`NEXT_PUBLIC_API_BASE` unset for the desktop build (the launcher builds with `""`).

## Getting started

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Scripts

| Command         | Description                                   |
| --------------- | --------------------------------------------- |
| `npm run dev`   | Start the dev server on port 3000             |
| `npm run build` | Production build                              |
| `npm start`     | Serve the production build                    |
| `npm test`      | Run the test suite (Vitest)                  |
| `npm run lint`  | Lint with ESLint                             |
