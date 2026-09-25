# Draft ReFormat

一个本地运行的多模态草稿分割与终稿排版工作台。前端支持图片批量导入、拖动/缩放语义块、画笔涂白、编号集合和整组分页；后端负责将图片安全转发到 Qwen Vision，并在未配置密钥时提供离线演示分区。

## 启动

1. 复制 `.env.example` 为 `.env`，填入 `DASHSCOPE_API_KEY`。
2. 运行 `python server.py`。
3. 打开 `http://127.0.0.1:8765`。

默认视觉模型为 `qwen-vl-max`，可用 `QWEN_MODEL` 覆盖。
