#  RSS to Telegram Bot
#  Copyright (C) 2021-2024  Rongrong <i@rong.moe>
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as
#  published by the Free Software Foundation, either version 3 of the
#  License, or (at your option) any later version.

from __future__ import annotations

from typing import Optional
import re

from .. import db, keyword_filter
from ..i18n import i18n
from .types import *
from .utils import command_gatekeeper, parse_command, escape_html, logger


KEY_VALUE_RE = re.compile(r'(?P<key>include|exclude|fields|mode)\s*=\s*(?P<value>.*?)(?=\s+(?:include|exclude|fields|mode)\s*=|$)')


USAGE_HTML = (
    '<b>Keyword filter usage</b>\n'
    '<code>/set_filter &lt;feed_url_or_sub_id&gt; include=term1|term2 exclude=term3|term4 fields=title,summary mode=any</code>\n\n'
    'Examples:\n'
    '<code>/set_filter 123 include=CuCrZr|ODS exclude=battery|catalysis fields=title,summary</code>\n'
    '<code>/set_filter 123 off</code>\n'
    '<code>/set_filter 123</code>'
)


def _parse_filter_params(param_text: str) -> keyword_filter.KeywordFilterRule:
    parsed = {m.group('key'): m.group('value').strip() for m in KEY_VALUE_RE.finditer(param_text)}
    include = tuple(filter(None, (term.strip() for term in parsed.get('include', '').split('|'))))
    exclude = tuple(filter(None, (term.strip() for term in parsed.get('exclude', '').split('|'))))
    fields = tuple(filter(None, (field.strip() for field in parsed.get('fields', '').split(','))))
    mode = parsed.get('mode', 'any')
    return keyword_filter.KeywordFilterRule.from_mapping({
        'include': include,
        'exclude': exclude,
        'fields': fields or keyword_filter.DEFAULT_FIELDS,
        'mode': mode,
    })


async def _get_sub_by_target(chat_id: int, target: str) -> Optional[db.Sub]:
    if target.isdecimal():
        return await db.Sub.get_or_none(id=int(target), user_id=chat_id).prefetch_related('feed')
    return await db.Sub.get_or_none(user_id=chat_id, feed__link=target).prefetch_related('feed')


def _format_sub(sub: db.Sub) -> str:
    feed = getattr(sub, 'feed', None)
    title = sub.title or (feed.title if feed else None) or str(sub.id)
    link = feed.link if feed else ''
    return f'<a href="{escape_html(link)}">{escape_html(title)}</a>' if link else escape_html(title)


def _format_current_filter(sub: db.Sub, rule: Optional[keyword_filter.KeywordFilterRule]) -> str:
    if rule is None:
        return (
            '<b>Keyword filter is not set</b>\n'
            f'Subscription: {_format_sub(sub)}\n'
            f'Sub ID: <code>{sub.id}</code>\n\n'
            f'{USAGE_HTML}'
        )
    return (
        '<b>Current keyword filter</b>\n'
        f'Subscription: {_format_sub(sub)}\n'
        f'Sub ID: <code>{sub.id}</code>\n'
        f'<pre>{escape_html(keyword_filter.format_rule(rule))}</pre>'
    )


@command_gatekeeper(only_manager=False)
async def cmd_set_filter(
        event: TypeEventMsgHint,
        *_,
        lang: Optional[str] = None,
        chat_id: Optional[int] = None,
        **__,
):
    chat_id = chat_id or event.chat_id
    args = parse_command(event.raw_text, max_split=2, strip_inline_header=True)

    if len(args) < 2:
        await event.respond(USAGE_HTML, parse_mode='html', link_preview=False)
        return

    target = args[1]
    param_text = args[2].strip() if len(args) >= 3 else ''

    sub = await _get_sub_by_target(chat_id, target)
    if sub is None:
        await event.respond('ERROR: ' + i18n[lang]['subscription_not_exist'])
        return

    if not param_text:
        rule = await keyword_filter.get_filter(sub.id)
        await event.respond(_format_current_filter(sub, rule), parse_mode='html', link_preview=False)
        return

    if param_text.lower() in {'off', 'clear', 'disable', 'none'}:
        await keyword_filter.clear_filter(sub.id)
        logger.info(f'Cleared keyword filter for sub {sub.id}')
        await event.respond(
            '<b>Keyword filter cleared</b>\n'
            f'Subscription: {_format_sub(sub)}\n'
            f'Sub ID: <code>{sub.id}</code>',
            parse_mode='html',
            link_preview=False,
        )
        return

    rule = _parse_filter_params(param_text)
    if rule.is_empty:
        await event.respond(
            'ERROR: empty keyword filter.\n\n' + USAGE_HTML,
            parse_mode='html',
            link_preview=False,
        )
        return

    await keyword_filter.set_filter(sub.id, rule)
    logger.info(f'Updated keyword filter for sub {sub.id}')
    await event.respond(
        '<b>Keyword filter updated</b>\n'
        f'Subscription: {_format_sub(sub)}\n'
        f'Sub ID: <code>{sub.id}</code>\n'
        f'<pre>{escape_html(keyword_filter.format_rule(rule))}</pre>',
        parse_mode='html',
        link_preview=False,
    )
