# GitHub 发布前检查

## 必须确认

- 不要提交 `.env`
- 不要提交任何真实 API Key
- `.env.example` 只能放占位符
- 公开仓库里不要放个人简历、身份证号、手机号、邮箱等隐私数据

## 推荐仓库结构

```text
resume_agent/
  index.html
  server.py
  README.md
  .env.example
  .gitignore
  start_agent.bat
  分享给朋友说明.md
```

## 上传到 GitHub 的基础命令

第一次上传：

```powershell
cd C:\Users\bibbo\Documents\gt\resume_agent
git init
git add index.html server.py README.md .env.example .gitignore start_agent.bat 分享给朋友说明.md
git commit -m "Initial resume delivery agent"
git branch -M main
git remote add origin https://github.com/你的用户名/你的仓库名.git
git push -u origin main
```

后续更新：

```powershell
git add .
git commit -m "Update resume delivery agent"
git push
```

## 对方怎么使用

对方 clone 后：

```powershell
cd resume_agent
Copy-Item .env.example .env
notepad .env
python server.py
```

然后打开：

```text
http://127.0.0.1:8787
```
