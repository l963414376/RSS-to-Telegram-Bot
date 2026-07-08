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


def _is_zh(lang: Optional[str]) -> bool:
    return bool(lang and lang.lower().startswith('zh'))


def _usage_html(lang: Optional[str]) -> str:
    if _is_zh(lang):
        return (
            '<b>关键词过滤用法</b>\n\n'
            '<b>设置规则</b>\n'
            '<code>/set_filter 订阅ID include=关键词1|关键词2 exclude=排除词1|排除词2 fields=title,summary mode=any</code>\n\n'
            '<b>设置全局默认规则</b>\n'
            '<code>/set_filter default include=关键词1|关键词2 exclude=排除词1 fields=title,summary</code>\n\n'
            '<b>查看规则</b>\n'
            '<code>/set_filter 订阅ID</code>\n'
            '<code>/set_filter default</code>\n\n'
            '<b>清除规则</b>\n'
            '<code>/set_filter 订阅ID off</code>\n'
            '<code>/set_filter default off</code>\n\n'
            '<b>示例</b>\n'
            '<code>/set_filter 123 include=CuCrZr|ODS exclude=battery|catalysis fields=title,summary</code>\n\n'
            '<b>说明</b>\n'
            'include 是必须匹配的关键词；exclude 命中后会跳过文章；'
            'fields 默认是 <code>title,summary</code>；mode 可选 <code>any</code> 或 <code>all</code>。\n'
            '订阅没有单独规则时，会自动使用全局默认规则。'
        )
    return (
        '<b>Keyword filter usage</b>\n\n'
        '<b>Set a rule</b>\n'
        '<code>/set_filter sub_id include=term1|term2 exclude=term3|term4 fields=title,summary mode=any</code>\n\n'
        '<b>Set the global default rule</b>\n'
        '<code>/set_filter default include=term1|term2 exclude=term3 fields=title,summary</code>\n\n'
        '<b>Show a rule</b>\n'
        '<code>/set_filter sub_id</code>\n'
        '<code>/set_filter default</code>\n\n'
        '<b>Clear a rule</b>\n'
        '<code>/set_filter sub_id off</code>\n'
        '<code>/set_filter default off</code>\n\n'
        '<b>Example</b>\n'
        '<code>/set_filter 123 include=CuCrZr|ODS exclude=battery|catalysis fields=title,summary</code>\n\n'
        '<b>Notes</b>\n'
        'include terms are required matches; exclude terms skip matching posts; '
        'fields defaults to <code>title,summary</code>; mode can be <code>any</code> or <code>all</code>.\n'
        'Subscriptions without their own rule automatically use the global default rule.'
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


def _format_rule(rule: keyword_filter.KeywordFilterRule, lang: Optional[str]) -> str:
    if not _is_zh(lang):
        return keyword_filter.format_rule(rule)
    return '\n'.join((
        f'包含关键词: {" | ".join(rule.include) if rule.include else "(空)"}',
        f'排除关键词: {" | ".join(rule.exclude) if rule.exclude else "(空)"}',
        f'匹配字段: {", ".join(rule.fields)}',
        f'匹配模式: {rule.mode}',
    ))


def _format_filter_response(
        sub: db.Sub,
        lang: Optional[str],
        title_zh: str,
        title_en: str,
        body: str = '',
) -> str:
    title = title_zh if _is_zh(lang) else title_en
    subscription_label = '订阅' if _is_zh(lang) else 'Subscription'
    sub_id_label = '订阅 ID' if _is_zh(lang) else 'Sub ID'
    parts = [
        f'<b>{title}</b>',
        f'{subscription_label}: {_format_sub(sub)}',
        f'{sub_id_label}: <code>{sub.id}</code>',
    ]
    if body:
        parts.extend(('', body))
    return '\n'.join(parts)


def _format_default_filter_response(
        lang: Optional[str],
        title_zh: str,
        title_en: str,
        body: str = '',
) -> str:
    title = title_zh if _is_zh(lang) else title_en
    target = '目标: <code>全局默认规则</code>' if _is_zh(lang) else 'Target: <code>Global default rule</code>'
    parts = [f'<b>{title}</b>', target]
    if body:
        parts.extend(('', body))
    return '\n'.join(parts)


def _format_current_filter(
        sub: db.Sub,
        rule: Optional[keyword_filter.KeywordFilterRule],
        lang: Optional[str],
) -> str:
    if rule is None:
        return _format_filter_response(
            sub,
            lang,
            '未设置关键词过滤',
            'Keyword filter is not set',
            _usage_html(lang),
        )
    return _format_filter_response(
        sub,
        lang,
        '当前关键词过滤',
        'Current keyword filter',
        f'<pre>{escape_html(_format_rule(rule, lang))}</pre>',
    )


def _format_current_default_filter(
        rule: Optional[keyword_filter.KeywordFilterRule],
        lang: Optional[str],
) -> str:
    if rule is None:
        return _format_default_filter_response(
            lang,
            '未设置全局默认关键词过滤',
            'Global default keyword filter is not set',
            _usage_html(lang),
        )
    return _format_default_filter_response(
        lang,
        '当前全局默认关键词过滤',
        'Current global default keyword filter',
        f'<pre>{escape_html(_format_rule(rule, lang))}</pre>',
    )


async def _respond_default_filter(
        event: TypeEventMsgHint,
        param_text: str,
        lang: Optional[str],
) -> None:
    if not param_text:
        rule = await keyword_filter.get_default_filter()
        await event.respond(_format_current_default_filter(rule, lang), parse_mode='html', link_preview=False)
        return

    if param_text.lower() in {'off', 'clear', 'disable', 'none'}:
        await keyword_filter.clear_default_filter()
        logger.info('Cleared default keyword filter')
        await event.respond(
            _format_default_filter_response(
                lang,
                '全局默认关键词过滤已清除',
                'Global default keyword filter cleared',
            ),
            parse_mode='html',
            link_preview=False,
        )
        return

    rule = _parse_filter_params(param_text)
    if rule.is_empty:
        await event.respond(
            ('错误：关键词过滤规则为空。\n\n' if _is_zh(lang) else 'ERROR: empty keyword filter.\n\n')
            + _usage_html(lang),
            parse_mode='html',
            link_preview=False,
        )
        return

    await keyword_filter.set_default_filter(rule)
    logger.info('Updated default keyword filter')
    await event.respond(
        _format_default_filter_response(
            lang,
            '全局默认关键词过滤已更新',
            'Global default keyword filter updated',
            f'<pre>{escape_html(_format_rule(rule, lang))}</pre>',
        ),
        parse_mode='html',
        link_preview=False,
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
        await event.respond(_usage_html(lang), parse_mode='html', link_preview=False)
        return

    target = args[1]
    param_text = args[2].strip() if len(args) >= 3 else ''

    if target.lower() in {'default', 'global'}:
        await _respond_default_filter(event, param_text, lang)
        return

    sub = await _get_sub_by_target(chat_id, target)
    if sub is None:
        await event.respond(
            ('ERROR: ' if not _is_zh(lang) else '错误：') + i18n[lang]['subscription_not_exist'],
            parse_mode='html',
        )
        return

    if not param_text:
        rule = await keyword_filter.get_filter(sub.id)
        body_extra = ''
        if rule is None and await keyword_filter.get_default_filter() is not None:
            body_extra = (
                '\n\n当前订阅未设置单独规则，会使用全局默认规则。'
                if _is_zh(lang)
                else '\n\nThis subscription has no own rule and will use the global default rule.'
            )
        await event.respond(
            _format_current_filter(sub, rule, lang) + body_extra,
            parse_mode='html',
            link_preview=False,
        )
        return

    if param_text.lower() in {'off', 'clear', 'disable', 'none'}:
        await keyword_filter.clear_filter(sub.id)
        logger.info(f'Cleared keyword filter for sub {sub.id}')
        await event.respond(
            _format_filter_response(
                sub,
                lang,
                '关键词过滤已清除',
                'Keyword filter cleared',
                (
                    '此订阅之后会使用全局默认规则；如果全局默认规则未设置，则不过滤。'
                    if _is_zh(lang)
                    else 'This subscription will now use the global default rule; if no default is set, it will not be filtered.'
                ),
            ),
            parse_mode='html',
            link_preview=False,
        )
        return

    rule = _parse_filter_params(param_text)
    if rule.is_empty:
        await event.respond(
            ('错误：关键词过滤规则为空。\n\n' if _is_zh(lang) else 'ERROR: empty keyword filter.\n\n')
            + _usage_html(lang),
            parse_mode='html',
            link_preview=False,
        )
        return

    await keyword_filter.set_filter(sub.id, rule)
    logger.info(f'Updated keyword filter for sub {sub.id}')
    await event.respond(
        _format_filter_response(
            sub,
            lang,
            '关键词过滤已更新',
            'Keyword filter updated',
            f'<pre>{escape_html(_format_rule(rule, lang))}</pre>',
        ),
        parse_mode='html',
        link_preview=False,
    )
