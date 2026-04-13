"""聊天 Agent - 基于知识库和大模型的问答系统"""
import os
import re
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

import pandas as pd

from config import config
from llm_client import LLMClient


@dataclass
class Document:
    """文档块"""
    content: str
    source: str
    date: str


class KnowledgeBase:
    """知识库 - 从 MD 文件加载和检索内容"""

    def __init__(self, data_dir: str = "output"):
        """初始化知识库

        Args:
            data_dir: 报告文件所在目录
        """
        self.data_dir = data_dir
        self.documents: list[Document] = []
        self._load_knowledge_base()

    def _load_knowledge_base(self):
        """从 data_dir 加载所有 MD 文件"""
        print(f"[知识库] 正在从 {self.data_dir} 加载报告...")

        md_files = self._find_md_files()
        if not md_files:
            print(f"[知识库] 未找到 MD 文件")
            return

        print(f"[知识库] 找到 {len(md_files)} 个报告文件")

        # 加载所有文档
        self.documents = []
        for filepath in md_files:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()

                filename = os.path.basename(filepath)
                # 从文件名解析日期，格式: 2026-04-11_01.33.md
                date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})_(\d{2})\.(\d{2})', filename)
                if date_match:
                    date_str = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)} {date_match.group(4)}:{date_match.group(5)}"
                else:
                    date_str = "未知日期"

                # 解析报告内容，提取各部分
                sections = self._parse_report_content(content, filename, date_str)

                for section in sections:
                    self.documents.append(section)

            except Exception as e:
                print(f"[知识库] 加载文件失败 {filepath}: {e}")

        if not self.documents:
            print(f"[知识库] 没有可用的文档")
            return

        print(f"[知识库] 已加载 {len(self.documents)} 个文档片段")

    def _parse_report_content(self, content: str, filename: str, date_str: str) -> list[Document]:
        """解析报告内容，按章节和表格分割

        分割策略：
        - ## 标题 -> 作为独立 section
        - ### 子标题 -> 作为独立 section
        - 表格（|开头） -> 独立 section（保留完整表格结构）
        """
        sections = []
        lines = content.split('\n')

        current_section_title = ""
        current_section_lines = []
        current_table_lines = []
        in_table = False

        def _flush_section(title: str, lines: list[str]):
            """将当前累积的内容 flush 为一个 Document"""
            if not lines:
                return
            text = "\n".join(lines).strip()
            if text:
                sections.append(Document(
                    content=text,
                    source=filename,
                    date=date_str
                ))

        def _flush_table(table_lines: list[str]):
            """将当前累积的表格 flush 为一个 Document"""
            if not table_lines:
                return
            text = "\n".join(table_lines).strip()
            if text:
                sections.append(Document(
                    content=text,
                    source=filename,
                    date=date_str
                ))

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # 检测一级/二级标题
            if line.startswith('## ') or line.startswith('### '):
                # 先 flush 之前的表格（如果有）
                if current_table_lines:
                    _flush_table(current_table_lines)
                    current_table_lines = []
                    in_table = False

                # flush 之前的 section
                if current_section_lines:
                    _flush_section(current_section_title, current_section_lines)
                    current_section_lines = []

                current_section_title = line.replace('#', '').strip()
                current_section_lines = [lines[i]]
                i += 1
                continue

            # 检测表格行（以 | 开头）
            if line.startswith('|'):
                # flush 之前的 section 内容
                if current_section_lines:
                    _flush_section(current_section_title, current_section_lines)
                    current_section_lines = []
                    current_section_title = ""

                current_table_lines.append(lines[i])
                in_table = True
                i += 1
                continue
            else:
                # 非表格行
                if in_table:
                    # 表格结束，flush 表格
                    _flush_table(current_table_lines)
                    current_table_lines = []
                    in_table = False

                if line or current_section_lines:
                    current_section_lines.append(lines[i])
                i += 1
                continue

        # 处理最后残留
        if current_table_lines:
            _flush_table(current_table_lines)
        if current_section_lines:
            _flush_section(current_section_title, current_section_lines)

        return sections

    def _find_md_files(self) -> list[str]:
        """查找目录下所有 MD 文件"""
        md_files = []
        if not os.path.exists(self.data_dir):
            return md_files

        for filename in os.listdir(self.data_dir):
            if filename.endswith(".md"):
                filepath = os.path.join(self.data_dir, filename)
                md_files.append(filepath)

        # 按文件名排序（最新的在前）
        md_files.sort(key=lambda x: os.path.basename(x), reverse=True)
        return md_files

    def search(self, query: str, top_k: int = 3) -> list[Document]:
        """检索与查询相关的文档

        Args:
            query: 查询文本
            top_k: 返回前 k 个最相关的结果

        Returns:
            相关文档列表
        """
        if not self.documents:
            return []

        query_lower = query.lower()
        scored_docs = []

        # 提取查询关键词
        keywords = query_lower.replace('?', '').replace('？', '').split()
        keywords = [kw for kw in keywords if len(kw) >= 2]

        # 日期匹配
        date_patterns = [
            r'(\d{4})-(\d{2})-(\d{2})',
            r'(\d{4})年(\d{1,2})月(\d{1,2})日',
        ]
        query_dates = []
        for pattern in date_patterns:
            query_dates.extend(re.findall(pattern, query_lower))

        # 平台匹配
        platforms = ['微博', 'bilibili', 'b站', '抖音', 'douyin']
        platform_mentioned = [p for p in platforms if p in query_lower]

        for doc in self.documents:
            score = 0
            content_lower = doc.content.lower()

            # 1. 日期匹配（最重要）
            for match in query_dates:
                date_str = '-'.join(match)
                if date_str in doc.source or date_str in content_lower:
                    score += 10

            # 2. 表格数据块检测
            is_table_block = '|' in doc.content and '序号' in doc.content and '标题' in doc.content
            is_comparison_table = '维度' in doc.content and '|' in doc.content  # 平台对比表

            # 3. 平台匹配 - 精确区分
            for platform in platform_mentioned:
                platform_score = 0
                if platform in content_lower or platform in doc.source:
                    platform_score = 8

                    # 如果是具体平台（微博、b站/bilibili、抖音/douyin）
                    # 检查表格内容是否包含该平台的具体数据行
                    if is_table_block:
                        # 提取表格中包含的源平台信息
                        # B站表格通常包含 "bilibili" 或 "B站" 在链接/来源中
                        # 微博表格包含 "weibo" 或 "微博热搜"
                        # 抖音表格包含 "douyin" 或 "抖音热榜"
                        platform_indicators = {
                            '微博': ['微博热搜', 'weibo', 's.weibo'],
                            'b站': ['bilibili', 'b站', 'B站热门', 'b站热门'],
                            'bilibili': ['bilibili', 'b站', 'B站热门', 'b站热门'],
                            '抖音': ['抖音热榜', 'douyin', 'hot.douyin'],
                            'douyin': ['抖音热榜', 'douyin', 'hot.douyin'],
                        }
                        for ind in platform_indicators.get(platform, []):
                            if ind in content_lower:
                                platform_score += 6
                                break

                    # 如果是对比表但用户问的是具体某个平台，降低对比表优先级
                    if is_comparison_table:
                        platform_score -= 4

                score += platform_score

            # 4. 表格数据块优先级
            if is_table_block:
                score += 3
                # 表格行数越多，通常是完整榜单，给更高分数
                table_rows = doc.content.count('|')
                if table_rows >= 10:
                    score += 5

            # 5. 关键词匹配
            for kw in keywords:
                if kw in content_lower:
                    score += 1
                    # 计算出现次数
                    score += content_lower.count(kw) * 0.3

            # 6. "原始数据"、"热搜"、"热榜" 等关键词匹配（说明是榜单数据）
            data_keywords = ['原始数据', '热搜', '热榜', '榜单']
            for dk in data_keywords:
                if dk in content_lower:
                    score += 2

            # 7. 内容行数（更丰富的内容稍微优先）
            line_count = doc.content.count('\n')
            score += min(line_count * 0.05, 3)

            if score > 0:
                scored_docs.append((score, doc))

        # 按分数排序
        scored_docs.sort(key=lambda x: x[0], reverse=True)

        return [doc for _, doc in scored_docs[:top_k]]

    def get_all_reports_summary(self) -> list[dict]:
        """获取所有报告的摘要信息"""
        reports = []
        for filepath in self._find_md_files():
            filename = os.path.basename(filepath)
            date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})_(\d{2})\.(\d{2})', filename)
            if date_match:
                date_str = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)} {date_match.group(4)}:{date_match.group(5)}"
            else:
                date_str = "未知日期"
            reports.append({
                "filename": filename,
                "date": date_str,
                "filepath": filepath
            })
        return reports


