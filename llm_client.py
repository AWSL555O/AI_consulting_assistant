"""模块三：大模型接入 - 支持 OpenAI 兼容接口和 Anthropic Claude"""
from typing import Optional, Iterator, Union
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.callbacks import StreamingStdOutCallbackHandler
from config import config


class LLMClient:
    """统一的大模型客户端，支持 OpenAI 兼容接口和 Anthropic"""

    PROVIDERS = {"openai_compatible", "anthropic", "openai"}

    def __init__(
        self,
        provider: str = "openai_compatible",
        model: Optional[str] = None,
        temperature: float = 0.7,
        streaming: bool = False,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        """初始化 LLM 客户端

        Args:
            provider: 提供商 ('openai_compatible', 'anthropic', 'openai')
            model: 模型名称，默认使用配置中的模型
            temperature: 随机性参数 (0.0-1.0)
            streaming: 是否启用流式输出
            api_key: API密钥，默认从配置读取
            base_url: 自定义API地址（用于 OpenAI 兼容接口）
        """
        if provider not in self.PROVIDERS:
            raise ValueError(f"不支持的提供商: {provider}，可用: {self.PROVIDERS}")

        self.provider = provider
        self.model = model or config.LLM_MODEL
        self.temperature = temperature
        self.streaming = streaming
        self.api_key = api_key or self._get_api_key()
        self.base_url = base_url or self._get_base_url()

        self._client = self._initialize_client()

    def _get_api_key(self) -> str:
        """根据提供商获取 API 密钥"""
        if self.provider == "openai":
            return config.LLM_API_KEY
        elif self.provider == "anthropic":
            return config.ANTHROPIC_API_KEY
        else:
            return config.LLM_API_KEY

    def _get_base_url(self) -> str:
        """获取 API 地址"""
        if self.provider in ("openai_compatible",):
            return config.LLM_BASE_URL
        return ""

    def _initialize_client(self) -> Union[ChatOpenAI, ChatAnthropic]:
        """初始化底层客户端"""
        callbacks = [StreamingStdOutCallbackHandler()] if self.streaming else []

        if self.provider == "openai":
            return ChatOpenAI(
                model=self.model,
                temperature=self.temperature,
                streaming=self.streaming,
                callbacks=callbacks,
                api_key=self.api_key,
            )
        elif self.provider == "anthropic":
            return ChatAnthropic(
                model=self.model,
                temperature=self.temperature,
                streaming=self.streaming,
                callbacks=callbacks,
                api_key=self.api_key,
            )
        else:
            # OpenAI 兼容接口（DeepSeek、Groq、Ollama 等）
            kwargs = {
                "model": self.model,
                "temperature": self.temperature,
                "streaming": self.streaming,
                "callbacks": callbacks,
                "api_key": self.api_key,
            }
            if self.base_url:
                kwargs["base_url"] = self.base_url
            return ChatOpenAI(**kwargs)

    def invoke(
        self,
        prompt: str,
        system_message: Optional[str] = None,
    ) -> str:
        """调用 LLM 生成回复

        Args:
            prompt: 用户输入的提示
            system_message: 可选的系统消息

        Returns:
            LLM 生成的回复内容
        """
        messages = []
        if system_message:
            messages.append(SystemMessage(content=system_message))
        messages.append(HumanMessage(content=prompt))

        response = self._client.invoke(messages)
        return response.content

    def invoke_stream(
        self,
        prompt: str,
        system_message: Optional[str] = None,
    ) -> Iterator[str]:
        """流式调用 LLM

        Args:
            prompt: 用户输入的提示
            system_message: 可选的系统消息

        Yields:
            逐字返回 LLM 的回复
        """
        messages = []
        if system_message:
            messages.append(SystemMessage(content=system_message))
        messages.append(HumanMessage(content=prompt))

        for token in self._client.stream(messages):
            yield token.content

    def batch_invoke(
        self,
        prompts: list[str],
        system_message: Optional[str] = None,
    ) -> list[str]:
        """批量调用 LLM

        Args:
            prompts: 多个用户提示
            system_message: 可选的系统消息

        Returns:
            多个 LLM 回复的列表
        """
        results = []
        for prompt in prompts:
            result = self.invoke(prompt, system_message)
            results.append(result)
        return results
