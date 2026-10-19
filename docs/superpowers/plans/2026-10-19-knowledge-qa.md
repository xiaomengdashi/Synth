# SynthAI 全库 AI 问答 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 在 SynthAI 中交付仅管理员可用、附可核对正文引用、可保存历史和连续追问的全库问答。

**Architecture:** SQLite 保存会话、轮次和正文片段，FTS5 负责中英文段落召回。每次提问前分批同步所有新增或变化文章，完成检索后释放数据库事务，再用现有服务端模型配置生成答案。前端使用独立问答模块和按会话 ID 隔离的请求状态，接入现有前后台导航。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy async、SQLite FTS5、BeautifulSoup、现有 httpx 模型客户端；React 18、TypeScript、Zustand、React Markdown、现有后台主题。

**Spec:** `docs/superpowers/specs/2026-10-19-knowledge-qa-design.md`

## Global Constraints

- 仅管理员使用，沿用现有后台访问令牌和模型服务配置。
- 首版使用本地文本检索，不要求另外配置 Embedding 模型或搜索服务。
- 页面路由为 `/admin/ask`，API 统一前缀 `/api/v1/knowledge`。
- 分段目标 900 字符，硬上限 1,200 字符，相邻段最多重叠 120 字符。
- 查询词上限 48 个，候选片段最多 60 个，采用片段最多 12 个、每篇最多 3 个。
- 正文上下文总上限 14,400 字符，历史对话最多最近 6 轮且总上限 8,000 字符，当前问题上限 2,000 字符。
- 回答输出上限为 `min(4096, 后台 llmMaxTokens)`，温度 0.2，超时沿用后台配置。
- 当前单进程部署使用进程内锁；模型调用期间不持有 SQLite 事务或索引锁。
- 仅模型生成读取服务端密钥；客户端不能覆盖 Base URL、API Key 或模型。
- 未找到资料不调用回答模型；模型返回无效引用、损坏 JSON、空答案时不保存正常答案。
- 所有测试使用临时数据库和模型替身；真实模型检查只使用已入库资料。
- Python 命令以仓库内 `backend/.venv/bin/python` 为准，pytest 从 `backend` 目录执行。

## Review Focus

1. 标题和摘要均无关键词、仅陈旧文章末段含中文词：仍能召回，不能只扫描最新文章或正文前缀。由任务 3 测试覆盖。
2. Markdown 代码中的 `[1]`、已有链接中的 `[1]`：保持代码与原链接，只把普通正文的合法编号变成引用。由任务 6 测试覆盖。
3. 文章在生成期间被删除：本轮使用已检索快照，历史引用保留、文章链接禁用；下一轮不得再召回。由任务 5 测试覆盖。
4. 模型错误包含 API Key、Base URL 或 HTML：页面与会话只收到固定中文错误，不暴露原始响应。由任务 5 测试覆盖。
5. 用户在 A 会话等待回答时切到 B：结果只更新 A，B 的输入和消息不受影响。由任务 6 测试和任务 7 浏览器验证覆盖。

## File Structure

| 文件 | 职责 |
| --- | --- |
| `backend/app/models/knowledge.py` | 四类 ORM 模型和唯一约束 |
| `backend/app/services/knowledge_index.py` | FTS 建表、启动恢复、增量同步；从检索模块拆出数据库维护，避免文件过大 |
| `backend/app/services/knowledge_retrieval.py` | 正文提取、分段、分词、查询、召回排序 |
| `backend/app/services/knowledge_qa.py` | 上下文预算、提示词、调用模型、引用验证 |
| `backend/app/routers/knowledge.py` | 鉴权、会话接口、去重、并发、失败状态 |
| `backend/app/models/__init__.py`、`database.py`、`backend/main.py` | 模型注册、索引启动初始化和 API 注册 |
| `backend/tests/test_knowledge_{storage,retrieval,index,qa,api}.py` | 对应后端行为验证 |
| `frontend/src/features/knowledge/types.ts`、`client.ts` | API 数据契约和带令牌请求 |
| `frontend/src/features/knowledge/lib/conversationState.ts` | 按会话隔离的纯状态更新，处理过期响应 |
| `frontend/src/features/knowledge/lib/citations.ts` | Markdown AST 中的合法编号引用转换 |
| `frontend/src/features/knowledge/lib/*.test.ts` | 会话竞态、引用代码保护和状态验证 |
| `frontend/src/features/knowledge/knowledgeStore.ts` | 请求生命周期和会话缓存，页面卸载后仍能接收结果 |
| `frontend/src/features/knowledge/components/KnowledgeAnswer.tsx` | 答案、引用定位、正文快照 |
| `frontend/src/features/knowledge/pages/AdminKnowledge.tsx` | 会话列表、对话和输入交互 |
| `frontend/src/features/knowledge/knowledge.css` | 响应式布局，使用现有 `--ac-*` 主题变量 |
| `frontend/src/App.tsx`、`components/AdminLayout.tsx`、`components/Layout.tsx` | 路由与可见入口 |
| `frontend/package.json`、`README.md` | 纳入测试目录，记录功能入口和检索边界 |

