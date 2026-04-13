"""模块四：LangGraph 工作流编排 - 每日热点追踪自动化"""
from typing import TypedDict
import os

import pandas as pd
from langgraph.graph import StateGraph, END

from data_fetcher import HotspotFetcher
from llm_client import LLMClient
from prompts import PromptManager, HOTSPOT_ANALYSIS_PROMPT
from config import config


class AgentState(TypedDict):
    """工作流状态管理 - 数据在各节点间流转

    Attributes:
        hotspot_data: 抓取并清洗后的热点数据 (DataFrame)
        analysis_result: LLM 分析结果 (str)
        error: 错误信息，如果有的话
        top_n: 要抓取的每平台条目数
    """
    hotspot_data: pd.DataFrame | None
    analysis_result: str | None
    error: str | None
    top_n: int


def create_hotspot_workflow(
    llm_client: LLMClient | None = None,
) -> StateGraph:
    """创建热点追踪的 LangGraph 工作流

    Args:
        llm_client: LLM 客户端实例，默认创建新实例

    Returns:
        编译好的 StateGraph，可直接运行
    """
    llm = llm_client or LLMClient(streaming=False)

    # ========== 节点1：获取与清洗 ==========
    def fetch_and_clean(state: AgentState) -> AgentState:
        """节点1：并发抓取三平台数据，并进行 Pandas 清洗"""
        top_n = state.get("top_n", 10)
        print(f"\n{'='*50}")
        print(f"[节点1] 开始并发抓取热点数据 (每平台 top {top_n})...")
        print(f"{'='*50}")

        try:
            with HotspotFetcher(headless=True) as fetcher:
                # fetch_all 内部已实现：API优先 + 微博抖音并发 + 降级兜底
                df = fetcher.fetch_all(top_n=top_n)

            if df is None or df.empty:
                return {**state, "error": "未能获取到任何热点数据"}

            print(f"\n[节点1] 数据抓取完成，共 {len(df)} 条记录")
            print(f"[节点1] 数据预览:\n{df.head(3).to_string()}\n")

            return {**state, "hotspot_data": df, "error": None}

        except Exception as e:
            error_msg = f"[节点1] 抓取失败: {str(e)}"
            print(error_msg)
            return {**state, "error": error_msg}

    # ========== 节点2：LLM 分析 ==========
    def analyze(state: AgentState) -> AgentState:
        """节点2：将 DataFrame 转为 Markdown 表格，发送给 LLM 分析"""
        df = state.get("hotspot_data")
        if df is None or df.empty:
            return {**state, "error": "没有可分析的数据"}

        print(f"\n{'='*50}")
        print(f"[节点2] 开始 LLM 分析...")
        print(f"{'='*50}")

        try:
            # 将 DataFrame 转为 Markdown 表格格式
            data_table = df.to_markdown(index=False)
            print(f"[节点2] 数据表格已生成，共 {len(df)} 行")

            # 构建分析提示
            analysis_prompt = f"""{HOTSPOT_ANALYSIS_PROMPT}

---
以下是今日热门内容数据：

{data_table}
---
请基于以上数据进行分析。"""

            # 调用 LLM
            print("[节点2] 正在调用 LLM 分析，请稍候...")
            result = llm.invoke(
                prompt=analysis_prompt,
                system_message="你是一个资深的互联网热点分析师。"
            )

            print(f"[节点2] LLM 分析完成，结果长度: {len(result)} 字符")
            return {**state, "analysis_result": result, "error": None}

        except Exception as e:
            error_msg = f"[节点2] 分析失败: {str(e)}"
            print(error_msg)
            return {**state, "error": error_msg}

    # ========== 节点3：输出报告 ==========
    def output(state: AgentState) -> AgentState:
        """节点3：将分析结果保存为 Markdown 报告"""
        result = state.get("analysis_result")
        if not result:
            return {**state, "error": "没有可输出的分析结果"}

        print(f"\n{'='*50}")
        print(f"[节点3] 生成分析报告...")
        print(f"{'='*50}")

        try:
            # 构建完整报告
            from datetime import datetime
            today = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")

            df = state.get("hotspot_data")
            # 获取数据来源列表
            sources = df["source"].unique().tolist() if df is not None and not df.empty else []
            source_str = "、".join(sources) if sources else "未知"

            # 生成各平台原始数据表格
            raw_data_table = ""
            if df is not None and not df.empty:
                # 按平台分组显示
                raw_data_lines = ["## 原始数据\n"]
                for source in ["weibo", "bilibili", "douyin"]:
                    platform_df = df[df["source"] == source]
                    if not platform_df.empty:
                        platform_name = {"weibo": "微博热搜", "bilibili": "B站热门榜", "douyin": "抖音热榜"}.get(source, source)
                        raw_data_lines.append(f"\n### {platform_name} (Top {len(platform_df)})\n")
                        raw_data_lines.append("| 序号 | 标题 | 热度/播放量 | 作者/来源 |")
                        raw_data_lines.append("|------|------|------------|-----------|")
                        for i, (_, row) in enumerate(platform_df.iterrows(), 1):
                            title = row["title"][:30] + "..." if len(str(row["title"])) > 30 else row["title"]
                            hot = row["hot_value"]
                            author = row["author"]
                            raw_data_lines.append(f"| {i} | {title} | {hot} | {author} |")
                        # 末尾统一添加链接
                        first_link = platform_df.iloc[0]["link"]
                        raw_data_lines.append(f"\n> 来源链接：[{platform_name}]({first_link})\n")
                raw_data_table = "\n".join(raw_data_lines)

            report = f"""# 每日热点追踪报告

> 生成时间: {today}
> 数据来源: {source_str}
> 数据条数: {len(df) if df is not None else 0} 条

---

## 热点分析

{result}

---

{raw_data_table}

---

*本报告由 AI Agent 自动化工作流生成*
"""

            # 保存报告（文件名包含日期时间，精确到分）
            output_dir = config.OUTPUT_DIR
            os.makedirs(output_dir, exist_ok=True)
            # 生成带时间戳的文件名，如 2026-04-10_22.10.md
            time_str = datetime.now().strftime("%Y-%m-%d_%H.%M")
            report_filename = f"{time_str}.md"
            report_path = os.path.join(output_dir, report_filename)

            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report)

            print(f"[节点3] 报告已保存至: {report_path}")
            return {**state, "analysis_result": report, "error": None}

        except Exception as e:
            error_msg = f"[节点3] 保存报告失败: {str(e)}"
            print(error_msg)
            return {**state, "error": error_msg}

    # ========== 构建工作流图 ==========
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("fetch_and_clean", fetch_and_clean)
    workflow.add_node("analyze", analyze)
    workflow.add_node("output", output)

    # 设置入口点
    workflow.set_entry_point("fetch_and_clean")

    # 定义流程：fetch -> clean -> analyze -> output -> END
    workflow.add_edge("fetch_and_clean", "analyze")
    workflow.add_edge("analyze", "output")
    workflow.add_edge("output", END)

    return workflow.compile()


