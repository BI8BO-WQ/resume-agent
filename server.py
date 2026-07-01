from __future__ import annotations

import json
import base64
import html
import os
import re
import sys
import zipfile
import urllib.error
import urllib.request
import http.cookiejar
from email.parser import BytesParser
from email.policy import default as email_default_policy
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL = "gpt-4.1-mini"
MAX_BODY_BYTES = 240_000
MAX_UPLOAD_BYTES = 8_000_000
SUPPORTED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
HUAQIN_CAMPUS_URL = "https://app.mokahr.com/campus-recruitment/hq/45417#/jobs"
HUAQIN_CAMPUS_FETCH_URL = "https://app.mokahr.com/campus-recruitment/hq/45417/"


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_dotenv(ROOT / ".env")


def is_valid_api_key(value: str | None = None) -> bool:
    key = (value if value is not None else os.environ.get("OPENAI_API_KEY", "")).strip()
    if not key:
        return False
    lowered = key.lower()
    if "your-api-key" in lowered or "sk-your" in lowered or lowered in {"placeholder", "none", "null"}:
        return False
    return key.startswith(("sk-", "sess-")) or len(key) > 20


def json_response(handler: SimpleHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.end_headers()
    handler.wfile.write(body)


def read_json_body(handler: SimpleHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    if length > MAX_BODY_BYTES:
        raise ValueError("请求内容过大，请缩短简历或JD后再试。")
    raw = handler.rfile.read(length)
    return json.loads(raw.decode("utf-8"))


def read_multipart_body(handler: SimpleHTTPRequestHandler) -> tuple[dict[str, str], dict[str, Any]]:
    content_type = handler.headers.get("Content-Type", "")
    if "multipart/form-data" not in content_type:
        raise ValueError("请使用 multipart/form-data 上传文件。")

    length = int(handler.headers.get("Content-Length", "0"))
    if length > MAX_UPLOAD_BYTES:
        raise ValueError("上传文件过大，请控制在 8MB 以内。")

    raw = handler.rfile.read(length)
    message = BytesParser(policy=email_default_policy).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + raw
    )

    fields: dict[str, str] = {}
    files: dict[str, Any] = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        if filename:
            files[name or "file"] = {
                "filename": filename,
                "content_type": part.get_content_type(),
                "data": payload,
            }
        elif name:
            fields[name] = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    return fields, files


def decode_text_file(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def extract_docx_text(data: bytes) -> str:
    from io import BytesIO

    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            xml = zf.read("word/document.xml")
    except Exception as exc:
        raise ValueError("无法解析 docx 文件，请确认文件未损坏。") from exc

    root = ElementTree.fromstring(xml)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", namespace):
        texts = [node.text or "" for node in paragraph.findall(".//w:t", namespace)]
        line = "".join(texts).strip()
        if line:
            paragraphs.append(line)
    return "\n".join(paragraphs)


def extract_pdf_text_locally(data: bytes) -> str:
    from io import BytesIO

    try:
        import pypdf  # type: ignore

        reader = pypdf.PdfReader(BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(page.strip() for page in pages if page.strip()).strip()
        if text:
            return text
    except Exception:
        pass

    try:
        import pdfplumber  # type: ignore

        with pdfplumber.open(BytesIO(data)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        text = "\n".join(page.strip() for page in pages if page.strip()).strip()
        if text:
            return text
    except Exception:
        pass

    text = extract_pdf_text_lightweight(data)
    if text:
        return text

    return ""


def extract_pdf_text_lightweight(data: bytes) -> str:
    # Small dependency-free fallback for text-layer PDFs. It will not handle every
    # PDF, but it often recovers enough text from resumes exported by office apps.
    raw = data.decode("latin-1", errors="ignore")
    chunks: list[str] = []

    for match in re.finditer(r"\((.*?)\)\s*Tj", raw, flags=re.S):
        chunks.append(match.group(1))

    for match in re.finditer(r"\[(.*?)\]\s*TJ", raw, flags=re.S):
        chunks.extend(re.findall(r"\((.*?)\)", match.group(1), flags=re.S))

    if not chunks:
        return ""

    text = "\n".join(unescape_pdf_text(chunk) for chunk in chunks)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def unescape_pdf_text(text: str) -> str:
    text = text.replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")
    text = text.replace(r"\n", "\n").replace(r"\r", "\n").replace(r"\t", " ")

    def replace_oct(match: re.Match[str]) -> str:
        try:
            return chr(int(match.group(1), 8))
        except ValueError:
            return ""

    return re.sub(r"\\([0-7]{1,3})", replace_oct, text)


def resume_pdf_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["resumeText", "confidence", "warnings"],
        "properties": {
            "resumeText": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "warnings": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
        },
    }


def extract_pdf_resume_with_model(file_info: dict[str, Any]) -> str:
    if not is_valid_api_key():
        raise RuntimeError(
            "PDF 本地解析没有提取到足够文字，且 OPENAI_API_KEY 未配置为真实 Key。"
            "请在 resume_agent/.env 中填入真实 Key 后重启后端；或把 PDF 另存为 docx/txt，或直接复制简历文字粘贴。"
        )

    filename = str(file_info.get("filename") or "resume.pdf")
    data = file_info.get("data") or b""
    if not data:
        raise ValueError("PDF 文件内容为空。")

    model = os.environ.get("OPENAI_FILE_MODEL", os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)).strip() or DEFAULT_MODEL
    file_data = f"data:application/pdf;base64,{base64.b64encode(data).decode('ascii')}"
    body: dict[str, Any] = {
        "model": model,
        "input": [
            {
                "role": "developer",
                "content": "你是简历 PDF 文本提取助手。只提取 PDF 中真实可见的简历文字，不要改写、总结或补充信息。",
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_file",
                        "filename": filename,
                        "file_data": file_data,
                    },
                    {
                        "type": "input_text",
                        "text": (
                            "请从这份 PDF 简历中提取完整文字。"
                            "保留姓名、联系方式、教育、经历、项目、技能、证书等信息；"
                            "如果存在多栏排版，请按适合阅读的顺序整理；"
                            "不要编造不存在的信息。"
                        ),
                    },
                ],
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "resume_pdf_extract_result",
                "strict": True,
                "schema": resume_pdf_schema(),
            },
            "verbosity": os.environ.get("OPENAI_TEXT_VERBOSITY", "medium"),
        },
    }
    add_reasoning_if_supported(body, model)

    response = make_openai_request(body, timeout=120)
    text = extract_output_text(response)
    if not text:
        raise RuntimeError("模型没有返回可解析的 PDF 简历文本。")
    result = parse_json_text(text)
    resume_text = str(result.get("resumeText") or "").strip()
    if not resume_text:
        raise RuntimeError("模型未能从 PDF 中提取到简历文字。")
    return resume_text


