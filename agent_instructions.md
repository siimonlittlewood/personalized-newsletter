# Daily newsletter agent instructions

Run every morning by the scheduled agent. This is the actual selection/
composition policy — it should stay stable across runs regardless of what
that day's headlines happen to be, so it generalizes rather than being
re-tuned by hand each time.

## Steps

1. Check Gmail for unprocessed replies to previous newsletters:
   `search_threads` with query `in:inbox subject:"Your Morning Briefing"`.
   IMPORTANT: `-label:Newsletter/Processed` in the query does NOT reliably
   exclude a thread — Gmail matches at the thread level, so a thread still
   shows up if any message in it (e.g. the original outbound send) lacks
   the label, even once the reply itself has been labeled (confirmed by
   testing). So: for each returned thread, `get_thread` and inspect each
   individual message's `labelIds` — only process reply messages that do
   NOT already have the `Newsletter/Processed` label id. If it contains a
   ticker add/remove request in plain English (e.g. "add SHOP.TO and AAPL",
   "drop TSLA"), update `config/tickers.json` accordingly. When reading the
   reply, use `plaintextBody` and take only the portion before the quoted
   "On ... wrote:" block — that's the new content, not the echoed original.
   Then `label_message` the reply with the `Newsletter/Processed` label id
   (get its id via `list_labels`) so it's never re-parsed on a future run —
   this is the only guard against reprocessing the same reply every
   morning, since there's no other local state tracking which replies were
   already handled.
2. Run `python scripts/fetch_headlines.py` to refresh `output/latest.json`
   (candidate headlines, already filtered for recency and obvious rumor
   language, tagged by interest category) and market data.
3. Select and compose the newsletter per the rules below.
4. Write the HTML body to a temp file and send it via
   `python scripts/send_email.py --subject "..." --html-file ...`.

## Selection rules

- **Volume**: ~10-12 personalized ("For You") items + ~4-5 general news
  items. Total roughly 15-17. Err toward including more borderline items
  rather than fewer — these are skimmable headlines, not required reading,
  so the cost of an uninteresting headline is low but the cost of a missed
  one is a duller newsletter.
- **Category balance**: hard cap of **2 items per interest category**
  (sports, music, tech, fashion, fitness, society), no exceptions even if
  one category has abundant fresh content that day. This naturally forces
  breadth across categories to hit the volume target — a quiet day for a
  given category is normal and should show up as "less content today," not
  as another category eating its slots.
- **Recency**: `fetch_headlines.py` already drops anything older than 7
  days. Within what's left, prefer same-day/prior-day stories when there's
  a choice between otherwise-similar candidates.
- **No rumors/speculation**: the fetch script filters obvious cases
  (regex on "rumor(s)", "reportedly", etc.), but apply judgment on top of
  it — skip trade speculation, "sources say," clickbait claims, and similar
  even if the filter missed the exact phrasing. Prefer confirmed news
  (signings, results, releases, announcements) over speculation.
- **Preserve qualifying context**: don't compress away details that change
  the meaning of a headline — e.g. "Summer League" vs. regular season,
  "preseason" vs. "regular season," rumored vs. confirmed, embargoed vs.
  released. A reader should never be confused about what actually happened.
- **Prefer substance over gossip**: within a category, when choosing
  between candidates, favor newsworthy items (releases, signings, real
  developments) over scene drama/gossip/controversy pieces, unless the
  drama item is itself clearly the most significant story available.
- **Summaries**: 1-3 sentences per headline, grounded strictly in the
  fetched title/description — never invent details not present in the
  source data.

## Known ongoing gaps (update this section as sources improve)

- No dedicated archive/vintage-fashion feed yet — relying on general
  fashion feeds (Hypebeast, Highsnobiety, Fashionista) to surface it via
  keyword match, which may be thin.
- Data science / big tech coverage depends entirely on Currents API's
  generic "technology" category matching interest keywords — no dedicated
  source yet.
- "Canadian politics" has no dedicated source; Currents API's "politics"
  category is global/US-heavy.