## Shared Data Contract

- `RetrievedChunk`：Python frozen dataclass，字段 `chunk_id: int`、`article_id: str`、`title: str`、`source_type: str`、`text: str`、`article_updated_at: str`。
- `KnowledgeSource`：JSON 对象，字段 `number: int`、`article_id: str`、`title: str`、`source_type: str`、`excerpt: str`、`article_updated_at: str`、`article_exists: bool`。存储时保留正文快照，读取时重新计算存在状态。
- `KnowledgeAnswer`：Python dataclass，字段 `answer: str`、`insufficient_evidence: bool`、`sources: list[dict]`。
- `KnowledgeTurn` API 对象：`id`、`conversation_id`、`request_id`、`question`、`answer`、`status`、`insufficient_evidence`、`sources`、`error_message`、`created_at`、`completed_at`。
- `ConversationSummary`：`id`、`title`、`created_at`、`updated_at`。列表响应 `{total, data}`，详情响应 `{conversation, turns}`，生成响应为一个 `KnowledgeTurn`。
- 前端 `ConversationDetail = {conversation: ConversationSummary; turns: KnowledgeTurn[]}`；`ConversationCache = Record<string, ConversationDetail & {lastMutationAt: number}>`，`lastMutationAt` 使用本地毫秒时间，仅用于排除早于本地完成响应的旧快照。
- `KnowledgeStatus`：`model_configured`、`index_available`、`article_count`、`indexed_count`、`unsearchable_count`、`message`；不返回任何密钥。

---

### Task 1: 建立持久化模型和幂等启动初始化

**Files:** Create `backend/app/models/knowledge.py`, `backend/app/services/knowledge_index.py`, `backend/tests/test_knowledge_storage.py`; modify `backend/app/models/__init__.py`, `backend/app/database.py`。

**Interfaces:**
- Consumes: `Base`, `AsyncSession`, `AsyncConnection` 和现有 `Article`。
- Produces: `KnowledgeConversation`, `KnowledgeTurn`, `KnowledgeIndexedArticle`, `KnowledgeChunk`；`initialize_knowledge(connection: AsyncConnection) -> bool`，创建 FTS 表并将遗留 pending 轮次转为 interrupted。

- [x] **Step 1:** 编写临时数据库测试：`test_create_all_registers_knowledge_tables` 断言四张 ORM 表存在；`test_request_id_unique_per_conversation` 断言同会话重复 request_id 违反唯一约束、不同会话允许；`test_startup_recovers_pending_once` 断言连续初始化两次后仅 pending 变为 interrupted、completed 不变；`test_missing_fts_keeps_core_database_usable` 模拟 `no such module: fts5`，断言初始化返回 false、文章仍能读写。
- [x] **Step 2:** 从 `backend` 运行 `.venv/bin/python -m pytest tests/test_knowledge_storage.py -q`，预期因模型和初始化入口尚不存在而失败。
- [x] **Step 3:** 实现四类模型。会话标题默认「新会话」，轮次状态使用 spec 的四个字符串；sources 存 Text JSON；片段整数主键，文章 ID + 序号唯一；indexed article 保存内容摘要、算法版本、索引状态、文章更新时间。FTS 建表 `fts5(title_tokens, body_tokens)`；只对明确缺失 FTS 的错误降级，不吞掉其他数据库错误。`init_db` 在模型建表后调用初始化，保留现有文章迁移和索引。
- [x] **Step 4:** 重跑同一测试文件，预期全部通过；确认初始化未触达真实运行库。
- [x] **Step 5:** 仅提交本任务文件，提交信息 `feat: persist knowledge conversations and search index`。

