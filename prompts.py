"""模块二：Prompt管理 - 结构化的提示词库"""

# ========== 热点分析提示词 ==========
HOTSPOT_ANALYSIS_PROMPT = """你是一个资深的互联网热点分析师。请分析以下今日热门内容数据，总结出今日的流行趋势、用户偏好，并对比B站和抖音的差异。

请按以下结构输出分析报告：
1. 【今日概览】简要描述今天的热点整体情况
2. 【流行趋势】分析今天最热门的内容类型或主题
3. 【用户偏好】分析两个平台用户的兴趣特点
4. 【平台差异】对比B站和抖音在内容风格、用户行为上的差异
5. 【洞察与建议】给出你的分析结论

数据格式说明：
- title: 内容标题
- hot_value: 热度值/播放量
- author: 作者/UP主/创作者
- source: 来源平台（bilibili/douyin）
- link: 内容链接

请结合数据表格中的具体数值进行分析，不要空洞泛谈。"""

# ========== 其他通用提示词 ==========
SUMMARIZER_PROMPT = """你是一个专业的内容摘要专家。请对提供的内容创建简洁准确的摘要。

准则：
1. 抓住要点和关键信息
2. 保持事实准确性
3. 使用清晰简洁的语言
4. 突出重要的结论或发现"""

ANALYZER_PROMPT = """你是一位资深数据分析师。请分析提供的数据并提取有价值的洞察。

请按以下结构输出：
- 总结
- 关键发现
- 模式识别
- 建议"""


class PromptManager:
    """提示词管理器"""

    PROMPTS = {
        "hotspot_analysis": HOTSPOT_ANALYSIS_PROMPT,
        "summarizer": SUMMARIZER_PROMPT,
        "analyzer": ANALYZER_PROMPT,
    }

    @classmethod
    def get_prompt(cls, task: str) -> str:
        """获取指定任务的提示词"""
        if task not in cls.PROMPTS:
            raise ValueError(f"未知的任务类型: {task}，可用: {list(cls.PROMPTS.keys())}")
        return cls.PROMPTS[task]

    @classmethod
    def list_prompts(cls) -> list[str]:
        """列出所有可用的提示词名称"""
        return list(cls.PROMPTS.keys())
