# 任务书：RSS 订阅关键词过滤与 Telegram 定向推送

## 1. 任务背景

当前仓库是从 `Rongronggg9/RSS-to-Telegram-Bot` fork 得到的 RSS 到 Telegram 推送系统。上游已经具备 RSS/Atom 抓取、订阅管理、去重、定时轮询、Telegram 推送、富文本格式、媒体处理、OPML 导入导出和 Docker 部署能力。

本任务不重写上述能力，只在现有推送链路中增加一层“关键词过滤”。目标是让用户订阅任意 RSS 或由 RSSHub/RSSBridge 生成的 feed 后，可以为该订阅设置关键词规则；只有新文章命中关键词规则时才推送到 Telegram。

## 2. 总目标

实现一个轻量、可维护、低侵入的关键词过滤功能：

```text
RSS feed 新条目
    ↓
上游 RSStT 正常解析为 Post
    ↓
读取该订阅的关键词过滤规则
    ↓
命中规则：发送到 Telegram
未命中规则：静默跳过
```

功能完成后，用户可以这样使用：

```text
/sub https://www.nature.com/nmat.rss
/set_filter https://www.nature.com/nmat.rss include=CuCrZr|oxide dispersion strengthened|graphene copper exclude=battery|catalysis fields=title,summary mode=any
```

## 3. 基本原则

1. 不重复造轮子：不重写 RSS 抓取、Telegram 发送、订阅管理、定时任务、去重、消息格式化。
2. 最小侵入：尽量只新增独立模块，并在发送前增加一个过滤判断。
3. 避免数据库迁移：第一版不修改 `Sub` 表结构，不新增迁移文件。
4. 保持上游可同步：改动范围要小，避免大规模重构上游代码。
5. 默认安全：如果某个订阅没有设置过滤规则，保持上游原行为，正常推送所有新条目。
6. 过滤失败不应阻塞主流程：规则 JSON 损坏或正则错误时，应记录日志并采用保守策略，不让 bot 崩溃。
7. 不做材料专用：功能必须通用，适用于任意学科、任意期刊、任意 RSS 源。

## 4. 功能范围

### 4.1 必须实现

#### 4.1.1 每个订阅独立过滤规则

每个 `Sub` 可以单独设置一个过滤规则。规则只影响当前订阅，不影响同一 feed 的其他订阅者。

#### 4.1.2 include 关键词

`include` 表示白名单关键词。

规则：

- 如果 `include` 为空，则不要求白名单命中。
- 如果 `include` 非空，则必须命中 include 才允许推送。
- 默认 `mode=any`，即任意一个 include 命中即可。
- `mode=all` 时，所有 include 都必须命中。

#### 4.1.3 exclude 关键词

`exclude` 表示黑名单关键词。

规则：

- 如果任意 exclude 命中，直接跳过，不推送。
- exclude 优先级高于 include。

#### 4.1.4 匹配字段

支持以下字段：

```text
title
summary
content
author
tags
link
```

第一版默认字段：

```text
title,summary
```

说明：

- `summary` 和 `content` 在实现上可以都映射到 `Post.html`，后续再细分。
- `tags` 来自 `Post.tags`。
- 字段不合法时忽略，不应报错退出。

#### 4.1.5 普通关键词匹配

普通关键词采用：

- 大小写不敏感；
- 子串匹配；
- HTML 标签去除后匹配；
- Unicode 原样保留。

#### 4.1.6 正则关键词匹配

以 `re:` 开头的 term 作为正则表达式。

示例：

```text
re:\bCu[- ]?Cr[- ]?Zr\b
```

要求：

- 大小写不敏感；
- 正则编译失败时，该 term 视为不命中，并记录 warning 日志；
- 不能因为一条坏正则导致整个 bot 崩溃。

#### 4.1.7 Telegram 命令 `/set_filter`

新增命令：

```text
/set_filter <feed_url_or_sub_id> include=term1|term2 exclude=term3|term4 fields=title,summary mode=any
```

用法一：设置过滤规则

```text
/set_filter https://www.nature.com/nmat.rss include=CuCrZr|ODS|graphene copper exclude=battery|catalysis fields=title,summary mode=any
```

用法二：查看过滤规则

```text
/set_filter https://www.nature.com/nmat.rss
```

用法三：清除过滤规则

```text
/set_filter https://www.nature.com/nmat.rss off
```

用法四：通过订阅 ID 设置

```text
/set_filter 123 include=Ga2O3|gallium oxide exclude=photocatalysis fields=title,summary
```

#### 4.1.8 帮助文档

新增或更新文档，至少说明：

- 功能作用；
- 命令格式；
- include/exclude/mode/fields 含义；
- 普通关键词和正则关键词写法；
- 期刊 RSS 示例；
- 关闭过滤规则的方法。

### 4.2 暂不实现

以下内容不在本任务范围内：

