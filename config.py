"""配置模块 - 管理API密钥和全局设置"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """应用程序配置"""

    # ========== LLM 配置 ==========
    # OpenAI 兼容接口（DeepSeek、Groq、Ollama 等）
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-chat")

    # Anthropic Claude
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

    # LLM 通用设置
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))

    # ========== 爬虫配置 ==========
    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "30000"))  # Playwright 超时(ms)
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))

    # ========== 输出配置 ==========
    OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "output")
    REPORT_FILENAME: str = os.getenv("REPORT_FILENAME", "daily_report.md")


config = Config()
