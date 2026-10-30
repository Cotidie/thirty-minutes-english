from app.api import auth, coaches, corpus, records, sessions, settings, topics

ROUTERS = (auth.router, settings.router, topics.router, sessions.router, coaches.router, records.router, corpus.router)
