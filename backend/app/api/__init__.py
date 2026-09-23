from app.api import coaches, records, sessions, settings, topics

ROUTERS = (settings.router, topics.router, sessions.router, coaches.router, records.router)
