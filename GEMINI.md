# Project Instructions (GEMINI.md)

This file contains foundational instructions, architecture rules, and workflows for the `zdrav.lenreg` project.

## Knowledge Management

- **API Documentation:** Save all CURL commands, JSON structures, and API responses as separate markdown files in `docs/knowledge/`.
- **Index:** Always maintain and update `docs/knowledge/_INDEX.md` when adding new API documentation.

## Session Workflow

- **Logging:** Record the results and key changes of every session in `SESSION_LOG.md` before concluding. Use the existing format: a list of bullet points under a date header.
- **Development History:** Maintain `DEVELOPMENT_HISTORY.md` for high-level changes, milestones, and technical debt tracking.

## File Restrictions & Security

- **Ignore Patterns:** Do not process or analyze the following:
  - `.git/`, `node_modules/`, `dist/`
  - `*.log` files
  - `data/monitoring_cache.json`
- **Data Privacy:** Never read large data files (e.g., `data/doctors.json`, `data/users_config.json`) in their entirety. Use structure previews or specific targeted reads if necessary.
- **Secrets:** Ensure `.env` is used for sensitive configuration. Never hardcode tokens or proxy URLs.

## Architecture & Conventions

- **Data Storage:** All JSON configuration and data files must reside in the `data/` directory.
- **API Clients:** The primary API interaction logic must be in `api/zdrav_client.py`.
- **Database:** Use `database/manager.py` for general data management and `database/doctor_manager.py` for doctor-specific logic.
- **Handlers:** Telegram bot handlers are located in the `handlers/` directory. Use `handlers/common.py` for general logic and `handlers/registration.py` for patient registration.
- **Services:** Background tasks (e.g., monitoring) and discovery logic reside in `services/`.
- **Utilities:** Shared utility functions (caching, etc.) should be in `utils/`.

## Coding Standards

- **Error Handling:** Use explicit checks for `None` types (e.g., `call.message`, `call.from_user`) to satisfy Pylance and ensure runtime stability.
- **API Interaction:** Ensure all API requests include necessary headers like `X-Requested-With`, `Content-Type`, and CSRF cookies where applicable.
- **Concurrency:** Use `asyncio.Lock` and `aiofiles` for atomic file operations, especially in `services/monitor.py`.
- **Rate Limiting:** Respect API limits using `aiolimiter` in the API client.