### Task 2: 实现跨平台正文、完整分段和中英文词元

**Files:** Create `backend/app/services/knowledge_retrieval.py`, `backend/tests/test_knowledge_retrieval.py`。

**Interfaces:**
- Consumes: `extract_note_body(content_md: str) -> str`，不修改导出接口原行为。
- Produces: `extract_search_text(content_md: str) -> str`、`split_chunks(text: str) -> list[str]`、`tokenize(text: str, *, query: bool = False) -> list[str]`、`build_match_query(tokens: list[str]) -> str`、`RetrievedChunk` dataclass。

- [x] **Step 1:** 编写测试：`test_platform_bodies_extract_without_scripts_or_markers` 覆盖 HTML、X Article、X tweet、普通 Markdown；`test_corrupt_payload_has_no_summary_substitute` 断言损坏块返回空；`test_chunks_preserve_tail_and_respect_budget` 断言全部片段 `len <= 1200` 且超长文章尾部标记仍存在；`test_tokens_match_chinese_and_english` 断言中文双字、单字和小写英文词可查询；`test_query_operators_are_literal_and_tokens_bounded` 断言 `OR`, 引号、星号和冒号不会变成用户控制的 MATCH 运算，问题词不超过 48。
- [x] **Step 2:** 运行 `.venv/bin/python -m pytest tests/test_knowledge_retrieval.py -q`，预期缺失入口失败。
- [x] **Step 3:** 按接口实现纯函数。清理 HTML 时先移除 script/style；必要时在调用现有提取入口前净化富内容内 HTML，避免先变纯文本后无法识别样式内容。段落不足则聚合至目标，超长句仍切分，不截断全文；词元按稳定顺序去重，问句停用词仅作用于 query。片段去重保留第一次出现的正文。
- [x] **Step 4:** 重跑该文件，预期通过；再运行 `tests/test_note_export.py`，确保共用入口未引入导出回归。
- [x] **Step 5:** 提交本任务文件，信息 `feat: extract and tokenize knowledge article chunks`。

### Task 3: 实现增量索引、BM25 召回和追问检索

**Files:** Modify `backend/app/services/knowledge_index.py`, `backend/app/services/knowledge_retrieval.py`; create `backend/tests/test_knowledge_index.py`。

**Interfaces:**
- Consumes: 任务 1 模型和初始化、任务 2 纯函数。
- Produces: `sync_knowledge_index(db: AsyncSession) -> None`；`retrieve_chunks(db: AsyncSession, question: str, *, previous_questions: list[str], previous_article_ids: list[str]) -> list[RetrievedChunk]`；`get_index_status(db: AsyncSession) -> dict`，返回 Shared Data Contract 的索引计数字段。

- [x] **Step 1:** 编写临时库测试：`test_body_only_match_in_old_article_tail` 插入超过 60 篇较新无关文章，旧文章尾段含「量化缓存」而标题摘要不含，断言能召回；`test_sync_add_edit_delete_and_version_rebuild` 断言新增、正文/标题更新、删除、算法版本改变后 FTS 与片段一致；`test_empty_or_corrupt_bodies_count_unsearchable` 断言不以摘要充数；`test_follow_up_reuses_topic_without_overriding_new_question` 覆盖「再讲详细些」与新主题切换；`test_retrieval_limits_and_diversifies_sources` 断言最多 12 个、每篇最多 3 个、正文字符和不超过 14400；`test_database_is_released_before_model_stage` 断言检索返回后无开放事务。
- [x] **Step 2:** 运行 `.venv/bin/python -m pytest tests/test_knowledge_index.py -q`，预期缺少同步与检索实现失败。
- [x] **Step 3:** 使用进程内索引锁，全库读取 ID/更新时间后按 64 篇分批加载变化正文；线程完成提取和分词，短事务替换片段与 FTS 行，保存内容摘要和算法版本。已删文章一并移除。参数化查询 `bm25(knowledge_chunks_fts, 4.0, 1.0)` 获取当前问题优先候选，历史词和此前文章在需要时补位；有新问题关键词时不让历史无关文章压过当前主题。FTS 查询失败则本轮失败，不静默退化到最新文章。
- [x] **Step 4:** 重跑 tasks 1–3 的三个测试文件，预期全部通过；无变化同步断言不重复写片段，避免每轮重建。
- [x] **Step 5:** 提交，信息 `feat: retrieve evidence from the complete article library`。

