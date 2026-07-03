# aBaiAutoplus 快速启动

## 🚀 一键启动

```bash
# Windows 双击运行
dev-start.bat

# 或命令行执行
powershell -ExecutionPolicy Bypass -File dev-start.ps1
```

## 📍 访问地址

- 前端：http://localhost:5173
- 后端：http://localhost:8000
- API 文档：http://localhost:8000/docs

## 🛑 停止服务

按 `Ctrl + C`

## 📋 首次运行

首次运行会自动安装所有依赖（约 5-10 分钟），包括：
- Python 虚拟环境
- Python 依赖包
- Playwright 浏览器驱动
- 前端依赖

后续启动仅需 10-20 秒。

## 🔧 快速命令

```bash
# 跳过依赖检查，快速启动
dev-start.bat -SkipCheck

# 健康检查
python scripts/smoke.py

# 手动启动后端
.venv\Scripts\activate
python -m uvicorn main:app --reload

# 手动启动前端
cd frontend && npm run dev
```

## 💡 常见问题

**端口被占用？**
```bash
netstat -ano | findstr ":8000"
taskkill /F /PID <进程ID>
```

**执行策略错误？**
```powershell
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```

详细文档请查看：[开发模式启动说明.md](./开发模式启动说明.md)