def extract_resume_text(file_info: dict[str, Any]) -> str:
    filename = str(file_info.get("filename") or "").lower()
    data = file_info.get("data") or b""
    if filename.endswith((".txt", ".md", ".markdown", ".csv")):
        return decode_text_file(data)
    if filename.endswith(".docx"):
        return extract_docx_text(data)
    if filename.endswith(".pdf"):
        local_text = extract_pdf_text_locally(data)
        if len(local_text) >= 80:
            return local_text
        return extract_pdf_resume_with_model(file_info)
    raise ValueError("暂只支持 txt、md、docx、pdf。")


def output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "company",
            "role",
            "score",
            "level",
            "reason",
            "requirements",
            "suggestions",
            "matchedSkills",
            "matchedKeywords",
            "gaps",
            "focus",
            "tailoredResume",
            "greeting",
            "advice",
        ],
        "properties": {
            "company": {"type": "string"},
            "role": {"type": "string"},
            "score": {"type": "integer", "minimum": 0, "maximum": 100},
            "level": {"type": "string"},
            "reason": {"type": "string"},
            "requirements": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
            "suggestions": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
            "matchedSkills": {"type": "array", "items": {"type": "string"}, "maxItems": 12},
            "matchedKeywords": {"type": "array", "items": {"type": "string"}, "maxItems": 18},
            "gaps": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
            "focus": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "bullets"],
                "properties": {
                    "title": {"type": "string"},
                    "bullets": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
                },
            },
            "tailoredResume": {
                "type": "string",
                "description": "投递决策报告，不是简历正文。必须包含投递结论、匹配依据、风险缺口、申请信息补齐建议。",
            },
            "greeting": {"type": "string"},
            "advice": {"type": "string"},
        },
    }


