# Draft ReFormat

Draft ReFormat 是一个本地运行的多模态草稿分割与终稿排版工作台。它适合把试卷、讲义、网页截图、化学结构式、生物图片和带批注的草稿整理成可继续编辑的终稿。

应用由两部分组成：浏览器中的长画布编辑器，以及负责调用 Qwen 多模态模型的本地 Python 服务。图片只在执行 AI 分析时发送到配置的 Qwen 兼容接口；编辑、裁剪、排布和项目 JSON 保存都在本地浏览器完成。

## 主要能力

- 多素材队列：批量上传 PNG、JPG、WEBP，也可以导入 HTML/MHTML 或网页图片资源。
- 语义分割：识别文字、图片、表格、公式、化学结构式、生物图片、图注和修正内容。
- 多边形裁剪：区域边界只能使用多边形，矩形也必须作为多边形处理；不再把外接框发送给模型。
- 多边形挖空：区域内部删除部分也使用多边形，并会绘制在监督/修改 agent 的参考图上，最终裁剪时按多边形涂白。
- 化学语义保护：尽量保持完整的反应式、机理、箭头、条件、催化剂和连接标注，不从语义单元中间拆开。
- 删除与修正：圈选、划线删除内容会单独标记；邻近修正作为独立区域处理。
- 监督审校：初次分割后由监督 agent 检查漏块、误合并、边缘完整性和语义完整性；失败时由修改 agent 重建完整区域列表，再交回监督 agent 复核，最多 10 轮。
- 单块细分：选中一个内容块后点击“分析并细分此块（保留原位）”。子块会映射回原图坐标，保持父块中的相对位置，替换父块时只收拢外围空白，不删除任何子块内容。
- 长画布：所有素材上下串接，块可以自由拖动并跨越页面查看；支持缩放、画笔涂白、方形覆盖、删除块和调整图层顺序。
- 集合分页：使用编号集合把题目、图片、图注和相关内容绑定在一起；导出分页时尽量保证同一集合不被拆开。
- 纯内容导出：PDF 预览使用零页边距，不包含编辑器 UI 外壳；小块保持原始比例，不会为了撑满页面而放大。
- 离线演示：没有 API key 或请求失败时仍可启动界面并使用演示分区继续手动编辑。

## 快速启动

