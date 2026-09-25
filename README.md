# Draft ReFormat

一个本地运行的多模态草稿分割与终稿排版工作台。Qwen 先按语义识别紧致内容块，再把每个区域真正裁剪成独立图片，放入默认纯白的连续长画布；多张草稿会自动上下串接，裁剪块可以跨越多个页面自由拖动。前端同时支持画笔涂白、方形覆盖、编号集合和整组分页；后端负责将图片安全转发到 Qwen Vision，并在未配置密钥时提供离线演示分区。

## 启动

1. 安装依赖：`python -m pip install -r requirements.txt`。
2. 复制 `.env.example` 为 `.env`，填入 `DASHSCOPE_API_KEY`。
3. 运行 `python server.py`。
3. 打开 `http://127.0.0.1:8765`。

默认视觉模型为 `qwen-3.6-plus`，可用 `QWEN_MODEL` 覆盖。发送给 Qwen 的临时分析图会叠加 10% 坐标网格和刻度，模型返回的坐标仍映射到无网格原图；网格不会出现在终稿中。
