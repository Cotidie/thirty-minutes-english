---
name: expression-cleanup
description: Use when reviewing or pruning the thirty-minutes-english expression corpus, after importing new expression posts, or when a session teaches a song lyric, movie line, quote, or a fixed sentence about one narrow situation instead of a reusable chunk.
---

# Expression cleanup

## Overview

The corpus is for chunks a learner carries into many conversations. A niche expression is a line that only makes sense where it came from, or a fixed sentence about one narrow fact. Find them, let the owner approve, then delete through the app.

## The test

Decide each expression with these questions, in order. The first answer that fits decides.

1. **Is it an established idiom or a stock phrase in its standard form?** Keep. (`It's on the tip of my tongue`, `Off the top of my head`, `Don't beat yourself up`)
2. **Did it come from a song, film, show, poem, slogan or quote?** Delete. This holds even when one line sounds sayable (`You had a bad day`) or echoes an idiom in the lyric's own words (`The grass might look greener on the other side`). If the standard idiom is worth having, it is a separate entry. To tell, look at the other lines from the same `source`: a post of lyrics or dialogue is deleted as a set, except for lines that pass question 1.
3. **Does it carry a reusable part: a slot (`~`, `someone`, `A and B`), or a conversational move that fits any topic?** Keep. (`How can I get to~?`, `Fill someone in`, `I'm torn between A and B`, `Good for you`, `Let me back up`, `Let me put it this way.`, `What have you been up to?`)
4. **Is it a complete sentence whose content is fixed, about one narrow fact or a rare moment?** Delete. (`How old is your boss?`, `What color is her hair?`, `Could I have a wet wipe, please?`, `The water pressure is really low`, `We're out of toilet paper`, `Let's cuddle on the couch and watch a movie.`, `I will do it without a plan.`) It does not matter that it is grammatical, practical, or something a person could say. The words fit one situation, and nothing carries over.
5. **A fixed sentence that is the stock wording for a very common moment** stays. (`Could we get the check?`, `Is this on the house?`)

"It's practical" and "a learner could reuse it" are not reasons to keep. Every grammatical sentence passes those. The question is whether the expression gives a learner something to use on a different topic.

## Procedure

1. Read `decisions.md` in this folder. Never propose an id it lists as kept. Start from its pending list if it has one.
2. List candidates read-only from the live database (run from the repo root):
   ```sh
   docker compose exec -T backend uv run --no-dev python - <<'EOF'
   import re, sqlite3
   c = sqlite3.connect("file:/data/sessions.db?mode=ro", uri=True)
   slot = re.compile(r"~|someone|one's|\bA\b and \bB\b|/")
   used = dict(c.execute("SELECT expression_id, count(*) FROM session_expressions GROUP BY expression_id"))
   for i, p, s in c.execute("SELECT id, phrase, source FROM expressions ORDER BY length(phrase) DESC"):
       if not slot.search(p) and len(p.split()) >= 4:
           print(i, used.get(i, 0), s[-14:], p)
   EOF
   ```
   Longest first. For every lyric- or quote-like hit, list its whole `source` (`WHERE source = ?`). Short lines from the same post are usually lyrics too.
3. Show the owner at most 30 candidates, grouped: lyrics, film or show lines, quotes, fixed narrow sentences. Give each its id and the number of sessions that teach it. Name the borderline ones you keep and why. Then stop and wait.
4. After the owner approves, back up, then delete only the approved ids through the API, so open sessions hear the change:
   ```sh
   docker compose exec -T backend uv run --no-dev python - <<'EOF'
   import json, os, sqlite3, urllib.error, urllib.request
   from datetime import datetime
   IDS = []  # the approved ids
   src = sqlite3.connect("/data/sessions.db")
   src.backup(sqlite3.connect(f"/data/sessions.db.bak-before-expression-cleanup-{datetime.now():%Y-%m-%d-%H%M%S}"))
   base = "http://127.0.0.1:8765"
   login = json.dumps({"email": os.environ["ADMIN_EMAIL"], "password": os.environ["ADMIN_PASSWORD"]}).encode()
   res = urllib.request.urlopen(urllib.request.Request(f"{base}/api/auth/login", login, {"Content-Type": "application/json"}))
   cookie = {"Cookie": res.headers["set-cookie"].split(";")[0]}
   for i in IDS:
       try:
           print(i, urllib.request.urlopen(urllib.request.Request(f"{base}/api/expressions/{i}", method="DELETE", headers=cookie)).status)
       except urllib.error.HTTPError as e:
           print(i, e.code)
   urllib.request.urlopen(urllib.request.Request(f"{base}/api/auth/logout", b"", cookie, method="POST"))
   print("left:", src.execute("SELECT count(*) FROM expressions").fetchone()[0])
   EOF
   ```
   Every id should answer 204.
5. Update `decisions.md`: add what was deleted, add what was kept on purpose, and replace the pending list. Commit it.

## Common mistakes

- Keeping a fixed narrow sentence because it is "practical" or "everyday".
- Keeping a lyric line because it resembles an idiom or a song title.
- Deleting a slot pattern or a stock phrase because it is short or plain.
- Deleting with SQL. Open sessions would not hear the change.
- Deleting before the owner approves, or deleting more than was approved.