### Task 4: 实现带引用的回答和可控模型调用

**Files:** Create `backend/app/services/knowledge_qa.py`, `backend/tests/test_knowledge_qa.py`。

**Interfaces:**
- Consumes: `RetrievedChunk`、现有 `chat_completion(messages, config, *, temperature, max_tokens, timeout)`。
- Produces: `KnowledgeAnswer` dataclass；`generate_knowledge_answer(question: str, chunks: list[RetrievedChunk], history: list[dict], config: dict) -> KnowledgeAnswer`（async）；`KnowledgeAnswerError`（固定中文错误）；`parse_answer(raw: str, chunks: list[RetrievedChunk]) -> KnowledgeAnswer`。

- [x] **Step 1:** 模型替身测试 `test_no_chunks_returns_insufficient_without_call` 断言调用数 0；`test_valid_citations_use_server_snapshots` 断言 `[2]` 只返回服务器第 2 段来源，不信任模型额外字段；`test_rejects_missing_unknown_or_malformed_citations` 覆盖未引用、`[999]`、损坏 JSON、空输出和非布尔 insufficient 标记；`test_history_and_context_budgets` 断言仅最近 6 轮、历史 <= 8000、资料 <= 14400；`test_model_request_uses_bounded_generation` 断言温度 0.2、tokens 不超过 min(4096, 配置值)，不修改现有摘要生成参数。
- [x] **Step 2:** 运行 `.venv/bin/python -m pytest tests/test_knowledge_qa.py -q`，预期入口缺失失败。
- [x] **Step 3:** 实现按问题、历史和资料划分的提示词；资料使用 JSON 编码，标为不可信引用材料，不执行其内指令。模型只产 answer/insufficient_evidence，服务端构建 number 与正文快照。解析可剥代码围栏；仅不足结果可无引用，所有出现的编号必须有效。使用后台配置的超时时间包裹 `asyncio.timeout`，约束完整模型阶段并保留可识别的 TimeoutError；其余异常转换为受控错误，不再次调用模型修复输出。
- [x] **Step 4:** 重跑该文件，预期通过；检查提示词没有密钥、代理和内部配置字段。
- [x] **Step 5:** 提交，信息 `feat: generate grounded answers with validated citations`。

### Task 5: 接通受保护的会话 API、幂等和失败恢复

**Files:** Create `backend/app/routers/knowledge.py`, `backend/tests/test_knowledge_api.py`; modify `backend/main.py`。

**Interfaces:**
- Consumes: tasks 1–4，`get_db`、`load_settings`、`get_admin_token_hash`、`require_admin`、`jsonable_local`。
- Produces: spec 第 8 节全部六类路由和 Shared Data Contract；`require_knowledge_admin` 先要求令牌已初始化，再验证现有令牌；受控异常带恰当 HTTP 状态。