class ChatAgent:
    """聊天 Agent - 基于知识库和 LLM 的问答系统"""

    # 系统提示词
    SYSTEM_PROMPT = """你是一个专业的热点资讯助手，基于提供的知识库内容回答用户问题。

重要规则（必须严格遵守）：
1. 【严格禁止编造】如果知识库中没有用户询问的具体数据（如具体热搜标题、热度值），绝对不能编造！不能写"张元英"、"我独自生活"等知识库中没有的内容！
2. 回答只能使用知识库中有的数据，每个数据点都必须能在上下文中找到对应来源
3. 如果知识库中没有相关信息，明确告知用户"知识库中没有找到相关信息"
4. 如果知识库中有部分信息，只回答有数据的部分，没有的部分明确说"知识库中没有更多详情"
5. 如果用户提供的问题涉及具体日期，优先查找该日期的报告
6. 如果用户询问特定平台，只返回该平台的数据，不要混合编造其他平台数据
7. 回答使用中文，语气友好专业

知识库信息格式：
- 来源文件: xxx
- 生成日期: xxxx-xx-xx xx:xx
- 内容: ...

请根据以上格式引用知识库内容进行回答。"""

    def __init__(self, knowledge_base: Optional[KnowledgeBase] = None):
        """初始化聊天 Agent

        Args:
            knowledge_base: 知识库实例
        """
        self.knowledge_base = knowledge_base or KnowledgeBase()
        self.llm_client = LLMClient(provider="openai_compatible", streaming=False)

    def _build_context_from_knowledge(self, query: str) -> str:
        """从知识库构建上下文"""
        results = self.knowledge_base.search(query, top_k=5)

        if not results:
            return ""

        context = "【知识库相关内容】\n\n"
        for i, result in enumerate(results, 1):
            context += f"--- 第{i}条 ---\n"
            context += f"来源: {result.source}\n"
            context += f"日期: {result.date}\n"
            context += f"内容:\n{result.content}\n\n"

        return context

    def _format_reports_list(self) -> str:
        """获取所有可用报告列表"""
        reports = self.knowledge_base.get_all_reports_summary()

        # 获取今天的日期
        today = datetime.now().strftime("%Y年%m月%d日")

        lines = [f"【今天是】{today}\n"]
        lines.append("【知识库中可用的报告】")

        if not reports:
            lines.append("暂无报告")
        else:
            for r in reports:
                lines.append(f"- {r['date']} 生成: {r['filename']}")

        return "\n".join(lines)

    def _extract_tables_from_doc(self, doc: 'Document') -> list[dict]:
        """从文档块中提取表格数据为结构化列表

        Args:
            doc: 文档块

        Returns:
            结构化数据列表，每个元素是 {序号, 标题, 热度, 作者} 的字典
        """
        lines = doc.content.split('\n')
        rows = []

        # 找到表头位置（| 序号 | 标题 | ...）
        header_idx = -1
        for idx, line in enumerate(lines):
            if '| 序号 |' in line or '| 序号|' in line:
                header_idx = idx
                break

        if header_idx == -1:
            return rows

        # 从表头下一行开始，解析每个数据行
        for line in lines[header_idx + 2:]:  # 跳过表头和分隔线
            line = line.strip()
            if not line or not line.startswith('|'):
                break
            # 解析 | a | b | c | 格式
            cells = [c.strip() for c in line.split('|')[1:-1]]  # 去掉首尾的空cell
            if len(cells) >= 3:
                # 序号、标题、热度、作者/来源
                try:
                    seq = cells[0]
                    title = cells[1]
                    hot = cells[2] if len(cells) > 2 else ""
                    author = cells[3] if len(cells) > 3 else ""
                    # 跳过分隔线等非数据行
                    if seq.isdigit() or (seq.startswith('`') and seq[1:].isdigit()):
                        rows.append({
                            "序号": seq,
                            "标题": title,
                            "热度": hot,
                            "作者/来源": author
                        })
                except Exception:
                    continue

        return rows

    def ask(self, question: str) -> str:
        """向 Agent 提问

        Args:
            question: 用户问题

        Returns:
            Agent 回答
        """
        print(f"\n[Agent] 问题: {question}")

        # 检索相关内容
        results = self.knowledge_base.search(question, top_k=5)

        # 构建提示
        reports_info = self._format_reports_list()

        # 分离：结构化表格数据 + 普通文本
        structured_data_lines = []
        analysis_text_parts = []

        for doc in results:
            if '|' in doc.content and '序号' in doc.content:
                # 是表格文档，解析为结构化数据
                tables = self._extract_tables_from_doc(doc)
                if tables:
                    # 判断是哪个平台
                    platform = "微博热搜"
                    if "bilibili" in doc.source.lower() or "b站" in doc.content.lower():
                        platform = "B站热门榜"
                    elif "douyin" in doc.source.lower() or "抖音" in doc.content.lower():
                        platform = "抖音热榜"
                    elif "weibo" in doc.source.lower() or "微博" in doc.content.lower():
                        platform = "微博热搜"

                    structured_data_lines.append(f"【{platform}】(来源: {doc.source}, 日期: {doc.date})")
                    for row in tables:
                        structured_data_lines.append(
                            f"  序号{row['序号']}: {row['标题']} | 热度: {row['热度']} | {row['作者/来源']}"
                        )
            else:
                # 普通分析文本
                preview = doc.content[:300].replace('\n', ' ')
                analysis_text_parts.append(f"来源: {doc.source} | {doc.date}\n{preview}")

        # 构建结构化数据部分
        structured_str = ""
        if structured_data_lines:
            structured_str = "\n".join(structured_data_lines)

        # 构建分析文本部分
        analysis_str = ""
        if analysis_text_parts:
            analysis_str = "\n\n---\n\n".join(analysis_text_parts)

        # 组装最终 prompt
        prompt = f"""你是一个专业的热点资讯助手。以下是知识库中的结构化数据，请根据这些数据回答用户问题。

【重要规则 - 必须严格遵守】：
1. 禁止编造！只能使用下方"结构化数据"中的具体数据
2. 如果结构化数据中有用户需要的信息，直接引用并回答
3. 如果结构话数据中没有相关信息，说"知识库中没有找到该信息"
4. 绝对不能编造热搜标题、用户名、热度数字等

{reports_info}

---
## 结构化数据（可直接查询使用）：

{structured_str if structured_str else "(无结构化数据)"}

---
## 分析文本参考：

{analysis_str if analysis_str else "(无分析文本)"}

---
用户问题: {question}

请只基于"结构化数据"回答问题，回答时引用具体数据："""

        # 调用 LLM
        try:
            answer = self.llm_client.invoke(
                prompt=prompt,
                system_message="你是一个专业的热点资讯助手。"
            )
        except Exception as e:
            answer = f"抱歉，发生了错误: {e}"

        return answer

    def chat(self):
        """交互式聊天"""
        print("\n" + "=" * 60)
        print("AI 热点资讯助手 - 基于知识库的问答系统")
        print("=" * 60)
        print("\n输入问题开始对话，输入 'q' 或 '退出' 结束对话")
        print("-" * 60)

        # 显示可用报告
        reports_info = self._format_reports_list()
        print(reports_info)
        print("-" * 60)

        while True:
            try:
                question = input("\n你: ").strip()

                if not question:
                    continue

                if question.lower() in ['q', 'quit', 'exit', '退出']:
                    print("\n再见！")
                    break

                answer = self.ask(question)
                print(f"\nAgent: {answer}")

            except (KeyboardInterrupt, EOFError):
                print("\n\n再见！")
                break


def main():
    """主函数"""
    agent = ChatAgent()
    agent.chat()


if __name__ == "__main__":
    main()
