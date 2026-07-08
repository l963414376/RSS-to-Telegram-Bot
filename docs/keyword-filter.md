# Keyword Filter for Academic and Journal Feeds

This fork is intended to add a lightweight keyword filter on top of RSStT instead of rebuilding an RSS to Telegram bot from scratch.

## Goal

A user can subscribe to any RSS feed supported by RSStT and optionally attach keyword rules to that subscription. New entries are only sent to Telegram when they match the rule.

Typical use cases:

- journal latest article RSS feeds
- Articles in Press feeds
- RSSHub generated feeds
- website feeds that already expose RSS or Atom
- cross field alerts such as materials science, semiconductors, energy, biology, medicine, AI, economics, or any custom topic

## Non goals

This fork should not reimplement the existing RSStT core features:

- RSS and Atom fetching
- Telegram delivery
- subscription management
- OPML import and export
- HTTP caching
- media handling
- message formatting
- deduplication and polling

Those remain upstream RSStT responsibilities.

## Minimal feature design

The first implementation should add only one layer before Telegram sending:

```text
new RSS entry
    ↓
RSStT parses entry into Post
    ↓
keyword filter checks title, summary/content, author, tags, and link
    ↓
matched: send to Telegram
not matched: skip silently
```

## Rule model

Each subscription can have one keyword filter. A filter contains:

```json
{
  "include": ["CuCrZr", "high strength copper", "oxide dispersion strengthened"],
  "exclude": ["lithium battery", "electrocatalysis", "photocatalysis"],
  "fields": ["title", "summary"],
  "mode": "any"
}
```

Meaning:

- `include`: at least one term must match when present.
- `exclude`: if any term matches, the entry is skipped.
- `fields`: which Post fields are searched.
- `mode`: `any` means any include term is enough; `all` means all include terms must match.

Recommended default fields:

```text
title, summary
```

For academic feeds, title plus summary is usually enough. Full content matching can create noisy alerts.

## Matching rules

The matching should be deliberately simple:

- case insensitive
- HTML tags removed before matching
- Unicode preserved
- terms separated by `|`
- terms beginning with `re:` treated as regular expressions

Examples:

```text
CuCrZr
high strength copper
re:\bCu[- ]?Cr[- ]?Zr\b
```

## Telegram command proposal

Use one command:

```text
/set_filter <feed_url_or_sub_id> include=term1|term2 exclude=term3|term4 fields=title,summary mode=any
```

Examples:

```text
/set_filter https://www.nature.com/nmat.rss include=CuCrZr|oxide dispersion strengthened|graphene copper exclude=battery|catalysis fields=title,summary mode=any
```

Clear a filter:

```text
/set_filter https://www.nature.com/nmat.rss off
```

Show current filter:

```text
/set_filter https://www.nature.com/nmat.rss
```

## Storage strategy

Avoid schema migrations at first. Store per subscription filters in the existing `option` table with keys like:

```text
keyword_filter:SUB_ID
```

Value is JSON.

This keeps the change small and avoids touching the upstream `sub` table schema. If the feature proves stable, it can later be migrated to a first class `Sub.keyword_filter` field.

## Best insertion point

The safest insertion point is `src/monitor/_notifier.py`.

Current flow:

```text
Notifier._notify_sub_with_entry_idx
    → Notifier._get_post
    → Notifier._do_send
    → Notifier._send
```

Add the filter check after `_get_post()` returns a `Post` and before `_do_send()`.

Pseudo code:

```python
post = await self._get_post(idx)
if post and await keyword_filter.matches(sub, post):
    await self._do_send(sub, post)
```

This avoids changing feed fetching, entry hashing, polling, and Telegram formatting.

## User workflow

1. Deploy RSStT normally.
2. Add a feed:

```text
/sub https://www.nature.com/nmat.rss
```

3. Attach keywords:

```text
/set_filter https://www.nature.com/nmat.rss include=CuCrZr|ODS|graphene copper exclude=battery|catalysis fields=title,summary
```

4. New matching entries are pushed to Telegram. Non matching entries are skipped.

## What the user still needs to do

The user only needs to provide:

- Telegram bot token from BotFather
- Telegram user ID for manager setup
- RSS feed URLs or website URLs that can be converted through RSSHub
- keyword lists

All code changes should stay in this fork.