def build_prompt(payload: dict[str, Any]) -> str:
    style_map = {
        "pm": "产品经理：业务价值、用户洞察、产品闭环、指标验证",
        "growth": "增长运营：转化漏斗、内容/私域、增长指标、复盘",
        "software": "软件开发：技术栈、负责模块、工程质量、性能/稳定性、项目交付",
        "mechanical": "机械结构：结构设计、三维建模、工程图、材料工艺、仿真验证、量产问题",
        "technical": "技术产品：系统边界、数据、模型能力、工程协作",
        "general": "通用岗位：岗位关键词、真实经历证据、项目结果、协作能力",
    }
    family_map = {
        "auto": "自动识别岗位方向",
        "pm": "产品经理 / AI产品",
        "growth": "运营 / 增长",
        "software": "软件开发 / 后端 / 前端",
        "mechanical": "机械结构 / 结构设计",
        "technical": "技术产品 / 解决方案",
        "general": "通用岗位",
    }
    style = style_map.get(str(payload.get("style", "general")), style_map["general"])
    job_family = family_map.get(str(payload.get("jobFamily", "auto")), "自动识别岗位方向")
    company = str(payload.get("company") or "目标公司")
    role = str(payload.get("role") or "目标岗位")
    resume = str(payload.get("resume") or "")
    jd = str(payload.get("jd") or "")

    return f"""你是一个严谨的 AI 求职管家 Agent，任务是基于候选人的真实简历和目标岗位 JD，生成岗位定制投递材料。

成功标准：
1. 只能基于候选人已提供的真实经历改写和重组，不得编造不存在的公司、项目、指标、学校、奖项或技能。
2. 如果 JD 要求里有候选人简历未体现的能力，要放入 gaps 和 suggestions，不要假装已具备。
3. 输出要能直接用于求职决策：匹配分析、是否建议投递、申请信息补齐建议、招聘平台打招呼语、官网填表提醒。
4. 保持半自动投递边界：建议用户人工确认后再投递，不要鼓励违规批量海投。
5. 中文输出，表达自然，适合招聘平台投递场景。
6. 先根据岗位名称和 JD 判断岗位类型，再使用对应岗位的证据口径，不要把产品经理话术套到其他岗位。
7. 不要生成或改写整份简历；候选人只需要识别简历、判断岗位是否合适、完善官网申请信息。
8. JSON 字段 tailoredResume 因前端兼容保留，但它必须写成“投递决策报告”，不要写成“岗位版简历摘要”或简历正文。

不同岗位评估口径：
- 产品经理/AI产品：看用户需求、竞品分析、PRD、原型、项目推进、指标复盘、AI/Agent 能力理解。
- 运营/增长：看活动/内容/用户运营、渠道、转化漏斗、数据复盘、增长指标、业务结果。
- 软件开发：看编程语言、框架、数据库、接口/服务、负责模块、代码质量、测试部署、性能和稳定性。
- 机械结构：看结构设计、三维建模、工程图、公差、材料工艺、仿真验证、样机、装配、可靠性、量产/降本问题闭环。
- 技术产品/解决方案：看技术理解、系统边界、客户/业务需求、方案设计、交付推进、研发协作。

招聘平台打招呼语写作要求：
1. 只生成 greeting，不生成求职信。greeting 要适合 BOSS直聘/拉勾/猎聘第一句，可直接复制发送。
2. 学习这个结构：您好，我是xxx，能到岗/实习时间/工作年限/教育背景，具备岗位所需技能，曾做过xx项目或工作，熟悉xx场景。详情可查看简历/作品集，希望进一步沟通，期待回复。
3. greeting 控制在 120-220 个中文字符，最多 2 句话。信息密度高，但不要像广告文案。
4. 优先使用简历里的真实姓名、学校、专业、到岗时间、实习时长、每周可到岗天数、工作年限、项目经历、作品集等信息；没有提供就不要编造，可改写为“可根据团队安排沟通到岗时间”“相关经历可查看简历”。
5. 技能要来自 JD 和简历的交集；如果 JD 要求未在简历体现，不能写成熟练掌握。
6. 语气礼貌、直接、自然，不要使用“贵公司平台广阔”“本人性格开朗”等套话。

tailoredResume 字段写作要求：
1. 必须以“【投递决策报告】”开头。
2. 必须包含这些小标题：投递结论、匹配依据、风险/缺口、申请信息准备、人工确认。
3. 不要以“姓名｜岗位方向”开头，不要写候选人简历摘要，不要输出可直接替换简历的简历正文。
4. 不要虚构经历，不要建议编造项目；只指出是否值得投、为什么、投递前还要补哪些申请信息。

投递风格：{style}
岗位方向：{job_family}
公司：{company}
岗位：{role}

候选人基础简历：
{resume}

目标岗位 JD：
{jd}
"""


