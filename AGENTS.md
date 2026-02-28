# Agent Guidelines for Kalshi Edge Detection

This document provides guidelines for agentic coding agents working in this repository.

## Project Overview

This is a full-stack application with two main components:

- **edge_engine/** - Python backend (Flask API + edge detection engine)
- **frontend/** - React + TypeScript frontend (Vite)

Python 3.10+ required.

---

## Build, Lint, and Test Commands

### Frontend (React + TypeScript)

```bash
# Install dependencies
cd frontend && npm install

# Development server (hot reload)
npm run dev

# Production build
npm run build

# Lint (ESLint + TypeScript)
npm run lint

# Preview production build locally
npm run preview

# Run a single test file (if tests exist)
npx vitest run src/path/to/test-file.test.ts
```

### Backend (Python)

```bash
# Install dependencies
pip install -r requirements.txt

# Run the main edge detection engine
python -m edge_engine.main

# Run the API server (default port 5050)
python -m edge_engine.api_server
# Or specify port: python -m edge_engine.api_server 8080

# Run linters (install dev deps first)
pip install black mypy types-requests types-PyYAML
black --check edge_engine/
mypy edge_engine/

# Run tests (install pytest first)
pip install pytest pytest-cov
pytest                    # run all tests
pytest path/to/test.py    # run single test file
pytest -k test_name       # run tests matching name
pytest --cov=edge_engine  # with coverage
```

---

## Code Style Guidelines

### General

- Write code that matches the existing patterns in the codebase
- Prioritize clarity over cleverness
- Add type hints to all new Python functions (use `| None` syntax for Python 3.10+)
- Keep functions focused and small (under 50 lines preferred)
- Use early returns to reduce nesting

### Python (edge_engine)

**Imports**
- Group imports: standard library, third-party, local modules
- Use absolute imports: `from edge_engine.data import KalshiClient`
- Order alphabetically within groups

**Naming**
- `snake_case` for functions, variables, and module names
- `PascalCase` for classes
- `UPPER_SNAKE_CASE` for constants

**Type Hints**
- Use modern Python 3.10+ union syntax: `def foo(x: int | None) -> str:`
- Avoid `Optional[x]` in new code

**Docstrings**
- Use Google-style docstrings for public APIs
- Include Args, Returns, Raises sections where helpful
- Keep brief module-level docstrings at the top of files

**Error Handling**
- Use specific exception types, not bare `except:`
- Log errors with context before re-raising
- Return appropriate HTTP status codes in API endpoints (500 for unexpected, 400/404 for client errors)

### TypeScript/React (frontend)

**Imports**
- Order: React imports, external libs, internal imports, CSS
- Use `import type { ... }` for type-only imports
- Use relative imports for internal modules: `./components/X` not `@/components/X`

**Naming**
- `camelCase` for variables and functions
- `PascalCase` for components and type names
- File naming: `PascalCase.tsx` for components, `camelCase.ts` for utilities/hooks

**TypeScript**
- Use strict mode (already enabled in tsconfig)
- Prefer `interface` over `type` for object shapes
- Use `as const` for literal unions when appropriate
- Never use `any` - use `unknown` if truly necessary

**React**
- Use functional components with hooks
- Name custom hooks with `use` prefix
- Destructure props at the component boundary
- Keep components focused (single responsibility)

**Styling**
- Use CSS classes defined in `*.css` files
- Avoid inline styles except for dynamic values
- Follow existing class naming patterns in `App.css`

---

## Working with the Codebase

### Key Files

- **config.yaml** - Main configuration (API keys, thresholds, polling intervals)
- **.env** - Local environment variables (copy from `.env.example`)
- **edge_engine/data/kalshi_client.py** - Kalshi API client
- **edge_engine/models/probability_model.py** - Core probability estimation logic
- **frontend/src/hooks/useMarkets.ts** - Main data fetching hook
- **frontend/src/components/** - UI components

### Common Tasks

**Adding a new API endpoint**
1. Add route in `edge_engine/api_server.py`
2. Use proper error handling (try/except with 500 return on failure)
3. Return JSON with consistent structure

**Adding a new frontend component**
1. Create file in `frontend/src/components/`
2. Add type definitions in appropriate `types/*.ts` file
3. Use existing component patterns (props interface, functional component)

**Running locally**
```bash
# Terminal 1: Start API server
python -m edge_engine.api_server

# Terminal 2: Start frontend
cd frontend && npm run dev
```

---

## Testing Guidelines

- Prefer pytest for Python, Vitest for TypeScript
- Test file naming: `test_*.py` or `*_test.py` for Python, `*.test.ts` or `*.spec.ts` for TS
- Focus tests on business logic and critical paths
- Mock external API calls in unit tests
- Include integration tests for API endpoints

---

## Lint Before Committing

Run the appropriate linter for your changes:

```bash
# Frontend
cd frontend && npm run lint

# Backend (requires dev dependencies)
pip install black mypy
black --check edge_engine/
mypy edge_engine/
```

Address all warnings and errors before submitting.