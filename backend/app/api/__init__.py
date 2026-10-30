from app.api import accounts, auth, coaches, corpus, events, images, records, sessions, settings, topics

ROUTERS = (auth.router, accounts.router, events.router, images.router, settings.router, topics.router, sessions.router, coaches.router, records.router, corpus.router)
