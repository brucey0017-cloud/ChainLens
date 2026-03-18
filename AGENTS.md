# AGENTS.md — ChainLens 操作手册

> 给任何 agent 的一页纸指南。读完就能跑通整个系统，不踩坑。

---

## 项目概况

ChainLens 是一个 AI 驱动的链上量化交易信号系统。每 15 分钟通过 GitHub Actions 自动运行，采集多源信号写入 Supabase，由策略引擎评估后生成交易建议。

```
信号采集 → 评分 → 多源交叉验证 → 策略引擎 → 风控 → 交易（paper/live）
```

**仓库：** `brucey0017-cloud/ChainLens`
**运行环境：** GitHub Actions（每 15 分钟 cron）
**数据库：** Supabase PostgreSQL（通过 REST API 访问）
**Dashboard：** GitHub Pages

---

## 架构速览

### 文件职责

| 文件 | 职责 | 数据流 |
|------|------|--------|
| `signal_monitor.py` | 采集 Smart Money / KOL / Whale 信号 | onchainos CLI → signals 表 |
| `news_monitor.py` | 采集加密新闻 | OpenNews API → RSS fallback → signals 表 |
| `twitter_kol_monitor.py` | 采集 KOL 推文中的 token 提及 | OpenTwitter API → signals 表 |
| `onchain_monitor.py` | 链上指标（持仓分布、鲸鱼活动） | onchainos CLI → signals 表 |
| `technical_indicators.py` | 技术指标（动量、波动率、成交量） | CoinGecko → signals 表 |
| `multi_signal_scorer.py` | 多源交叉验证，综合评分 | signals 表 → signals 表（更新分数） |
| `strategy_engine.py` | 策略引擎，生成交易信号 | signals 表 → trades 表 |
| `intelligent_risk_manager.py` | 风控检查（敞口、日亏损限制） | trades 表 → risk_events 表 |
| `position_monitor.py` | 监控持仓，执行止损/止盈 | trades 表 + CoinGecko 价格 |
| `price_fetcher.py` | 统一价格获取（CoinGecko + onchainos） | 被多个模块调用 |
| `token_auditor.py` | Token 风险审计（8 维度评分） | onchainos CLI |
| `supabase_client.py` | Supabase REST API 客户端 | 被所有模块通过 db_patch 使用 |
| `db_patch.py` | 透明 DB fallback（REST → psycopg2） | import 时自动生效 |
| `dashboard_generator.py` | 生成 dashboard 数据 | 数据库 → docs/data/latest.json |

### 数据库（Supabase）

8 张表：`signals`, `trades`, `portfolio`, `strategy_performance`, `account_state`, `risk_events`, `backtest_results`, `trading_config`

Schema 定义在 `schema.sql`。

---

## 环境变量（GitHub Secrets）

| Secret | 用途 | 必需 |
|--------|------|------|
| `SUPABASE_URL` | Supabase 项目 URL | ✅ |
| `SUPABASE_SERVICE_KEY` | Supabase service_role JWT | ✅ |
| `OPENNEWS_TOKEN` | 6551 OpenNews API token | ✅ |
| `TWITTER_TOKEN` | 6551 OpenTwitter API token（和 OpenNews 共用） | ✅ |
| `SUPABASE_ANON_KEY` | Supabase anon key（前端用） | 可选 |
| `SUPABASE_DATABASE_URL` | 直连 PostgreSQL URL（IPv6 only，当前不可用） | 备用 |

**OpenNews 和 OpenTwitter 共用同一个 6551 JWT token。**

---

## 数据库连接

### 当前方案：REST API

直连 `db.feljzomjpesmxuoxrzdr.supabase.co` 只有 IPv6 地址，GitHub Actions 和大部分 VPS 不支持 IPv6 出站。

所有模块通过 `db_patch.py` 自动 fallback 到 Supabase REST API：

```
import db_patch   ← 每个模块第一行
import psycopg2   ← psycopg2.connect 已被 patch，失败时自动走 REST
```

### 如果需要改数据库连接

1. 不要直接改各模块的 psycopg2 调用
2. 改 `supabase_client.py`（REST 客户端）或 `db_patch.py`（fallback 逻辑）
3. 测试：`python3 -c "from supabase_client import select; print(select('signals', limit=1))"`

### ⚠️ 不要踩的坑

- **不要尝试直连数据库。** IPv6 only，连不上。不要花时间修网络，用 REST API。
- **密码含特殊字符 `/`、`@`、`*`。** 如果需要拼连接串，必须 URL 编码。
- **REST API 不支持复杂 SQL。** JOIN、子查询、窗口函数需要用 Management API 的 `/database/query` 端点。

---

## 信号源

### onchainos CLI

```bash
# Smart Money 信号（wallet-type 1）
onchainos signal list --chain solana --wallet-type 1

# KOL 信号（wallet-type 2）
onchainos signal list --chain solana --wallet-type 2

# Token 价格
onchainos market price --chain solana --address <token_address>

# Token 信息
onchainos token info --chain solana --address <token_address>
```

**注意：** 参数必须用 `--chain solana` 命名格式，不是位置参数。`--wallet-type 3`（Whale）在部分链上返回空。

### OpenTwitter（6551 API）

```bash
curl -s -X POST "https://ai.6551.io/open/twitter_user_tweets" \
  -H "Authorization: Bearer $TWITTER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"username": "cobie", "maxResults": 10, "product": "Latest"}'
```

