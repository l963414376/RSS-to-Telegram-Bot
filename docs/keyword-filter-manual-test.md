# Keyword Filter Manual Test Checklist

Use this checklist after deploying the `feature-keyword-filter` branch.

## 1. Start bot normally

Expected result: the bot starts with no database migration errors.

## 2. Subscribe to a test feed

```text
/sub https://www.nature.com/nmat.rss
```

Expected result: subscription succeeds.

## 3. Check current filter

Use either the feed URL or the subscription ID.

```text
/set_filter https://www.nature.com/nmat.rss
```

Expected result: bot says the keyword filter is not set.

## 4. Set include filter

```text
/set_filter https://www.nature.com/nmat.rss include=CuCrZr|ODS fields=title,summary
```

Expected result: bot replies `Keyword filter updated` and shows include terms.

## 5. Check include behavior

Wait for new entries or temporarily use a feed whose recent entries are known.

Expected result: only entries whose title or summary contains `CuCrZr` or `ODS` are pushed.

## 6. Set include plus exclude filter

```text
/set_filter https://www.nature.com/nmat.rss include=copper exclude=battery|catalysis fields=title,summary
```

Expected result: entries containing `copper` are sent unless they also contain `battery` or `catalysis`.

## 7. Set regex filter

```text
/set_filter https://www.nature.com/nmat.rss include=re:\bCu[- ]?Cr[- ]?Zr\b fields=title,summary
```

Expected result: `CuCrZr`, `Cu-Cr-Zr`, and `Cu Cr Zr` can match.

## 8. Clear filter

```text
/set_filter https://www.nature.com/nmat.rss off
```

Expected result: bot replies `Keyword filter cleared`.

## 9. Confirm upstream behavior

After clearing the filter, new entries from the subscription should be sent normally, matching upstream RSStT behavior.

## 10. Bad regex should not crash bot

```text
/set_filter https://www.nature.com/nmat.rss include=re:[ fields=title,summary
```

Expected result: the bot keeps running. The bad regex is logged as a warning and treated as not matched.