- [x] **Step 1:** 添加测试 `test_knowledge_requires_initialized_admin_on_every_endpoint`（未初始化 503、错误/缺令牌 401）；`test_conversations_survive_reload_and_delete_explicitly`（创建、列表分页、读历史、删除轮次）；`test_same_request_generates_once`（completed 重放不再调用、失败重放不重试）；`test_busy_conversation_rejects_send_and_delete`（并发请求/删除 409，不同会话独立）；`test_deleted_during_generation_keeps_source_snapshot`（快照保留、article_exists=false、下轮不召回）；`test_model_errors_are_sanitized_and_pending_recovers`（密钥诱饵不在响应/存储中，failed/interrupted 合法）；`test_unknown_conversation_and_question_validation`（404、trim 后非空、最大 2000）；`test_status_exposes_counts_without_credentials`。
- [x] **Step 2:** 运行 `.venv/bin/python -m pytest tests/test_knowledge_api.py -q`，预期路由尚未定义失败。
- [x] **Step 3:** 实现路由。生成前保存 pending 并提交，检索与模型分开事务；已有同 request_id 先处理重放再判断忙。同会话锁覆盖发送和删除；finally 释放锁；cancelled 使用短清理事务标 interrupted 后重新抛取消。失败以固定中文映射 502/504，FTS/模型未配置为 503；completed/failed 更新会话时间。history 仅取成功轮次，source.exists 在序列化时检查实际文章。用主程序注册知识路由，不更改其他路由鉴权行为。
- [x] **Step 4:** 运行 `.venv/bin/python -m pytest tests/test_knowledge_api.py tests/test_knowledge_qa.py tests/test_knowledge_index.py tests/test_admin_guards.py -q`，预期通过；使用替身确认一次请求仅触发允许的模型调用。
- [x] **Step 5:** 提交，信息 `feat: expose authenticated knowledge conversations`。

### Task 6: 建立前端契约、引用渲染和会话隔离状态

**Files:** Create `frontend/src/features/knowledge/{types.ts,client.ts,knowledgeStore.ts}`, `frontend/src/features/knowledge/lib/{citations.ts,citations.test.ts,conversationState.ts,conversationState.test.ts}`; modify `frontend/package.json`。

**Interfaces:**
- Consumes: 任务 5 API，`adminFetch`。
- Produces: `knowledgeClient.status(): Promise<KnowledgeStatus>`、`list(limit: number, offset: number): Promise<{total: number; data: ConversationSummary[]}>`、`create(): Promise<ConversationSummary>`、`get(id: string): Promise<ConversationDetail>`、`remove(id: string): Promise<void>`、`send(id: string, question: string, requestId: string): Promise<KnowledgeTurn>`。
- Produces: `useKnowledgeStore` 暴露 `conversations`, `total`, `byId: ConversationCache`, `pendingById`, `errorsById`；异步动作 `loadList(reset: boolean)`, `createConversation(): Promise<string>`, `loadConversation(id: string)`, `deleteConversation(id: string)`, `sendQuestion(id: string, question: string)`。
- Produces: `mergeTurn(cache: ConversationCache, conversationId: string, turn: KnowledgeTurn, receivedAt: number): ConversationCache`、`applyConversationSnapshot(cache: ConversationCache, snapshot: ConversationDetail, startedAt: number): ConversationCache`；`remarkKnowledgeCitations(options: {turnId: string; numbers: number[]})` 返回兼容 remark 的 AST transformer。

- [x] **Step 1:** 添加 Node 测试 `completion_for_a_does_not_mutate_b_or_draft`（A 完成只改 A）；`stale_snapshot_preserves_newer_completed_turn`（旧详情响应不得覆盖新答案）；`duplicate_completion_upserts_by_turn_id`（不重复消息）；`citations_skip_code_existing_links_and_invalid_numbers`（普通合法编号有定位链接，代码块/行内代码/已有链接/非法编号保持原状）；`same_turn_numbers_have_unique_anchor_ids`（不同轮次 `[1]` 不冲突）。
- [x] **Step 2:** 从 `frontend` 运行 `node --experimental-strip-types --test src/features/knowledge/lib/*.test.ts`，预期模块缺失失败。
- [x] **Step 3:** 实现纯更新函数与 Markdown AST 访问器，跳过 link/code/inlineCode/image 节点；仅为服务器返回的有效编号插入本页 anchor。API 客户端统一解析受控错误与状态码；生成请求不自动重试。store 按 conversation ID 保存请求 promise 与 pending 状态，页面切换不取消另一个会话生成；新建和发送请求失败均保留可恢复输入。request_id 使用 `crypto.randomUUID()`；显式重试生成新 ID。npm test 脚本纳入新 lib 目录。
- [x] **Step 4:** 运行 `npm test` 与 `npm run build`，预期测试和类型构建通过；新增文件不引入依赖包。
- [x] **Step 5:** 提交，信息 `feat: manage knowledge chat state and citation rendering`。