### OpenNews（6551 API）

```bash
curl -s -X POST "https://ai.6551.io/open/news_search" \
  -H "Authorization: Bearer $OPENNEWS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"keyword": "bitcoin", "limit": 20}'
```

### CoinGecko（免费，无需 key）

```bash
# 价格
curl -s "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd"

# Trending
curl -s "https://api.coingecko.com/api/v3/search/trending"
```

Rate limit：10-30 req/min。`price_fetcher.py` 已内置 1 秒延迟。

---

## CI/CD

### Workflows

| Workflow | 触发 | 作用 |
|----------|------|------|
| `trading-system.yml` | 每 15 分钟 + 手动 | 完整信号管线 |
| `ci.yml` | push + PR | ruff + mypy + pytest + bandit |
| `test-supabase.yml` | 手动 | Supabase 连通性测试 |

### 手动触发

```bash
gh workflow run trading-system.yml --ref main -f task=monitor
```

### 读日志（最重要的习惯）

```bash
# 不要只看绿灯！读实际输出
gh run view <run-id> --log | grep -E "Found [0-9]|Stored [0-9]|Total|ERROR|warning::|KeyError|TypeError" -i
```

### ⚠️ 不要踩的坑

- **CI 绿灯不代表系统正常。** 很多 step 用了 `|| echo "warning"` 吞错误。必须读日志确认每个信号源的实际产出数量。
- **`workflow_dispatch` 只能在 main 分支触发。** 要测分支代码，先合并或用 push 触发。
- **本地 postgres service 每次 CI 跑完就销毁。** 数据持久化靠 Supabase REST API，不是本地 postgres。

---

## 修改代码的注意事项

### 数据库操作

- 所有模块已通过 `import db_patch` 自动 fallback 到 REST API
- 新增模块也要在第一行加 `import db_patch  # noqa: F401`
- PostgreSQL 的 `DECIMAL` 列返回 Python `Decimal` 对象，取值后用 `float()` 包一下再运算

### 返回值一致性

- 函数的所有返回路径必须保持字典 key 一致
- 用 `.get("key", default)` 防御性读取
- 写完后 grep 所有 return 路径确认

### 信号源 Fallback

每个信号源都有 fallback 链：
```
news_monitor:  OpenNews API → CoinTelegraph RSS → CoinDesk RSS → Decrypt RSS
price_fetcher: CoinGecko API → onchainos market price
db:            Supabase REST → psycopg2 直连 → 本地 postgres
```

新增信号源时也要遵循这个模式：主路径 + fallback + 记录用了哪条路径。

### 测试

```bash
# 跑测试
cd ChainLens && pytest -q

# Lint
ruff check *.py

# 类型检查（只检查核心文件）
mypy --ignore-missing-imports price_fetcher.py supabase_client.py token_auditor.py

# 编译检查（全部文件）
python3 -c "import py_compile; [py_compile.compile(f, doraise=True) for f in __import__('glob').glob('*.py')]"
```

---

## 策略参数

| 参数 | 值 | 说明 |
|------|-----|------|
| 最低信号分 | 0.7 | multi_signal_scorer 阈值 |
| 最少信号源 | 2 | 至少 2 个独立源确认 |
| 单笔最大 | $50 | 风控限制 |
| 总敞口上限 | $200 | 风控限制 |
| 日亏损限制 | $50 | 触发熔断 |
| 止损 | -15% | triple_confirmation 策略 |
| 止盈 | +30% | triple_confirmation 策略 |

**当前状态：** 信号阈值 0.7 保持保守，等数据积累后自然达标。不要调低。

---

## 快速诊断

### "CI 绿灯但没有交易"

```bash
# 1. 看信号数量
gh run view <id> --log | grep "Found\|Stored\|Total"

# 2. 看 multi-signal scorer 输出
gh run view <id> --log | grep "meeting threshold"

# 3. 看策略引擎输出
gh run view <id> --log | grep "trades generated"
```

正常情况：200+ signals → 0-5 tokens meeting threshold → 0-2 trades。刚开始跑时 0 trades 是正常的。

### "某个 step 报错"

```bash
# 看具体错误
gh run view <id> --log | grep -B 2 -A 5 "ERROR\|Traceback\|KeyError\|TypeError"
```

### "Supabase 连不上"

不要修。用 REST API。如果 REST API 也挂了：
```bash
# 检查项目状态
curl -s "https://api.supabase.com/v1/projects/feljzomjpesmxuoxrzdr" \
  -H "Authorization: Bearer $SBP_TOKEN" | python3 -c "import json,sys; print(json.load(sys.stdin)['status'])"
```

---

## 历史决策记录

| 日期 | 决策 | 理由 |
|------|------|------|
| 2026-03-18 | REST API over 直连 | IPv6 only，REST 走 HTTPS 无限制 |
| 2026-03-18 | 信号阈值保持 0.7 | Phase 2 小资金实盘，保守优先 |
| 2026-03-18 | CoinGecko + RSS 作为 fallback 保留 | 免费无限制，onchainos/6551 挂了还能跑 |
| 2026-03-18 | db_patch monkey-patch 模式 | 13 个文件最小侵入，不逐个重写 |

---

*最后更新：2026-03-18 by COMMANDER*
