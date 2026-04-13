"""主入口 - 每日热点追踪 AI Agent 工作流"""
import sys
import os

# 确保项目根目录在模块搜索路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from workflow import HotspotTracker, create_hotspot_workflow
from data_fetcher import HotspotFetcher, init_playwright
from prompts import PromptManager
from llm_client import LLMClient
from config import config


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("🔥 每日热点追踪系统 - AI Agent 工作流")
    print("=" * 60)

    # 检查 API 密钥
    if not config.LLM_API_KEY:
        print("\n⚠️  错误: 未配置 LLM_API_KEY")
        print("请在 .env 文件中设置你的 API 密钥")
        print("格式: LLM_API_KEY=你的密钥")
        return

    # 运行热点追踪工作流
    tracker = HotspotTracker(
        llm_provider="openai_compatible",
        top_n=10,
    )

    result = tracker.run()

    print("\n" + "=" * 60)
    print("📊 分析报告内容:")
    print("=" * 60)
    print(result)


def demo_fetcher():
    """仅测试数据抓取（不调用 LLM）"""
    print("\n" + "=" * 60)
    print("🧪 数据抓取测试模式")
    print("=" * 60)

    # 确保 playwright 驱动已安装
    print("\n提示: 首次运行需要安装 Playwright 驱动")
    print("在项目目录执行: playwright install\n")

    try:
        with HotspotFetcher(headless=True) as fetcher:
            # 抓取 B站
            print("\n--- B站 热门榜单 ---")
            bilibili_data = fetcher.fetch_bilibili(top_n=5)

            # 抓取 抖音
            print("\n--- 抖音 热榜 ---")
            douyin_data = fetcher.fetch_douyin(top_n=5)

            # 合并数据
            all_data = fetcher.fetch_all(top_n=5)
            print(f"\n总计抓取: {len(all_data)} 条")

    except Exception as e:
        print(f"抓取出错: {e}")


def chat_mode():
    """启动聊天 Agent"""
    from chat_agent import ChatAgent

    print("\n正在初始化知识库...")
    try:
        agent = ChatAgent()
        agent.chat()
    except Exception as e:
        print(f"聊天 Agent 初始化失败: {e}")


def interactive_mode():
    """交互模式"""
    print("\n" + "=" * 60)
    print("🎯 每日热点追踪系统 - 交互模式")
    print("=" * 60)

    while True:
        print("\n选项:")
        print("  1. 运行完整工作流（抓取 + 分析）")
        print("  2. 仅测试数据抓取")
        print("  3. 查看可用提示词")
        print("  4. 安装 Playwright 驱动（首次运行）")
        print("  5. 登录 B站（首次运行或Cookies失效时）")
        print("  6. 登录 抖音（首次运行或Cookies失效时）")
        print("  7. 启动聊天 Agent（基于知识库的问答）")
        print("  8. 退出")

        choice = input("\n请选择 (1-8): ").strip()

        if choice == "1":
            main()
        elif choice == "2":
            demo_fetcher()
        elif choice == "3":
            print("\n可用提示词:")
            for name in PromptManager.list_prompts():
                print(f"  - {name}")
        elif choice == "4":
            print("\n正在安装 Playwright 驱动...")
            init_playwright()
            print("安装完成！")
        elif choice == "5":
            # 登录 B站
            print("\n正在打开 B站 登录页面...")
            try:
                with HotspotFetcher(headless=False) as fetcher:
                    fetcher.login_bilibili()
            except Exception as e:
                print(f"登录出错: {e}")
        elif choice == "6":
            # 登录 抖音
            print("\n正在打开 抖音 登录页面...")
            try:
                with HotspotFetcher(headless=False) as fetcher:
                    fetcher.login_douyin()
            except Exception as e:
                print(f"登录出错: {e}")
        elif choice == "7":
            chat_mode()
        elif choice == "8":
            print("\n再见！")
            break
        else:
            print("无效选项，请重试。")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="每日热点追踪 AI Agent")
    parser.add_argument(
        "--mode",
        choices=["full", "demo", "interactive"],
        default="full",
        help="运行模式: full(完整工作流), demo(仅抓取), interactive(交互)"
    )

    args = parser.parse_args()

    if args.mode == "full":
        main()
    elif args.mode == "demo":
        demo_fetcher()
    elif args.mode == "interactive":
        interactive_mode()