### Task 7: 交付问答页面、入口和端到端验证

**Files:** Create `frontend/src/features/knowledge/pages/AdminKnowledge.tsx`, `frontend/src/features/knowledge/components/KnowledgeAnswer.tsx`, `frontend/src/features/knowledge/knowledge.css`; modify `frontend/src/App.tsx`, `frontend/src/components/AdminLayout.tsx`, `frontend/src/components/Layout.tsx`, `README.md`。

**Interfaces:**
- Consumes: 任务 6 store、引用插件和类型，现有 `useVerifiedAdminToken`、`ConfirmDialog`、后台样式变量。
- Produces: `/admin/ask` 页面；后台「知识库问答」入口；前台仅 verified 管理员可见的相同入口。

- [x] **Step 1:** 完成页面与组件：桌面双栏、手机会话折叠；历史会话分批加载并保留总数；question 输入、发送中状态、失败重试、创建/删除、引用定位与文章新标签页。已删文章禁用跳转但保留快照。资料不足沿用服务端说明。未配置模型链接 `/admin/model`，未初始化令牌链接 `/admin/token`；输入支持 Enter/Shift+Enter，输入法组合期间 Enter 不提交。
- [x] **Step 2:** 接路由和导航，复用后台标题位置，避免重复 h1；CSS 使用 `--ac-*`，遵守已有深浅色主题和减少动效设置。README 记录入口、首次索引、模型配置和词面召回边界。
- [x] **Step 3:** 从 `backend` 运行 `.venv/bin/python -m pytest tests/test_knowledge_storage.py tests/test_knowledge_retrieval.py tests/test_knowledge_index.py tests/test_knowledge_qa.py tests/test_knowledge_api.py tests/test_admin_guards.py tests/test_article_refetch.py tests/test_note_export.py -q`；从 `frontend` 运行 `npm test`、`npm run build`；运行 `git diff --check`。预期无失败，新增修正仅重跑相关检查。
- [x] **Step 4:** 使用临时数据库与替身模型启动隔离后端，并启动前端指向该后端；浏览器以桌面和 390px 手机宽度实际检查入口、登录、正文命中提问、连续追问、引用点击、刷新恢复、删除、失败状态、主题切换。操作 A 生成中切 B，断言 B 不被覆盖；删除文章后检查历史来源显示。截图保存到任务产物目录，不往生产文章库插测试内容。
- [x] **Step 5:** 若已有可用模型配置，用已入库文章做一次真实提问，确认答案和引用；缺少配置时记录真实调用未验证，并报告配置入口。检查当前反向代理对长请求的超时，若会截断则报告实际限制，不宣称真实链路通过。
- [x] **Step 6:** 仅对计划范围内 diff 做整体代码审阅，聚焦鉴权、索引完整性、引用验证、锁释放和会话竞态；修复发现并重跑关联检查。将已完成任务复选框更新后提交，信息 `feat: deliver knowledge library question answering`。

## Self-Review

- 规格第 1–4 节的范围与页面入口由任务 5–7 实现；第 5 节分段、全库增量和预算由任务 1–3 实现。
- 第 6 节模型与引用由任务 4、6 实现；第 7 节持久化、互斥、重放与中断由任务 1、5 实现；第 8 节所有路由映射任务 5。
- Review Focus 的五类输入各有具名测试；浏览器检查负责真实布局和跨页面流程，构建不替代视觉检查。
- 签名、JSON 属性名、状态枚举和路径在 Shared Data Contract 中固定，各任务不另起同义名称。
- 保持现有正文导出与鉴权行为；FTS 缺失时仅问答受影响。
- 计划仅增 `knowledge_index.py` 作为索引维护边界；同步采用 spec 已澄清的有界批次短事务。

## Execution Handoff

用户确认后已在当前会话直接执行并完成全部任务。执行选择依据：后端索引、API 和前端共享引用契约，逐步实现与校验方便统一调整。另一选项为逐任务子代理实施与独立审阅。

已使用 `superpowers:executing-plans` 执行，完成独立代码审阅、回归修复和实际模型/浏览器验证。结果见 `docs/superpowers/reports/2026-10-19-knowledge-qa.md`。