需要 Python 3.9 或更高版本。

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
python server.py
```

然后打开：

```text
http://127.0.0.1:8765
```

Linux/macOS 可使用等价的 `cp .env.example .env` 命令。停止服务时在运行窗口按 `Ctrl+C`。

## Qwen 配置

`.env` 只保存在本地，不要提交真实 API key。推荐配置如下：

```dotenv
DASHSCOPE_API_KEY=替换为你的key
QWEN_MODEL=qwen3.8-flash
QWEN_ENDPOINT=https://ws-yqr3lqq5xyjbxf30.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions
QWEN_COORDINATE_FRAME=1
QWEN_SUPERVISOR_ROUNDS=10
QWEN_REQUEST_TIMEOUT=180
```

配置项说明：

- `DASHSCOPE_API_KEY`：DashScope/MaaS 兼容接口的访问密钥。也兼容读取 `QWEN_API_KEY`。
- `QWEN_MODEL`：默认是 `qwen3.8-flash`，可改为工作空间实际开放的模型 ID。
- `QWEN_ENDPOINT`：OpenAI 兼容的 chat completions 地址。当前默认使用工作空间的兼容模式地址。
- `QWEN_COORDINATE_FRAME`：为 `1` 时给初次分割图附加外侧 0–100 数值坐标轴；不会绘制内部网格线。
- `QWEN_SUPERVISOR_ROUNDS`：监督轮数配置，服务端硬上限为 10，超过 10 会自动截断。
- `QWEN_REQUEST_TIMEOUT`：单次模型请求超时时间，单位为秒。

可以用健康检查确认服务读取到了模型配置：

```text
http://127.0.0.1:8765/api/health
```

返回内容不会包含 API key，只会报告模型名称、是否配置 key 和最近一次错误摘要。

## AI 分割流程

1. 初次分割 agent 接收原图和外侧数值坐标轴，返回完整 `regions` 列表。
2. 服务端拒绝缺少多边形、带有 `x/y/w/h` 或 `bbox` 的模型输出。
3. 服务端根据多边形顶点推导内部裁剪尺寸，供浏览器裁剪和排版使用；这些派生字段不会再发送给模型。
4. 监督和修改阶段各接收两张对齐图片：原比例候选边界图，以及带外侧数值坐标轴的放大图。
5. 区域边界使用紫色/红色多边形，删除区域使用红色多边形，内部挖空使用橙色多边形；图片中不绘制候选外接框。
6. 监督通过后才将最终区域交给编辑器。监督失败时，修改 agent 根据问题和当前多边形重新输出完整区域列表。

模型面对的区域结构大致如下：

```json
{
  "id": "r1",
  "label": "Reaction Pathway",
  "kind": "chemistry",
  "polygon": [[12.5, 8.2], [46.5, 8.2], [42.0, 29.7], [15.0, 29.7]],
  "group": "Q1",
  "description": "Complete reaction with conditions",
  "editAction": "keep",
  "holes": [
    {"polygon": [[20.0, 15.0], [26.0, 14.0], [30.0, 16.0], [28.0, 20.0], [22.0, 21.0]]}
  ]
}
```

`polygon` 和 `holes[].polygon` 都使用相对于原图内容区的 0–100 百分比坐标。模型不得输出矩形边界字段。编辑器内部保留 `x/y/w/h` 只是为了裁剪尺寸和排版计算，不属于模型协议。

## 单块细分

单块细分用于初次分割已经找到大语义块，但需要进一步拆开其中的题号、图注、结构式或修正内容的情况：

1. 在中央画布点击目标块。
2. 在右侧检查器点击“分析并细分此块（保留原位）”。
3. 服务端将当前多边形块裁成临时图片，重新调用初次分割、监督和修改流程。
4. 子块坐标按父块坐标映射回原图；子块继承父块的编号集合，并在画布中保留父块内的相对位置。
5. 只有在得到至少两个有效子多边形并通过监督后，才会替换父块；失败时原块保持不变。

## 编辑与导出

- 选择：点击块后拖动到长画布任意位置。
- 分区：使用分区工具创建人工区域；人工区域同样可继续拖动和删除。
- 涂白：画笔和方形覆盖分别用于局部修正；白色结果会进入预览和导出。
- 图层：在右侧检查器中执行置底、下移、上移和置顶。
- 删除：可删除素材，也可删除单个内容块；删除操作支持撤销。
- 编号集合：修改块的集合 ID；导出分页按集合组织内容。
- 保存项目：下载 `.draft.json`，其中不包含临时 `cropSrc` 数据。
- 生成分页预览：打开纯内容打印预览，可从浏览器打印对话框保存为 PDF。

导出时每个图像块使用自己的裁剪尺寸和原始比例；不会使用 `object-fit: cover` 之类的撑满布局。集合分页使用零页边距页面，并尽量将一个集合完整放在同一页。

## 本地接口

服务端只提供本地编辑器需要的轻量接口：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/health` | 查看服务、模型和 key 配置状态 |
| POST | `/api/segment` | 提交一张图片进行初次分割；返回初始区域和异步监督任务 ID |
| GET | `/api/segment-status?jobId=...` | 查询监督任务状态和最终区域 |
| POST | `/api/import-url` | 读取网页标题和图片资源地址 |
| POST | `/api/proxy-image` | 将网页图片代理为浏览器可用的 data URL |

`/api/segment` 的请求体示例：

```json
{
  "image": "data:image/jpeg;base64,...",
  "hint": "保持题号、图注和化学反应的语义完整"
}
```

## 测试与模型基准

运行回归测试：

```powershell
python -m unittest -v
python -m py_compile server.py benchmark_qwen.py test_server.py
node --check public/app.js
git diff --check
```

运行模型对比脚本：

```powershell
python benchmark_qwen.py
```

脚本会对同一张合成测试图依次请求 `qwen3.8-flash`、`qwen3.7-plus`、`qwen3.6-flash` 和 `qwen3.6-plus`，输出耗时、请求状态、区域数量和多边形数量。脚本不会打印 API key。

## 安全与隐私

- 不要把真实 API key 写入 README、源码、提交记录或截图。
- `.env` 已加入 `.gitignore`；提交前请检查 `git status` 和 `git diff`。
- 上传的图片只会在 AI 分析请求时发送到 `QWEN_ENDPOINT`；本地编辑操作不会自动上传。
- 网页导入会读取网页中的图片资源，使用前请确认目标网页和图片包含的信息适合发送到所配置的模型服务。
- `1.jpeg` 等本地测试素材不属于程序配置，不应随代码提交，除非明确需要作为公开测试资源。

## 项目结构

```text
DraftReFormat/
├─ server.py              # 本地 HTTP 服务、Qwen 调用、坐标和监督校验
├─ public/
│  ├─ index.html          # 编辑器页面结构
│  ├─ styles.css          # 编辑器样式和长画布布局
│  └─ app.js              # 上传、裁剪、拖动、细分、分页和导出逻辑
├─ benchmark_qwen.py      # Qwen 模型对比脚本
├─ test_server.py         # JSON schema、监督轮数和多边形标注回归测试
├─ requirements.txt       # Pillow 依赖
├─ .env.example           # 本地配置模板
└─ .gitignore
```

## GitHub 发布前检查

```powershell
git status --short
git diff --check
git log -1 --stat
```

确认没有 `.env`、API key、个人图片或临时测试文件后，再提交和推送代码。