1. Web 前端。
2. 大模型摘要或语义匹配。
3. 复杂打分系统。
4. 全局用户默认过滤规则。
5. 按期刊分组的图形化管理。
6. 自动发现期刊 RSS。
7. 从普通网页自动推断 RSS。
8. 邮件提醒解析。
9. Web of Science、Google Scholar、ScienceDirect 邮件接入。
10. 修改 Telegram 消息格式为论文日报。
11. 数据库表结构迁移。
12. 合并回上游。

这些可以后续再做，但本任务不做。

## 5. 数据存储设计

第一版不新增数据库字段，不新增迁移文件。使用现有 `Option` 表存储过滤规则。

key 格式：

```text
keyword_filter:<sub_id>
```

value 格式为 JSON 字符串：

```json
{
  "include": ["CuCrZr", "oxide dispersion strengthened"],
  "exclude": ["battery", "catalysis"],
  "fields": ["title", "summary"],
  "mode": "any"
}
```

清除过滤规则时，建议将对应 `Option` 记录删除；如果删除不方便，也可以写入空规则：

```json
{
  "include": [],
  "exclude": [],
  "fields": ["title", "summary"],
  "mode": "any"
}
```

但更推荐删除记录，便于判断“未设置过滤规则”。

## 6. 建议改动文件

### 6.1 新增 `src/keyword_filter.py`

职责：

- 定义过滤规则解析；
- 从 `Option` 表读取/写入/删除规则；
- 对 `Post` 执行匹配；
- 处理 HTML 去标签；
- 处理普通关键词和正则关键词；
- 提供命令层可调用的格式化输出。

建议接口：

```python
async def get_filter(sub_id: int) -> KeywordFilterRule | None:
    ...

async def set_filter(sub_id: int, rule: KeywordFilterRule) -> None:
    ...

async def clear_filter(sub_id: int) -> None:
    ...

async def post_matches_filter(sub: db.Sub, post: Post) -> bool:
    ...
```

### 6.2 修改 `src/monitor/_notifier.py`

在 `_notify_sub_with_entry_idx` 中增加过滤判断。

当前逻辑类似：

```python
post = await self._get_post(idx)
if post:
    await self._do_send(sub, post)
```

改为：

```python
post = await self._get_post(idx)
if post and await keyword_filter.post_matches_filter(sub, post):
    await self._do_send(sub, post)
```

要求：

- 没有过滤规则时返回 True，保持原行为；
- 过滤规则存在但不命中时返回 False，静默跳过；
- 过滤模块异常时记录日志，默认返回 True 或 False 需要明确。建议返回 True，避免误删用户原始推送；但错误日志必须可见。

### 6.3 新增或修改命令文件

可选方案：

1. 新增 `src/command/filter.py`；
2. 或在 `src/command/customization.py` 中加入命令。

推荐新增 `src/command/filter.py`，避免污染上游已有 customization 逻辑。

命令函数：

```python
cmd_set_filter(...)
```

职责：

- 解析 `/set_filter` 命令；
- 根据 feed URL 或 sub_id 找到当前 chat/user 的订阅；
- 设置、查看或清除过滤规则；
- 返回用户可读的 Telegram HTML 消息。

### 6.4 修改 `src/command/__init__.py`

加入：

```python
from . import filter
```

或在原有 import 列表中加入 `filter` 模块。

### 6.5 修改 `src/entrypoint.py`

注册 `/set_filter` 命令。

建议 pattern：

```python
bot.add_event_handler(command.filter.cmd_set_filter,
                      events.NewMessage(pattern=construct_remote_command_matcher('/set_filter')))
```

如需带参数匹配，可以参考 `/set_title`、`/set_interval` 等命令注册方式。

### 6.6 更新 i18n

为了降低第一版复杂度，可以先在命令响应中直接使用英文或中文硬编码提示。但更推荐至少更新：

```text
src/i18n/en.json
src/i18n/zh-Hans.json
```

新增键：

```text
cmd_description_set_filter
keyword_filter_usage_html
keyword_filter_updated
keyword_filter_cleared
keyword_filter_current
keyword_filter_not_found
keyword_filter_invalid
```

如果全量多语言维护成本太高，第一版可以依赖 fallback，但不能导致启动时报缺 key。

## 7. 命令解析规则

### 7.1 参数格式

基础格式：

```text
/set_filter <target> [off]
/set_filter <target> include=... exclude=... fields=... mode=...
```

其中 `<target>` 可以是：

1. 订阅 ID；
2. feed URL。

### 7.2 include/exclude 分隔符

多个 term 使用 `|` 分隔：

```text
include=CuCrZr|ODS|graphene copper
exclude=battery|catalysis
```

term 前后空格应自动去掉。

### 7.3 fields 分隔符

fields 使用逗号分隔：

```text
fields=title,summary
```

非法字段忽略。如果全部非法，使用默认字段：

```text
title,summary
```

### 7.4 mode

支持：

```text
any
all
```

