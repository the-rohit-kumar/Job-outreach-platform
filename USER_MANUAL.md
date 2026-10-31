# OutreachHub — User Manual

This manual is rendered inside the app at `/help` with search. Keep it in sync with what is
actually built: **update it at the end of every build step**.

## Build status

| Area | Status |
| --- | --- |
| Monorepo, database models, migrations | Built |
| Single-user login, sessions, API tokens | Built |
| Profile page (About me, do-not-mention, tone, CV link) | Built |
| First-run onboarding checklist + Dashboard | Built |
| Collectors, Leads, Sources pages | Built |
| Dedupe and scoring (Founder-focused, Senior penalty) | Built |
| Enrichment, drafting, self-check (Email & founder extraction) | Built |
| Review Queue, Gmail OAuth, warm-up and caps | Built |
| Tracker, reply detection, follow-ups | Coming in step 6 |
| Chrome extension | Coming in step 7 |
| Remaining collectors, manual importer, Analytics, Help page | Coming in step 8 |


Everything on this list that says "Built" works today; anything else renders a placeholder page
that names the step it arrives in.

---

## 1. One-time setup (about 30 minutes)

- Run `docker compose up --build` (or see the README for a local, no-Docker run), open
  http://localhost:3000, and create your login. This login is local to your machine — the app
  never asks for your LinkedIn, X, Wellfound or Gmail passwords.
- **Profile:** check that your details are accurate and the do-not-mention list is filled in
  (client names, SAP). Edit the text yourself, because drafts are only as honest as this page.
- **Settings:** connect Gmail through the Google sign-in screen (the app never sees your
  password), choose a send window, keep the default warm-up schedule.
- **Sources:** turn on the API-based collectors first (HN, RemoteOK, WWR, Remotive, GitHub).
  Add keywords such as LLM, agents, RAG, LangChain, Python, part-time, contract.
- Add company slugs for Lever, Greenhouse, and Ashby (the name in the job-board URL).
- In Gmail, create job alerts on LinkedIn, Wellfound, Indeed, Naukri, and similar sites.
- Install the Chrome extension (Extensions > Developer mode > Load unpacked) and paste the
  token from Settings into the popup.

The Dashboard shows this as a checklist and ticks items off as you finish them.

## 2. Daily routine (about 45 minutes)

- **Morning (10 min):** check Dashboard counts and source errors, "Run now" on failed sources.
- **Review session (25-30 min):** in the Review Queue, check each lead summary and the company
  hook, then `A` approve, `E` edit, `S` skip, `R` regenerate, `N` never contact. Email drafts
  send after approval. Platform drafts: Copy or Fill draft, paste, read, press Send yourself,
  confirm "sent". Stop at the day's cap.
- **Evening (10 min):** update the Tracker, reply to people promptly, approve single follow-ups.

## 3. Warm-up schedule (do not skip)

- Days 1-3: up to 10 emails per day. Days 4-7: up to 20. Days 8-14: up to 30. After day 14:
  40-50 if bounce rate and spam signals stay clean.
- LinkedIn/X/Wellfound: start at 5-10 per day, never above 25 per platform.
- The app pauses automatically on a bounce rate over 5%. Find the cause instead of overriding.

## 4. Using the Chrome extension

- Log in yourself. Open a profile or post you chose, click "Send to OutreachHub" to save a lead.
- Open that person's message box, click "Fill draft", read, edit, press Send yourself, then
  "Confirm sent" in the popup. Stop for the day on any captcha or restriction notice.

## 5. Writing good messages

- One specific thing about their product, post, or repo (if you can't name it, skip the lead).
- One relevant project of yours, one clear ask, under 120 words, no hype or unprovable claims.
- Edit at least one line in each message so it sounds like you.

## 6. Reading Analytics (weekly, 15 minutes)

- Double down on the top two or three sources by reply rate. Disable sources under 1% after
  100+ messages. Typical cold-outreach reply rate is 3-8%; under 2% after two weeks means the
  drafts need to be more specific, not that you need to send more.

## 7. Replies and next steps

- Reply within a few hours, offer a short call, propose a small trial task with fixed scope and
  a rate. Before accepting paid work, check the Wipro contract for outside-work and
  conflict-of-interest clauses. Never share client data or Wipro-internal details.

## 8. Troubleshooting

- **Spam folder:** lower the daily count, check warm-up, shorten messages, remove links.
- **High bounce rate:** mark the contact, the lead is suppressed.
- **Collector errors:** Sources > the source > last run log (usually rate limits or a changed page).
- **Platform warning or captcha:** stop on that platform for 24-48 hours and halve the cap.
- **Opt-out request:** click "Opt out" to add the person to the suppression list permanently.
- **Cannot sign in:** the login is the one you created on first run; nothing is emailed to you.
  Delete `backend/data/outreach.db` only if you are happy resetting the whole local app.

## 9. Adding a new source

- Prefer an official API or RSS feed, otherwise use the manual importer. Copy an existing
  collector, implement `fetch()` to return Lead objects, add its settings to the YAML config,
  add a recorded-fixture test, enable it on the Sources page, and watch its first run.

## Non-negotiable rules

1. You approve every message before it is sent. No unattended sending, no "approve all" button.
2. The app never stores or asks for your LinkedIn, X, Wellfound or Gmail passwords. Gmail uses
   OAuth only.
3. LinkedIn, X and Wellfound are never scraped and never automated. The extension only works on
   pages you opened yourself.
4. Only publicly listed contact information is used — no email guessing, no contact-data
   scraping, nothing behind logins.
5. Every collector respects robots.txt, site terms, rate limits, opt-outs, and the suppression
   list.
