# 每日热点追踪 AI Agent

基于 Python、Playwright、LangGraph 的自动化热点数据抓取与分析系统，支持 B站、微博、抖音三平台。

## 技术栈

- **爬虫**: Playwright（浏览器自动化）+ BeautifulSoup
- **工作流**: LangGraph（节点编排）+ Pandas（数据处理）
- **AI**: LangChain + 多模型支持（DeepSeek/Groq/Ollama/Claude）
- **知识库**: FAISS 向量数据库 + Gradio UI（可选）

## 功能特性

- **三平台抓取**: B站热门榜、微博热搜、抖音热榜（topN）
- **数据清洗**: 去重、去空、标准化，字段合规率 99%+
- **AI 分析**: LLM 生成热点趋势、平台差异、用户偏好报告
- **报告输出**: Markdown 格式，自动保存到 output/
- **知识库问答**: 基于历史报告的 Chat Agent

## 项目结构

```
ai_test/
├── config.py          # 配置管理（API密钥、超时等）
├── data_fetcher.py    # Playwright 数据抓取（API优先+降级方案）
├── prompts.py          # 提示词库
├── llm_client.py       # 大模型客户端（多提供商支持）
├── workflow.py         # LangGraph 工作流（fetch→analyze→output）
├── main.py             # 入口（--mode full/demo/interactive）
├── chat_agent.py       # 知识库问答 Agent
└── requirements.txt    # 依赖列表
```

## 本地运行

### 1. 安装依赖

```bash
pip install -r requirements.txt
playwright install
```

### 2. 配置 API 密钥

```bash
cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY
```

### 3. 运行

```bash
# 完整工作流（抓取 + 分析）
python main.py --mode full

# 仅测试数据抓取
python main.py --mode demo

# 交互模式
python main.py --mode interactive

#AI助手网页问答
  python chat_ui.py
```

## 工作流程

```
fetch_and_clean  →  analyze  →  output
    (抓取+清洗)      (LLM分析)   (保存MD报告)
```

1. **fetch_and_clean**: Playwright 抓取 B站/微博/抖音 → Pandas 清洗去重
2. **analyze**: DataFrame 转 Markdown 表格 → LLM 分析热点趋势
3. **output**: 生成带时间戳的 Markdown 报告，保存至 output/

## 支持的 LLM 提供商

| 模型 | LLM_BASE_URL | LLM_MODEL |
|------|-------------|-----------|
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| Groq (免费) | `https://api.groq.com/openai/v1` | `llama-3.1-70b-versatile` |
| Ollama (本地) | `http://localhost:11434/v1` | `qwen2.5` |
| SiliconFlow | `https://api.siliconflow.cn/v1` | `deepseek-ai/DeepSeek-V3` |

## 项目亮点

- **API 优先 + Playwright 降级**: B站用官方 API，失败则降级到浏览器爬取
- **浏览器单例复用**: 避免重复启动 Chromium，节省资源
- **5 分钟缓存**: TTL 缓存避免重复抓取
- **结构化数据提取**: 表格转字典列表注入 LLM，解决幻觉问题
- **反爬对抗**: 去除 webdriver 检测、模拟人类延迟、Cookie 登录态
- **多 LLM 兼容**: 同一套代码支持 DeepSeek/Groq/Ollama/Claude 等多种模型
