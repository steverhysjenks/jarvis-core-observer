# API surface

FastAPI also exposes generated OpenAPI documentation at `/docs`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | service identity/version |
| GET | `/health` | health, version, local timestamp/timezone |
| GET | `/context/home` | home context |
| GET | `/context/user` | user/presence context |
| GET | `/context/calendar?days=` | normalised calendar context |
| GET | `/context/history?hours=` | semantic HA history |
| GET | `/context/observer` | current Observer snapshot + candidates |
| GET | `/observer/status` | runtime cycle/mode/error status |
| GET | `/observer/announcements?limit=` | recent Observer decisions |
| GET | `/api/notifications?limit=` | structured recent delivery history |
| GET | `/notifications?limit=` | simple HTML delivery-history view |
| POST | `/voice/repeat-last` | authenticated deterministic replay |
| POST | `/request` | authenticated bounded request entry point |

`/request` and `/voice/repeat-last` require `Authorization: Bearer <JARVIS_CORE_API_KEY>`.
