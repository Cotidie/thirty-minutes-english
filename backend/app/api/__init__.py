from app.api import coaches, corpus, records, sessions, settings, topics

ROUTERS = (settings.router, topics.router, sessions.router, coaches.router, records.router, corpus.router)