def extract_output_text(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"]
    chunks: list[str] = []
    for item in response.get("output", []) or []:
        for content in item.get("content", []) or []:
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks).strip()


def parse_json_text(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def make_openai_request(body: dict[str, Any], timeout: int = 90) -> dict[str, Any]:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not is_valid_api_key(api_key):
        raise RuntimeError("未配置 OPENAI_API_KEY。请在 resume_agent/.env 中填写后重启后端。")

    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    url = f"{base_url}/responses"
    req = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API 请求失败：HTTP {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"无法连接模型 API：{exc.reason}") from exc


def supports_reasoning_effort(model: str) -> bool:
    normalized = model.lower()
    return normalized.startswith(("gpt-5", "o3", "o4"))


def add_reasoning_if_supported(body: dict[str, Any], model: str) -> None:
    effort = os.environ.get("OPENAI_REASONING_EFFORT", "").strip()
    if effort and supports_reasoning_effort(model):
        body["reasoning"] = {"effort": effort}


def classify_verified_job(title: str, category: str = "") -> str:
    text = f"{title} {category}".lower()
    if re.search(r"结构|机械|工艺|设备|自动化|硬件|质量|mes|制造", text):
        return "mechanical"
    if re.search(r"软件|开发|it|测试|运维|java|python|算法|后端|前端", text):
        return "software"
    if re.search(r"运营|用户|内容|增长", text):
        return "growth"
    if re.search(r"产品|项目|经管", text):
        return "pm"
    return "general"


def keywords_for_verified_job(title: str, family: str, category: str = "") -> list[str]:
    text = f"{title} {category}"
    presets = {
        "mechanical": ["结构设计", "机械", "工程图", "工艺", "制造", "质量", "自动化", "设备", "硬件"],
        "software": ["软件开发", "编程", "测试", "数据库", "接口", "系统", "运维", "IT"],
        "growth": ["运营", "用户", "内容", "增长", "活动"],
        "pm": ["产品", "项目", "需求", "数据", "协作"],
        "general": ["项目", "沟通", "数据", "协作"],
    }
    found = [word for word in presets.get(family, presets["general"]) if word.lower() in text.lower()]
    return found or presets.get(family, presets["general"])[:4]


def fetch_text_url(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": HUAQIN_CAMPUS_URL,
        },
        method="GET",
    )
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    with opener.open(req, timeout=timeout) as resp:
        raw = resp.read()
    return raw.decode("utf-8", errors="replace")


