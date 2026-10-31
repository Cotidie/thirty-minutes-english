from app.api import accounts, auth, coaches, corpus, credits, events, images, records, sessions, settings, topics

ROUTERS = (auth.router, accounts.router, credits.router, events.router, images.router, settings.router, topics.router, sessions.router, coaches.router, records.router, corpus.router)
