# Contributing to YA-WAMF

First off, thanks for taking the time to contribute! 🎉

The following is a set of guidelines for contributing to Yet Another WhosAtMyFeeder. These are mostly guidelines, not rules. Use your best judgment, and feel free to propose changes to this document in a pull request.

## 🛠️ Development Setup

### Backend (Python)
1.  Navigate to `backend/`:
    ```bash
    cd backend
    ```
2.  Create a virtual environment:
    ```bash
    python3.12 -m venv .venv
    source .venv/bin/activate
    ```
3.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
4.  Run the dev server:
    ```bash
    uvicorn app.main:app --reload
    ```

### Frontend (Svelte 5)
1.  Navigate to `apps/ui/`:
    ```bash
    cd apps/ui
    ```
2.  Install dependencies:
    ```bash
    npm install
    ```
3.  Run the dev server:
    ```bash
    npm run dev
    ```
    *Note: You may need to configure the Vite proxy in `vite.config.ts` if your backend is not on port 8000.*

## 🧪 Running Tests

*   **Backend:**
    ```bash
    cd backend
    pytest
    ```
*   **Frontend:**
    ```bash
    cd apps/ui
    npm run test  # (Assuming vitest is configured)
    ```

## 📐 Coding Standards

*   **Python:** I use [Ruff](https://github.com/astral-sh/ruff) for linting and formatting. Please run `ruff check .` and `ruff format .` before committing.
*   **TypeScript/Svelte:** Use standard Prettier formatting.
*   **Commits:** Please write clear, concise commit messages.

## 🐛 Reporting Bugs

Bugs are tracked as GitHub issues. When filing an issue, please include:
*   A clear title and description.
*   Steps to reproduce.
*   Logs from the backend (`docker compose logs backend`).
*   Browser console errors (if UI related).

## 🚀 Pull Requests

1.  Fork the repo and create your branch from `main`.
2.  If you've added code that should be tested, add tests.
3.  Ensure the test suite passes.
4.  Make sure your code lints.
5.  Issue that pull request!