class HotspotTracker:
    """热点追踪器 - 对外暴露的简洁接口"""

    def __init__(
        self,
        llm_provider: str = "openai_compatible",
        top_n: int = 10,
    ):
        """初始化热点追踪器

        Args:
            llm_provider: LLM 提供商
            top_n: 每平台抓取的热点数量
        """
        self.llm_client = LLMClient(provider=llm_provider, streaming=False)
        self.top_n = top_n
        self.workflow = None

    def initialize(self):
        """初始化/编译工作流"""
        self.workflow = create_hotspot_workflow(llm_client=self.llm_client)

    def run(self) -> str:
        """运行完整的热点追踪工作流

        Returns:
            分析报告内容
        """
        if self.workflow is None:
            self.initialize()

        initial_state: AgentState = {
            "hotspot_data": None,
            "analysis_result": None,
            "error": None,
            "top_n": self.top_n,
        }

        print("\n" + "=" * 60)
        print("🚀 每日热点追踪工作流启动")
        print("=" * 60)

        try:
            result = self.workflow.invoke(initial_state)

            if result.get("error"):
                print(f"\n❌ 工作流出错: {result['error']}")
                return f"错误: {result['error']}"

            print("\n" + "=" * 60)
            print("✅ 工作流执行完成！")
            print("=" * 60)

            return result.get("analysis_result", "无结果")
        finally:
            # 关闭全局浏览器单例，释放资源
            from data_fetcher import close_browser
            close_browser()
