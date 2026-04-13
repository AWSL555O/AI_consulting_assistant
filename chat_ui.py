"""聊天 Agent 网页界面 - 使用 Gradio"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gradio as gr
from chat_agent import ChatAgent


def main():
    """启动 Gradio 界面"""
    print("\n" + "=" * 60)
    print("AI 热点资讯助手 - 网页版")
    print("=" * 60)

    # 初始化 Agent
    print("正在初始化知识库...")
    try:
        agent = ChatAgent()
        print("初始化完成！")
    except Exception as e:
        print(f"初始化失败: {e}")
        agent = None

    # 创建响应函数
    def respond(message, history):
        """处理用户消息"""
        if not message.strip():
            return "", history

        if agent is None:
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": "Agent未初始化，请检查配置"})
            return "", history

        try:
            answer = agent.ask(message)
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": answer})
            return "", history
        except Exception as e:
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": f"发生错误: {e}"})
            return "", history

    def clear_history():
        """清空对话历史"""
        return []

    # 创建界面
    with gr.Blocks(title="AI 热点资讯助手") as demo:
        gr.Markdown(
            "# 🔥 AI 热点资讯助手\n"
            "基于知识库的智能问答，支持查询微博、B站、抖音热搜\n"
            "---\n"
            "**示例问题：**\n"
            "• 今天B站热搜是什么？\n"
            "• 今天三个平台热度最高的视频是什么？\n"
            "• 2026年4月10日的抖音热搜有哪些？\n"
            "• 对比一下今天三个平台的热搜差异"
        )

        # 初始化 chatbot 为空列表（字典格式）
        chatbot = gr.Chatbot(
            value=[],
            height=500,
        )

        msg = gr.Textbox(placeholder="输入你的问题...", scale=8)
        btn = gr.Button("发送", variant="primary", scale=1)

        # 发送按钮点击事件
        btn.click(
            fn=respond,
            inputs=[msg, chatbot],
            outputs=[msg, chatbot],
        )

        # 回车发送
        msg.submit(
            fn=respond,
            inputs=[msg, chatbot],
            outputs=[msg, chatbot],
        )

        # 清空按钮
        gr.Button("清空对话", variant="secondary").click(
            fn=clear_history,
            outputs=[chatbot]
        )

    print("\n正在启动网页界面...")
    print("访问地址: http://localhost:7860\n")

    demo.launch(server_name="0.0.0.0", server_port=7860, share=False, inbrowser=True)


if __name__ == "__main__":
    main()