def parse_huaqin_init_data(page_html: str) -> dict[str, Any]:
    match = re.search(r'<input\s+id="init-data"[^>]*value="([\s\S]*?)"', page_html)
    if not match:
        raise RuntimeError("华勤校招官网页面未返回可解析的岗位数据。")
    return json.loads(html.unescape(match.group(1)))


def normalize_huaqin_job(job: dict[str, Any], verified_at: str) -> dict[str, Any] | None:
    if str(job.get("status") or "").lower() != "open":
        return None
    job_id = str(job.get("id") or "").strip()
    title = str(job.get("title") or "").strip()
    if not job_id or not title:
        return None

    category = ""
    zhineng = job.get("zhineng")
    if isinstance(zhineng, dict):
        category = str(zhineng.get("name") or "").strip()
    family = classify_verified_job(title, category)
    locations = job.get("locations") if isinstance(job.get("locations"), list) else []
    city = " / ".join(
        str(item.get("address") or "").strip()
        for item in locations[:4]
        if isinstance(item, dict) and str(item.get("address") or "").strip()
    )
    custom_fields = job.get("customFields") if isinstance(job.get("customFields"), dict) else {}
    target = ""
    target_field = custom_fields.get("133435")
    if isinstance(target_field, dict):
        target = str(target_field.get("value") or "").strip()

    return {
        "company": "华勤技术",
        "role": title,
        "family": family,
        "status": "已核验在招",
        "verificationLevel": "open",
        "source": "华勤技术校招官网（Moka）",
        "sourceUrl": HUAQIN_CAMPUS_URL,
        "url": f"https://app.mokahr.com/campus-recruitment/hq/45417#/job/{job_id}/apply",
        "city": city or "详见官网",
        "target": target or "详见官网",
        "category": category or "详见官网",
        "updatedAt": str(job.get("updatedAt") or ""),
        "openedAt": str(job.get("openedAt") or ""),
        "verifiedAt": verified_at,
        "verification": f"官方页面结构化数据返回 status=open；职位 ID：{job_id}",
        "keywords": keywords_for_verified_job(title, family, category),
        "jobId": job_id,
    }


def fetch_verified_jobs() -> dict[str, Any]:
    verified_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    page_html = fetch_text_url(HUAQIN_CAMPUS_FETCH_URL)
    data = parse_huaqin_init_data(page_html)
    jobs = [
        normalized
        for normalized in (normalize_huaqin_job(job, verified_at) for job in data.get("jobs", []) or [])
        if normalized
    ]
    groups = []
    for item in data.get("jobsGroupedByZhineng", []) or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        count = item.get("jobCount")
        if label and isinstance(count, int):
            groups.append({"label": label, "jobCount": count})
    return {
        "source": "official",
        "verifiedAt": verified_at,
        "jobs": jobs,
        "groups": groups,
        "total": len(jobs),
        "officialTotal": ((data.get("jobStats") or {}).get("total") if isinstance(data.get("jobStats"), dict) else None),
        "sourceUrl": HUAQIN_CAMPUS_URL,
    }


def ocr_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["jdText", "company", "role", "confidence", "warnings"],
        "properties": {
            "jdText": {"type": "string"},
            "company": {"type": "string"},
            "role": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "warnings": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
        },
    }


