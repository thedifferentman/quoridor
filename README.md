# 路墙棋游戏

基于 [james1BadCreeper/quoridor](https://github.com/james1BadCreeper/quoridor) 的游戏本体修改版，采用 React + FastAPI，支持双人、人机及上传 C++ AI 对战。

游戏源码位于 [`game/`](game/)。完整规则、运行方式、AI 协议及变更记录见 [游戏 README](game/README.md)。本仓库此次提交只包含游戏本体及相关文档、测试，不包含本地训练数据、模型或 MCTS 实验代码。

## 主要变更

- 围死任意一方改为非法动作，放墙必须保留双方通路。
- AI 改用 `protocol_version=2` 单事件协议：每次一个 `action`；连续行动分次决策，流沙单独提交。
- 补齐技能锁、强制移动、公开技能效果和事件预算；默认上限 800 个事件。
- 技能与动作整体校验；修复对战计数，统一实战与回放逻辑。
- 更新 C++ 公共库及内置贪心、随机 AI，移除单 AI 容器的半核 CPU 配额。
- 补充前端状态显示、回放字段、Windows 启动脚本和协议测试。

**旧 AI 的 `actions` 数组输出不兼容。** 请按 [AI 编写指南](game/backend/app/ai_cpp_example/README.md) 修改并重新上传。详细变更清单位于游戏 README 的“相对原始仓库的变更（2026-10-19）”一节。

## 本地运行

Windows 分别启动 [`game/launch_backend.bat`](game/launch_backend.bat) 和 [`game/launch_frontend.bat`](game/launch_frontend.bat)，访问 http://127.0.0.1:5173。后端 http://127.0.0.1:8000 仅提供 API。

上传 AI 的编译与运行需要 Docker 和 `gcc:14-bookworm` 镜像，具体要求见游戏 README。

## 验证

在仓库根目录执行：

```powershell
python -m pytest game/backend/tests -q
```

前端构建：

```powershell
cd game/frontend
npm ci
npm run build
```
