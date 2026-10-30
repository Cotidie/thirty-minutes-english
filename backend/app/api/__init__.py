from app.api import auth, coaches, corpus, images, records, sessions, settings, topics

ROUTERS = (auth.router, images.router, settings.router, topics.router, sessions.router, coaches.router, records.router, corpus.router)