def ocr_jd_image(file_info: dict[str, Any]) -> dict[str, Any]:
    content_type = str(file_info.get("content_type") or "")
    filename = str(file_info.get("filename") or "")
    data = file_info.get("data") or b""
    if content_type not in SUPPORTED_IMAGE_TYPES:
        raise ValueError("JD 图片仅支持 png、jpg、jpeg、webp。")
    if not data:
        raise ValueError("图片内容为空。")

    model = os.environ.get("OPENAI_VISION_MODEL", os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)).strip() or DEFAULT_MODEL
    image_url = f"data:{content_type};base64,{base64.b64encode(data).decode('ascii')}"
    body: dict[str, Any] = {
        "model": model,
        "input": [
            {
                "role": "developer",
                "content": "你是招聘 JD 图片 OCR 助手。只提取图片中真实可见的招聘信息，不要补写不存在的信息。",
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "请识别这张招聘岗位截图中的文字，整理为完整 JD 文本。"
                            "如果能看到公司名和岗位名，也提取出来。"
                            "保留职责、要求、加分项、地点、薪资等信息。"
                        ),
                    },
                    {"type": "input_image", "image_url": image_url},
                ],
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "jd_ocr_result",
                "strict": True,
                "schema": ocr_schema(),
            },
            "verbosity": os.environ.get("OPENAI_TEXT_VERBOSITY", "medium"),
        },
    }
    add_reasoning_if_supported(body, model)

    response = make_openai_request(body, timeout=90)
    text = extract_output_text(response)
    if not text:
        raise RuntimeError("模型没有返回可解析的OCR文本。")
    result = parse_json_text(text)
    result["filename"] = filename
    result["model"] = model
    return result


def call_openai(payload: dict[str, Any]) -> dict[str, Any]:
    model = os.environ.get("OPENAI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    request_body: dict[str, Any] = {
        "model": model,
        "input": [
            {
                "role": "developer",
                "content": (
                    "你是求职材料定制助手。必须输出严格 JSON，不编造经历，保留人工确认投递边界。"
                    "不要生成或改写整份简历。重点判断岗位是否适合投递、申请信息是否需要补齐，并生成招聘平台打招呼语。"
                ),
            },
            {"role": "user", "content": build_prompt(payload)},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "resume_agent_result",
                "strict": True,
                "schema": output_schema(),
            },
            "verbosity": os.environ.get("OPENAI_TEXT_VERBOSITY", "medium"),
        },
    }

    add_reasoning_if_supported(request_body, model)

    data = make_openai_request(request_body, timeout=90)

    text = extract_output_text(data)
    if not text:
        raise RuntimeError("模型没有返回可解析的文本。")

    result = parse_json_text(text)
    result["company"] = result.get("company") or payload.get("company") or "目标公司"
    result["role"] = result.get("role") or payload.get("role") or "目标岗位"
    result["createdAt"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {"source": "model", "model": model, "result": result}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[resume-agent] " + fmt % args + "\n")

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/health":
            json_response(
                self,
                200,
                {
                    "ok": True,
                    "hasApiKey": is_valid_api_key(),
                    "model": os.environ.get("OPENAI_MODEL", DEFAULT_MODEL),
                },
            )
            return
        if self.path.startswith("/api/verified-jobs"):
            try:
                json_response(self, 200, fetch_verified_jobs())
            except Exception as exc:
                json_response(self, 502, {"error": str(exc)})
            return
        if self.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:
        try:
            if self.path == "/api/analyze":
                payload = read_json_body(self)
                result = call_openai(payload)
                json_response(self, 200, result)
                return
            if self.path == "/api/extract-resume":
                _fields, files = read_multipart_body(self)
                file_info = files.get("file")
                if not file_info:
                    raise ValueError("没有收到简历文件。")
                text = extract_resume_text(file_info).strip()
                if not text:
                    raise ValueError("未能从文件中提取到文字。")
                json_response(
                    self,
                    200,
                    {
                        "text": text,
                        "filename": file_info.get("filename"),
                        "chars": len(text),
                    },
                )
                return
            if self.path == "/api/ocr-jd":
                _fields, files = read_multipart_body(self)
                file_info = files.get("file")
                if not file_info:
                    raise ValueError("没有收到JD图片。")
                result = ocr_jd_image(file_info)
                json_response(self, 200, result)
                return
            json_response(self, 404, {"error": "not_found"})
        except Exception as exc:  # keep local dev errors readable in the UI
            json_response(self, 500, {"error": str(exc)})


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8787"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Resume Agent backend running: http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
