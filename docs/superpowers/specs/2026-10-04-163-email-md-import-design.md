# 163 邮箱 md 附件导入书房 — 设计文档

日期:2026-10-04
状态:待用户审阅

## 背景与目标

用户通过 163 邮箱接收 B 站视频的总结 md 文档(以附件形式),希望把这些文档导入 SynthAI 书房,与现有 B 站视频笔记同源管理。

- 触发方式:**手动拉取**——后台一个「拉取邮件」动作,点击即拉取、过滤、入库并当场反馈结果。
- 过滤规则:按**发件人白名单**过滤(不依赖已读状态,手机上读过的邮件也能拉到)。
- 入库产物:每个 md 附件一篇 `source_type='bilibili'` 的文章,正文一字不动进 `content_md`。
- 前台零改动:bilibili 来源的色条、筛选、统计、md 渲染全部复用现有实现。

### 非目标(明确不做)

- 自动轮询 / IMAP IDLE 常驻(以后有需要再加)。
- 邮件正文入库(只取 md 附件)。
- 非 md 格式附件(PDF/Word/图片等)。
- 前台操作入口(前台只展示)。
- 发信 / 回信能力。

## 决策记录

1. **不复用现有任务系统。** 任务系统是 URL 驱动(身份、去重、类型推断全建立在 URL 上),邮件没有 URL identity,伪 URL(`imap://...`)违背「无伪链接」的 UI 标准。走独立导入接口,与 `POST /api/v1/articles/import-html` 同模式。
2. **不引入 email MCP**(评估过 [leeguooooo/email-mcp-service](https://github.com/leeguooooo/email-mcp-service),有附件下载能力、支持 163):它定位是 AI 客户端交互工具,后端集成需起子进程调 CLI 解析 JSON 或实现 MCP 客户端,均是多一层胶水;需在服务器装外部二进制(GitHub release,国内链路风险)且自带独立配置与缓存,邮箱配置两处管理。本场景(单发件人 + md 附件 + INBOX)直连成本更低。
3. **来源标 `bilibili`**,不新增「邮件」来源类型:这批笔记与现有 B 站视频笔记同源,不拆两堆,前端五处枚举零改动。
4. **IMAP 客户端用 Python 标准库 `imaplib` + `email`**,零新增依赖;网易怪癖(连接后必须发 IMAP `ID` 命令,RFC 2971)在本模块内处理。

## 架构

### 后端

#### 1. 新模块 `backend/app/services/email_client.py`

- 核心函数 `fetch_whitelisted_messages(config) -> list[EmailMessageData]`:
  - `imaplib.IMAP4_SSL(host, 993)` → `login(user, 授权码)`;
  - 登录后补发 `ID` 命令:`imaplib.Commands['ID'] = ('AUTH',)` 后 `_simple_command('ID', '("name" "SynthAI" "version" "1.0")')`;该命令失败不阻断(仅网易系需要,兼容其他 host);
  - `SELECT INBOX` → `SEARCH SINCE`(当前日期前推 30 天,固定窗口)→ 逐封 `FETCH RFC822`(量小,不做两段式);
  - 解析:From 地址小写后匹配白名单;Subject 解 RFC2047;Date 解析为 datetime;附件遍历 MIME part,`get_filename()` 解码后以 `.md` 结尾(或 content-type 为 `text/markdown`)的收集为 `{filename, content}`,payload 按 part 自身 charset 解码,缺省 utf-8、`errors="replace"`;
  - 返回 `[{message_id, from_addr, subject, date, md_attachments}]`。
- 异常:`EmailAuthError`(登录失败,中文提示「授权码无效或未开启 IMAP 服务」)、`EmailFetchError`(其他)。连接超时 30s。
- 入库函数 `import_email_message(msg) -> list[Article]`:每个 md 附件生成一篇:
  - `title`:md 首个 `# ` 一级标题 → 无则邮件主题(去 `Re:`/`Fwd:` 前缀)→ 再无则附件文件名去扩展名;
  - `content_md`:附件原文,**不改一字**(含代码块、空行、格式瑕疵——与微信复刻同原则);
  - `source_type`:`'bilibili'`;
  - `original_url`:正则 `https?://(www\.)?bilibili\.com/video/BV\w+` 或 `https?://b23\.tv/\w+` 取正文首个匹配,无则空;
  - `publish_time`:邮件 Date;`account_name`:发件人地址;`category`/`summary`:空(用户后台自行分类);
  - 同步写 runtime_store 内存镜像(对齐 `task_service.py` 中 `process_task` 的落库路径,实施时照抄其做法)。
- 去重:已入库邮件的 Message-ID 存 app_settings 内部 key `emailProcessedMessageIds`(JSON 数组,上限 500 条 FIFO 截断;不进 SUPPORTED_KEYS、不对前端暴露)。**入库成功后才写入**,失败的邮件留待下次重拉。

#### 2. 新路由 `backend/app/routers/email_import.py`

- `POST /api/v1/email/test`:读配置 → 连接+登录 → 返回 `{ok, recent_count}`(白名单发件人近 30 天邮件数)。
- `POST /api/v1/email/fetch`:拉取 → 逐封处理,**单封失败不阻断**(进 `skipped` 并附原因)→ 返回 `{fetched, imported: [{id, title, filename}], skipped: [{subject, reason}]}`;`fetched` 为白名单内符合条件的**邮件封数**,`imported` 为入库**篇数**(一封邮件多个 md 附件时大于封数)。
- 两接口均校验 `X-Admin-Token`(现有后台鉴权依赖);未配置 IMAP 时返回明确中文错误。

#### 3. 配置(settings_store,照 minimaxApiKey 现成模式)

- `SUPPORTED_KEYS` 新增:`imapHost`(默认 `imap.163.com`)、`imapUser`、`imapPassword`(授权码,非登录密码)、`imapSenderWhitelist`(逗号分隔的邮箱地址字符串)。
- `routers/config.py` 的 `AppConfigModel` 加同名字段;`public_settings` 对 `imapPassword` 掩码回显。

### 前端

- 新页 `frontend/src/features/email/pages/AdminEmailImport.tsx`,路由 `/admin/email`,后台导航组加「邮箱导入」项(照 `AdminTikHubSettings` 表单模式):
  - 配置表单:host / 邮箱账号 / 授权码 / 发件人白名单;授权码已配置时掩码回显 `••••`;
  - 「测试连接」按钮:显示白名单发件人近 30 天邮件数;
  - 「拉取邮件」主按钮:结果当场反馈——入库清单(标题可点进文章详情)+ 跳过明细(含原因);
  - 全中文、一动作一入口、无伪链接。
- 前台零改动。

## 错误处理

- 登录失败(授权码错 / 未开 IMAP / 网易返回 `NO LOGIN`):中文明确提示,不暴露 traceback。
- 网络 / 超时:30s 上限,超时报「邮箱连接超时」。
- 单封解析或入库失败:该封进 `skipped`(附原因),其余继续。
- 白名单为空:`fetch` 直接返回提示「请先配置发件人白名单」,不连邮箱。
- 极端情况(入库成功但 Message-ID 写入失败):下次可能重复入库,后台手动删除即可,不做事务补偿(YAGNI)。

## 测试与验证(手动清单)

前置:用户在 163 网页版开启 IMAP 服务并生成客户端授权码,后台「邮箱导入」页完成配置。

1. 「测试连接」通过,显示近 30 天邮件数;
2. 首次「拉取」:白名单发件人的 md 附件全部入库,标题、正文、来源色条正确;
3. 二次「拉取」:入库 0 篇(验证 Message-ID 去重);
4. 手机上已读的邮件仍被拉取(验证不限已读状态);
5. 非白名单发件人的邮件被跳过且原因明确;
6. md 无一级标题时回退用邮件主题;
7. 正文无 B 站链接时 `original_url` 为空,详情页不出现死链;
8. 断网 / 错误授权码:中文错误提示正确。

部署注意:本地 8000 无 `--reload`,改后端须重启;线上部署用 deploy 脚本后须手动 restart(脚本不会重启已运行服务)。