非法 mode 使用 `any`。

### 7.5 空 include

允许只设置 exclude：

```text
/set_filter 123 exclude=battery|catalysis
```

含义：所有新条目默认通过，但命中 exclude 的跳过。

### 7.6 空 exclude

允许只设置 include：

```text
/set_filter 123 include=CuCrZr|ODS
```

含义：只有命中 include 的才推送。

## 8. 匹配文本构造

从 `Post` 构造匹配文本。

字段映射建议：

```text
title   -> post.title
summary -> post.html
content -> post.html
author  -> post.author
tags    -> " ".join(post.tags or [])
link    -> post.link
```

处理规则：

- `None` 转为空字符串；
- HTML 去标签；
- HTML 实体可选反转义；
- 多字段用换行拼接；
- 最终统一转小写用于普通关键词匹配。

## 9. 日志要求

至少记录以下情况：

1. 过滤规则 JSON 解析失败；
2. 正则表达式编译失败；
3. 某条文章被过滤跳过，debug 级别即可；
4. 命令设置过滤规则成功；
5. 命令清除过滤规则成功。

避免在 info 级别打印过多文章内容。

## 10. 测试要求

如果仓库现有测试体系容易接入，新增单元测试：

```text
tests/test_keyword_filter.py
```

至少覆盖：

1. 无过滤规则时返回 True；
2. include 命中返回 True；
3. include 未命中返回 False；
4. exclude 命中返回 False；
5. exclude 优先于 include；
6. mode=all 时必须全部命中；
7. `re:` 正则命中；
8. 坏正则不崩溃；
9. HTML 标签不影响关键词匹配；
10. fields 只匹配指定字段。

如果暂时不接入测试框架，至少提供一个独立 dry-run 说明或开发者手动测试步骤。

## 11. 验收标准

任务完成后，必须满足以下验收条件：

### 11.1 基础订阅不受影响

未设置过滤规则的订阅，行为与上游一致，所有新条目照常推送。

### 11.2 include 生效

设置：

```text
include=CuCrZr|ODS
```

只有标题或摘要中包含 `CuCrZr` 或 `ODS` 的文章被推送。

### 11.3 exclude 生效

设置：

```text
exclude=battery|catalysis
```

命中 battery 或 catalysis 的文章不推送。

### 11.4 include 和 exclude 同时生效

设置：

```text
include=copper exclude=battery
```

包含 copper 且不包含 battery 的文章才推送。

### 11.5 正则生效

设置：

```text
include=re:\bCu[- ]?Cr[- ]?Zr\b
```

能匹配 `CuCrZr`、`Cu-Cr-Zr`、`Cu Cr Zr`。

### 11.6 命令可用

以下命令均可用：

```text
/set_filter <target> include=...
/set_filter <target>
/set_filter <target> off
```

### 11.7 不破坏上游部署

Docker Compose、PyPI/源码运行方式不因本任务改动而失效。

### 11.8 不新增复杂依赖

第一版尽量不新增第三方依赖。若必须新增，需说明理由。

## 12. 用户只需要做的事情

用户不需要改代码。用户只需要：

1. 准备 Telegram bot token；
2. 准备 Telegram user ID；
3. 部署 fork 仓库；
4. 用 `/sub` 添加 RSS；
5. 用 `/set_filter` 设置关键词规则。

## 13. 推荐实现顺序

虽然任务不拆成长期阶段，但实现时建议按以下顺序一次性完成：

1. 新增 `src/keyword_filter.py`；
2. 在 `_notifier.py` 中插入过滤判断；
3. 新增 `/set_filter` 命令；
4. 注册命令；
5. 更新文档；
6. 增加测试或手动测试说明；
7. 提交一个完整 commit。

## 14. 不接受的实现

以下实现不接受：

1. 重写 RSS 抓取逻辑；
2. 重写 Telegram 发送逻辑；
3. 把材料领域关键词写死到代码；
4. 用大模型判断相关性作为第一版核心逻辑；
5. 修改大量上游文件导致后续难以同步；
6. 强制所有订阅必须设置关键词；
7. 关键词不命中却仍然推送；
8. 正则错误导致 bot 崩溃；
9. 为第一版引入复杂数据库迁移；
10. 把 bot 改成只适合期刊论文，失去通用 RSS 能力。

## 15. 最终交付物

本任务完成后，应至少包含：

```text
src/keyword_filter.py
src/command/filter.py
src/monitor/_notifier.py 修改
src/command/__init__.py 修改
src/entrypoint.py 修改
docs/keyword-filter.md 更新或补充
README 或 FAQ 中增加简短入口说明
```

如有测试：

```text
tests/test_keyword_filter.py
```

## 16. 备注

本 fork 的定位不是替代 RSStT，而是在 RSStT 上增加“面向任意 RSS/期刊源的关键词定向推送”。保持小改动、可同步、可部署，比做成独立大项目更重要。
