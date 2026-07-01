# 岗位定制简历投递助手 Agent

这是一个本地运行的 AI 求职 Agent MVP。前端负责输入和展示，后端负责安全地调用模型 API。

## 文件说明

- `index.html`：前端页面，浏览器打开。
- `server.py`：本地后端，提供 `/api/analyze`，调用 OpenAI Responses API。
- `.env.example`：环境变量示例。
- `.env`：你自己创建，用来放 API Key，不要上传或发给别人。

## 后端怎么运行

1. 进入项目目录：

```powershell
cd C:\Users\bibbo\Documents\gt\resume_agent
```

2. 复制配置文件：

```powershell
Copy-Item .env.example .env
```

3. 用记事本打开 `.env`，填入你的 API Key：

```powershell
notepad .env
```

把这一行：

```text
OPENAI_API_KEY=sk-your-api-key-here
```

改成你的真实 Key。

4. 启动后端：

```powershell
python server.py
```

看到下面这行说明启动成功：

```text
Resume Agent backend running: http://127.0.0.1:8787
```

5. 打开浏览器访问：

```text
http://127.0.0.1:8787
```

不要直接双击桌面 HTML 测试模型版。模型版建议通过这个本地地址访问。

## 怎么测试

1. 点“填入示例”。
2. 点“生成材料”。
3. 如果后端和 API Key 正常，页面会显示“模型生成”。
4. 如果模型失败，前端会自动退回本地规则版，并提示失败原因。

## 新增上传能力

### 上传基础简历

页面左侧“基础简历”上方可以上传文件：

- 支持：`txt`、`md`、`docx`、`pdf`
- 支持从微信/文件夹拖拽到“基础简历”区域
- 如果微信复制的是纯文字，也可以直接粘贴到简历输入框

PDF 会先尝试本地解析；如果本机没有 `pypdf/pdfplumber`，或 PDF 是复杂排版/扫描版导致提取文字太少，后端会调用模型读取 PDF 并提取简历文字。因此 PDF 上传需要 `.env` 里配置 `OPENAI_API_KEY`。

可选：如果你想让普通文字 PDF 尽量走本地解析，可以安装：

```powershell
pip install pypdf
```

### 上传岗位 JD 截图

页面左侧“岗位 JD”上方可以上传岗位截图：

- 支持：`png`、`jpg/jpeg`、`webp`
- 支持从微信拖拽岗位截图到“岗位 JD”区域
- 支持复制微信截图后，在“岗位 JD”区域内粘贴
- 需要：后端已启动，且 `.env` 里配置了 `OPENAI_API_KEY`

上传后后端会调用模型视觉能力识别截图文字，并自动填入 JD 输入框；如果识别到公司名和岗位名，也会自动填入对应字段。

注意：不同浏览器和微信版本对“拖拽/粘贴文件”的支持不完全一致。如果拖拽没有反应，可以先把文件保存到桌面，再点击上传按钮；如果截图粘贴没有反应，可以把截图另存为图片后上传。

## 安全边界

- API Key 只放在本机 `.env`，不要写进 `index.html`。
- 这个工具不做自动登录招聘平台，不做未经授权的批量海投。
- 建议定位为半自动投递助手：生成不同岗位的简历和话术，由你人工确认后投递。

## 官方接口口径

后端使用 OpenAI Responses API 的 `POST /responses` 创建模型响应，并使用 `json_schema` 约束模型输出结构。模型名可在 `.env` 中通过 `OPENAI_MODEL` 调整。
