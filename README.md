# 岗位定制简历投递助手 Agent

一个面向校招/实习投递场景的本地 AI 求职 Agent MVP。它可以识别基础简历和岗位 JD，判断岗位匹配度，整理投递决策，辅助生成官网填表脚本，并维护本地投递追踪表。

> 当前项目定位为个人求职效率工具和 Agent 产品原型，不做未经授权的自动批量海投，也不会自动点击最终提交按钮。

## 功能亮点

- **简历识别**：支持粘贴文本，也支持上传/拖拽 `txt`、`md`、`docx`、`pdf` 简历。
- **JD 识别**：支持粘贴岗位 JD，也支持上传/粘贴岗位截图并调用视觉模型提取文字。
- **多岗位方向分析**：可识别产品经理、软件开发、机械结构、运营等不同岗位方向。
- **岗位匹配判断**：输出匹配度、命中能力、能力缺口、投递建议和岗位证据。
- **可投岗位推荐**：维护企业校招官网入口和部分官方结构化岗位，按企业聚合展示。
- **官网填表辅助**：基于个人档案生成浏览器 Console 填表脚本，只填表，不自动提交。
- **投递追踪表**：记录公司、岗位、投递类型、匹配度、状态、下一步，并支持单条删除和 CSV 导出。
- **安全本地运行**：API Key 只保存在本机 `.env`，不会写入前端页面。

## 项目截图

项目当前是本地 Web 应用。启动后访问：

```text
http://127.0.0.1:8787
```

## 技术栈

- 前端：原生 HTML / CSS / JavaScript
- 后端：Python 标准库 HTTP Server
- 模型接口：OpenAI Responses API 兼容接口
- 本地存储：浏览器 `localStorage`
- 文件解析：内置 `docx` 文本解析；PDF 可选本地解析，必要时调用模型提取

## 目录结构

```text
resume_agent/
  index.html        # 前端页面
  server.py         # 本地后端和模型调用
  start_agent.bat   # Windows 一键启动脚本
  .env.example      # 环境变量示例
  .gitignore        # 忽略密钥和缓存
  README.md         # 项目说明
```

## 快速开始

### 1. 克隆项目

```powershell
git clone https://github.com/BI8BO-WQ/resume-agent.git
cd resume-agent
```

### 2. 配置环境变量

```powershell
Copy-Item .env.example .env
notepad .env
```

填写你的模型 API Key：

```text
OPENAI_API_KEY=sk-your-api-key-here
OPENAI_MODEL=gpt-4.1-mini
OPENAI_FILE_MODEL=gpt-4.1-mini
OPENAI_VISION_MODEL=gpt-4.1-mini
OPENAI_BASE_URL=https://api.openai.com/v1
```

如果你使用兼容 OpenAI Responses API 的企业网关，可以将 `OPENAI_BASE_URL` 改成对应地址。

### 3. 启动应用

方式一：双击运行：

```text
start_agent.bat
```

方式二：命令行运行：

```powershell
python server.py
```

看到以下输出表示启动成功：

```text
Resume Agent backend running: http://127.0.0.1:8787
```

然后打开浏览器访问：

```text
http://127.0.0.1:8787
```

## 环境变量

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `OPENAI_API_KEY` | 模型 API Key | 必填 |
| `OPENAI_MODEL` | 岗位分析模型 | `gpt-4.1-mini` |
| `OPENAI_FILE_MODEL` | 简历/PDF 提取模型 | `gpt-4.1-mini` |
| `OPENAI_VISION_MODEL` | JD 截图识别模型 | `gpt-4.1-mini` |
| `OPENAI_BASE_URL` | OpenAI 兼容接口地址 | `https://api.openai.com/v1` |
| `OPENAI_REASONING_EFFORT` | 推理强度 | `low` |
| `OPENAI_TEXT_VERBOSITY` | 输出详细程度 | `medium` |
| `HOST` | 本地服务地址 | `127.0.0.1` |
| `PORT` | 本地服务端口 | `8787` |

## 使用流程

1. 上传或粘贴基础简历。
2. 粘贴 JD，或上传岗位截图自动识别。
3. 填写公司名称、岗位名称，选择岗位方向或自动识别。
4. 点击分析，查看匹配度、能力命中、缺口和投递建议。
5. 进入“官网填表”，维护个人档案并生成半自动填表脚本。
6. 保存记录到“投递追踪”，后续维护状态、导出 CSV 或删除无效记录。

## 安全说明

- 不要提交 `.env`，它可能包含真实 API Key。
- `.gitignore` 已默认忽略 `.env`、缓存和临时文件。
- 本项目不会自动登录招聘平台，也不会自动点击“提交申请”。
- 官网填表脚本只建议用于本人主动投递的页面，遇到验证码、协议勾选、最终提交等步骤应人工确认。

## 当前限制

- 官方岗位推荐仍以人工维护入口和部分可解析官网数据为主，动态招聘页面需要二次确认。
- PDF 简历如果是扫描件或复杂排版，可能需要模型提取，速度会比纯文本慢。
- 浏览器拖拽/粘贴文件能力受系统、微信和浏览器版本影响。
- 投递记录保存在浏览器本地，换浏览器或清缓存后可能丢失。

## Roadmap

- [ ] 支持批量导入岗位链接并自动生成投递清单
- [ ] 增加岗位截止日期、城市、投递批次和网申入口核验
- [ ] 增加多版本简历档案：产品、软开、机械结构、运营等
- [ ] 增加投递漏斗：待投递、已投递、笔试、面试、offer、拒绝
- [ ] 增加岗位推荐解释和投递优先级排序
- [ ] 支持云端/文件备份投递记录

## 开发维护

常用本地开发命令：

```powershell
python server.py
```

提交更新：

```powershell
git status
git add .
git commit -m "Describe your change"
git push
```

如果你在国内网络环境下推送 GitHub，需要确保 Git 使用了可访问 GitHub 的代理。

## License

当前项目未设置开源许可证。公开使用、复制或二次分发前，建议先补充明确的 License。
