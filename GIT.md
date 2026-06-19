# Git: Push to Remote and Conventions

Steps to push this project to Git and what to ignore.

---

## 1. One-time: init and remote

If the project is **not** yet a git repo:

```bash
cd /path/to/steampipe
git init
git add .
git status   # ensure .env and venv are not staged (see .gitignore)
git commit -m "Initial commit: Cloud Governance API, worker, scheduler, migrations"
```

Add the remote (use your repo URL):

```bash
git remote add origin https://github.com/DRANTIQ/steampipe.git
# or: git remote add origin git@github.com:YOUR_ORG/steampipe.git
```

---

## 2. Push to Git

```bash
# Ensure .env is not tracked
git status
# If .env appears, it should be in .gitignore; if it was committed before, run:
# git rm --cached .env

git add .
git status
git commit -m "Your message"
git branch -M main
git push -u origin main
```

For an **existing** repo that already has a remote:

```bash
git add .
git status
git commit -m "Your message"
git push origin main
```

---

## 3. What is ignored (.gitignore)

| Ignored | Reason |
|--------|--------|
| `.env` | Secrets: DB URL, Redis URL, AWS keys, JWT. Use `env.example` as a template; never commit `.env`. |
| `venv/`, `.venv/`, `env/` | Python virtual environments. |
| `__pycache__/`, `*.pyc` | Python bytecode. |
| `local/` | Local snapshot storage (dev). |
| `.idea/`, `.vscode/` | IDE project files (optional to share; safe to ignore). |
| `dist/`, `build/`, `*.egg-info/` | Build artifacts. |
| `.coverage`, `htmlcov/` | Test coverage output. |

**Rule:** Never commit credentials. Copy `env.example` to `.env` locally and fill from **user_input.md** or your team’s secret store.

---

## 4. Before first push (checklist)

- [ ] `.gitignore` is in the repo (so `.env` and `venv/` are ignored).
- [ ] `.env` is **not** staged (`git status` should not list `.env`).
- [ ] `env.example` is committed (no secrets; documents required variables).
- [ ] Migrations under `alembic/versions/` are committed.
- [ ] No hardcoded passwords or API keys in code.

---

## 5. Branches and workflow (optional)

- Use a main branch (e.g. `main` or `master`) for production-ready code.
- For features: `git checkout -b feature/trigger-tenant`, then merge via PR.
- Run tests before push: see **Testing.md**.

---

## 6. If you already committed .env by mistake

```bash
git rm --cached .env
echo ".env" >> .gitignore
git add .gitignore
git commit -m "Stop tracking .env; add to gitignore"
# Rotate any secrets that were ever pushed (DB password, Redis, AWS, JWT).
git push
```

Then rotate all secrets that might have been exposed.
