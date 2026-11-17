# Qwen Lab · 安装与启动

本文依据项目 README 的“启动”章节整理，并与 package.json 核对。Qwen Lab 是本地学习应用，与知识库里的虚构产品“青竹笔记”不同。

## 环境与模型

Qwen Lab 使用 Node.js 22、Next.js、React 和 TypeScript。聊天模型是本机 Ollama 的 qwen3:14b，向量模型是 qwen3-embedding:0.6b。用 ollama list 检查模型与服务；无法连接时在另一个终端运行 ollama serve。聊天模型负责生成回答，向量模型负责文档检索，不出现在聊天模型选择列表中。

## 启动网页

进入项目目录 qwen-chat-lab，运行 npm run dev，然后打开 http://127.0.0.1:3010。服务仅监听本机地址，端口为 3010。首次加载聊天模型通常较慢。如果端口已经占用，先使用已打开的网页，不要重复启动同一服务。停止开发服务可在对应终端按 Ctrl+C。

## 重建依赖

Qwen Lab 的依赖在 node_modules，版本由 package-lock.json 锁定。重新安装依赖使用 npm ci。生产构建命令是 npm run build；已有构建后可用 npm start 在本机 3010 端口运行。开发服务和生产服务不能同时占用这个端口。
