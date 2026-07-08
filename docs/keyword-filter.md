# Keyword Filter

This fork adds a lightweight keyword filter on top of RSStT. It does **not** rebuild the RSS bot. RSStT still handles RSS fetching, polling, deduplication, subscription management, message formatting, media handling, OPML import/export, and Telegram delivery.

The filter supports a global default rule and per-subscription overrides:

- If a subscription has its own rule, that rule is used.
- If a subscription has no rule, the global default rule is used.
- If neither exists, upstream behavior is kept and every new entry is sent.

## Basic workflow

Subscribe to a feed as usual:

```text
/sub https://www.nature.com/nmat.rss
```

Set a keyword filter:

```text
/set_filter https://www.nature.com/nmat.rss include=CuCrZr|ODS|graphene copper exclude=battery|catalysis fields=title,summary mode=any
```

Set the global default keyword filter:

```text
/set_filter default include=CuCrZr|oxide dispersion strengthened exclude=battery|catalysis fields=title,summary
```

For reliability, you can also use the subscription ID shown in `/list` or `/set` pages:

```text
/set_filter 123 include=CuCrZr|oxide dispersion strengthened exclude=battery|catalysis fields=title,summary
```

Show the current filter:

```text
/set_filter 123
/set_filter default
```

Clear the filter:

```text
/set_filter 123 off
/set_filter default off
```

## Rule fields

A rule contains:

```json
{
  "include": ["CuCrZr", "oxide dispersion strengthened"],
  "exclude": ["battery", "catalysis"],
  "fields": ["title", "summary"],
  "mode": "any"
}
```

Meaning:

- `include`: white list terms. If non empty, at least one term must match when `mode=any`; all terms must match when `mode=all`.
- `exclude`: black list terms. If any exclude term matches, the entry is skipped. Exclude has higher priority than include.
- `fields`: the fields to search.
- `mode`: `any` or `all` for include matching.

## Supported fields

```text
title
summary
content
author
tags
link
```

Default fields are:

```text
title,summary
```

In the first implementation, `summary` and `content` both use `Post.html` internally.

## Matching rules

The matching is intentionally simple:

- case insensitive
- ordinary terms use substring matching
- HTML tags are removed before matching
- Unicode is preserved
- multiple terms are separated by `|`
- terms beginning with `re:` are treated as regular expressions

Examples:

```text
CuCrZr
high strength copper
re:\bCu[- ]?Cr[- ]?Zr\b
```

The regex example can match `CuCrZr`, `Cu-Cr-Zr`, and `Cu Cr Zr`.

Bad regex terms are ignored and logged as warnings. They do not crash the bot.

## Storage

The first implementation avoids database schema migrations. Rules are stored in the existing `option` table.

Key format:

```text
keyword_filter:<sub_id>
keyword_filter:default
```

Value format: JSON string.

## Implementation note

The filter is applied in `src/monitor/_notifier.py`, after RSStT parses an entry into `Post` and before Telegram sending:

```python
post = await self._get_post(idx)
if post and await keyword_filter.post_matches_filter(sub, post):
    await self._do_send(sub, post)
```

This keeps RSS fetching, entry hashing, polling, formatting, and Telegram sending untouched.

## Non goals

This feature does not implement:

- subscription groups or folders
- global default keyword rules
- web UI
- semantic matching or LLM relevance scoring
- automatic RSS discovery beyond upstream RSStT behavior
- paper digest formatting
