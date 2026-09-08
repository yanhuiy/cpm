# 全国算力看板 · 部署与 Git 方案

本文档固化「Git 版本管理 + 静态部署」的完整方案。看板为**纯静态站点**（HTML + JS，无后端、无数据库），可零成本托管。

---

## 0. 部署架构

需要部署的文件（均在 `全国算力看板/` 目录）：

```
全国算力看板/
├── index.html        页面（含全部渲染逻辑）
├── data.js           数据层（由 data.json 生成）
├── echarts.min.js    图表库
├── china_geo.js      中国地图 GeoJSON
├── cities_geo.js     地市地图 GeoJSON
└── data.json         主数据源（部署时可不提交，本地维护即可）
```

> 纯静态、无服务端，任何静态托管都可用。

---

## 1. 目录规划建议

**重要**：项目根目录 `niu/` 混杂了大量与看板无关的文件（演示 HTML、PDF、docx、7z、`.venv` 等）。建议在 `全国算力看板/` **子目录内独立初始化 git 仓库**，只管理并部署看板本身，避免无关大文件卷入版本库。

```powershell
cd "c:\Users\28517\Documents\trae_projects\niu\全国算力看板"
git init
```

---

## 2. .gitignore（首次初始化时创建）

在 `全国算力看板/` 下创建 `.gitignore`，排除本地/敏感/生成物：

```gitignore
# Python 运行产物
__pycache__/
*.pyc

# 密钥（切勿提交）
.env
*.key

# 本地数据源（可选：若不想公开 data.json 原始数据则忽略）
# data.json

# 系统文件
.DS_Store
Thumbs.db
```

> 若你希望 `data.json` 也纳入版本库（便于团队协作、数据版本可追溯），删掉上面 `# data.json` 前的注释即可。密钥与 `.env` **务必忽略**。

---

## 3. 首次提交

```powershell
cd "c:\Users\28517\Documents\trae_projects\niu\全国算力看板"
git init
git add .gitignore index.html data.js echarts.min.js china_geo.js cities_geo.js
git add refresh.py export_data.py check_all.py data.json   # 如需一并入库
git commit -m "init: 全国算力中心看板（静态站点）"
```

---

## 4. 方案 A：GitHub Pages（推荐，免费 + 自动 HTTPS）

### 4.1 创建远程仓库并推送

1. 在 GitHub 新建仓库，例如 `national-ai-computing-dashboard`（Public 免费，Private 也可用 Pages）。
2. 关联并推送：

```powershell
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git branch -M main
git push -u origin main
```

### 4.2 启用 GitHub Pages

- 仓库页 → **Settings → Pages**：
  - Source：`Deploy from a branch`
  - Branch：`main`，目录 `/(root)`
- 保存后，站点地址为：

```
https://<你的用户名>.github.io/<仓库名>/
```

### 4.3 自定义域名（可选）

1. 在域名 DNS 控制台添加 CNAME 记录：

| 类型 | 主机记录 | 记录值 |
|---|---|---|
| CNAME | `www` | `<你的用户名>.github.io` |

2. 仓库 `Settings → Pages → Custom domain` 填入你的域名，并在仓库根放一个 `CNAME` 文件（内容为域名）。

---

## 5. 方案 B：Vercel / Netlify（备选）

- **Vercel**：`vercel.com` 导入 GitHub 仓库，Framework 选 `Other`，`Output Directory` 留空（根目录），自动部署并分配 `*.vercel.app` 域名。
- **Netlify**：`netlify.com` 拖拽 `全国算力看板/` 文件夹或导入仓库，Publish directory 设为根目录。

三者通用流程：**推代码即自动重新部署**。

---

## 6. 更新与发布流程（日常）

每次数据更新后，重复以下三步完成「本地更新 → 版本提交 → 线上生效」：

```powershell
# 1. 更新数据并体检
python refresh.py --run
python check_all.py

# 2. 提交版本
git add data.json data.js
git commit -m "data: 更新 2026-09 数据"
git push

# 3. 等 Pages/Vercel 自动部署完成，硬刷新线上地址验证
```

---

## 7. 域名与 ICP 备案说明

| 场景 | 是否需备案 | 说明 |
|---|---|---|
| 使用 `*.github.io` / `*.vercel.app` / `*.netlify.app` 免费子域名 | 否 | 无需备案，开箱即用 |
| 绑定国内服务器 + 自有域名 | 是 | 需 ICP 备案后接入 |
| 绑定自有域名到国外静态托管（Pages/Vercel/Netlify） | 否 | 域名本身无需国内备案，但国内访问速度可能受限 |

> 国内访问 `github.io` 可能不稳定；若面向国内用户且需稳定访问，建议选 Vercel / Netlify（有国内可达节点），或使用国内对象存储/CDN（需备案）。

---

## 8. 安全提示

- **绝不提交** `DEEPSEEK_API_KEY`、`TAVILY_API_KEY` 等密钥（已写入 `.gitignore`）。
- `data.json` 若含敏感的内部数据，可选择不公开到仓库（`.gitignore` 中取消 `data.json` 注释）。
- 数据回填脚本（`refresh.py`）仅在本机运行，不需要部署到线上。