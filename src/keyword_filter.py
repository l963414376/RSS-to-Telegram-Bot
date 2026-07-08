#  RSS to Telegram Bot
#  Copyright (C) 2021-2024  Rongrong <i@rong.moe>
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as
#  published by the Free Software Foundation, either version 3 of the
#  License, or (at your option) any later version.

from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from re import IGNORECASE, compile as re_compile, sub as re_sub
from typing import Any, Optional, TYPE_CHECKING
import json

from . import db, log

if TYPE_CHECKING:
    from .parsing.post import Post


logger = log.getLogger('RSStT.keyword_filter')

OPTION_KEY_PREFIX = 'keyword_filter:'
DEFAULT_FIELDS = ('title', 'summary')
VALID_FIELDS = frozenset(('title', 'summary', 'content', 'author', 'tags', 'link'))
VALID_MODES = frozenset(('any', 'all'))


@dataclass(frozen=True)
class KeywordFilterRule:
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    fields: tuple[str, ...] = DEFAULT_FIELDS
    mode: str = 'any'

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> 'KeywordFilterRule':
        include = _normalize_terms(data.get('include'))
        exclude = _normalize_terms(data.get('exclude'))
        fields = _normalize_fields(data.get('fields'))
        mode = str(data.get('mode') or 'any').strip().lower()
        if mode not in VALID_MODES:
            mode = 'any'
        return cls(include=include, exclude=exclude, fields=fields, mode=mode)

    def to_dict(self) -> dict[str, Any]:
        return {
            'include': list(self.include),
            'exclude': list(self.exclude),
            'fields': list(self.fields),
            'mode': self.mode,
        }

    @property
    def is_empty(self) -> bool:
        return not self.include and not self.exclude


def option_key(sub_id: int) -> str:
    return f'{OPTION_KEY_PREFIX}{sub_id}'


def _normalize_terms(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = value.split('|')
    if not isinstance(value, (list, tuple, set)):
        return ()
    terms = []
    seen = set()
    for term in value:
        term = str(term).strip()
        if not term or term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return tuple(terms)


def _normalize_fields(value: Any) -> tuple[str, ...]:
    if value is None:
        return DEFAULT_FIELDS
    if isinstance(value, str):
        value = value.split(',')
    if not isinstance(value, (list, tuple, set)):
        return DEFAULT_FIELDS
    fields = []
    seen = set()
    for field in value:
        field = str(field).strip().lower()
        if field not in VALID_FIELDS or field in seen:
            continue
        seen.add(field)
        fields.append(field)
    return tuple(fields) or DEFAULT_FIELDS


async def get_filter(sub_id: int) -> Optional[KeywordFilterRule]:
    option = await db.Option.get_or_none(key=option_key(sub_id))
    if option is None or not option.value:
        return None
    try:
        data = json.loads(option.value)
        if not isinstance(data, dict):
            raise TypeError('keyword filter option value must be a JSON object')
        rule = KeywordFilterRule.from_mapping(data)
    except Exception as e:
        logger.warning(f'Failed to parse keyword filter for sub {sub_id}', exc_info=e)
        return None
    return None if rule.is_empty else rule


async def set_filter(sub_id: int, rule: KeywordFilterRule) -> None:
    if rule.is_empty:
        await clear_filter(sub_id)
        return
    await db.Option.update_or_create(
        defaults={'value': json.dumps(rule.to_dict(), ensure_ascii=False)},
        key=option_key(sub_id),
    )


async def clear_filter(sub_id: int) -> None:
    await db.Option.filter(key=option_key(sub_id)).delete()


def _strip_html(value: str) -> str:
    value = re_sub(r'<[^>]+>', ' ', value)
    value = unescape(value)
    return re_sub(r'\s+', ' ', value).strip()


def _post_field_value(post: 'Post', field: str) -> str:
    if field == 'title':
        return post.title or ''
    if field in {'summary', 'content'}:
        return post.html or ''
    if field == 'author':
        return post.author or ''
    if field == 'tags':
        return ' '.join(post.tags or [])
    if field == 'link':
        return post.link or ''
    return ''


def build_match_text(post: 'Post', fields: tuple[str, ...] = DEFAULT_FIELDS) -> str:
    return '\n'.join(
        _strip_html(_post_field_value(post, field))
        for field in fields
        if field in VALID_FIELDS
    )


def _term_matches(term: str, text: str, text_lower: str) -> bool:
    if term.startswith('re:'):
        pattern = term[3:].strip()
        if not pattern:
            return False
        try:
            return re_compile(pattern, IGNORECASE).search(text) is not None
        except Exception as e:
            logger.warning(f'Invalid keyword filter regex: {pattern}', exc_info=e)
            return False
    return term.lower() in text_lower


def matches_rule(rule: KeywordFilterRule, post: 'Post') -> bool:
    text = build_match_text(post, rule.fields)
    text_lower = text.lower()

    if any(_term_matches(term, text, text_lower) for term in rule.exclude):
        return False

    if not rule.include:
        return True

    include_matches = [_term_matches(term, text, text_lower) for term in rule.include]
    if rule.mode == 'all':
        return all(include_matches)
    return any(include_matches)


async def post_matches_filter(sub: db.Sub, post: 'Post') -> bool:
    try:
        rule = await get_filter(sub.id)
        if rule is None:
            return True
        matched = matches_rule(rule, post)
        if not matched:
            logger.debug(f'Post {post.link} skipped by keyword filter of sub {sub.id}')
        return matched
    except Exception as e:
        logger.error(f'Keyword filter failed for sub {sub.id}; sending post without filtering', exc_info=e)
        return True


def format_rule(rule: KeywordFilterRule) -> str:
    lines = [
        f'include: {" | ".join(rule.include) if rule.include else "(empty)"}',
        f'exclude: {" | ".join(rule.exclude) if rule.exclude else "(empty)"}',
        f'fields: {", ".join(rule.fields)}',
        f'mode: {rule.mode}',
    ]
    return '\n'.join(lines)
