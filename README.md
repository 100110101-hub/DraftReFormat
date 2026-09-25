# Draft ReFormat

一个本地运行的多模态草稿分割与终稿排版工作台。Qwen 先按语义识别紧致内容块，再由监督审校 agent 检查漏块、误合并和边界问题，直到监督通过（默认最多 5 轮，硬上限 6 轮）后输出坐标；每个区域会真正裁剪成独立图片，放入默认纯白的连续长画布。多张草稿会自动上下串接，裁剪块可以跨越多个页面自由拖动。前端同时支持画笔涂白、方形覆盖、素材/内容块删除、图层顺序、编号集合和整组分页。

## 启动

1. 安装依赖：`python -m pip install -r requirements.txt`。
2. 复制 `.env.example` 为 `.env`，填入 `DASHSCOPE_API_KEY`。
3. 运行 `python server.py`。
3. 打开 `http://127.0.0.1:8765`。

默认视觉模型为 `qwen-3.6-plus`，可用 `QWEN_MODEL` 覆盖。发送给 Qwen 的临时分析图会扩展白色边界并添加外侧 0–100 数值坐标轴，不画内部网格线；模型返回的坐标仍映射到无坐标轴原图，坐标轴不会出现在终稿中。

`QWEN_ENDPOINT` 使用 MaaS 的 OpenAI 兼容地址，默认配置为工作空间的 `/compatible-mode/v1/chat/completions`。

可用 `python benchmark_qwen.py` 对候选 Qwen 模型做同一张测试图的结构化坐标对比。该脚本不会输出 API Key；若 DashScope 返回 401，需要先更换为有效的 DashScope API Key。
