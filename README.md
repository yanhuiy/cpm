# 全国算力看板

纯静态站点（HTML + JS，无后端、无数据库）的「数据更新 + Git 部署」一站式说明。

```
全国算力看板/
├── index.html        页面（含全部渲染逻辑）
├── data.js           数据层（由 data.json 生成，勿手改）
├── echarts.min.js    图表库
├── china_geo.js      中国地图 GeoJSON
├── cities_geo.js     地市地图 GeoJSON
├── data.json         主数据源（只改这里，本地维护）
├── refresh.py        数据刷新/回填脚本（仅本机运行）
├── export_data.py    data.json → data.js 生成器
└── check_all.py      质量体检脚本
```

---

## 一、数据更新流程

核心原则：**只改 `data.json`**，`data.js` 一律由 `export_data.py` 生成。

### 1. 密钥配置（仅首次）

密钥**只存环境变量，不写入文档/代码**。已永久配置为本机用户环境变量，本机可直接用；换电脑时按下面临时配置即可。

```powershell
$env:DEEPSEEK_API_KEY = "sk-你的密钥"   # 必填，DeepSeek 官网获取
$env:TAVILY_API_KEY   = "tvly-你的密钥" # 可选推荐，Tavily 官网获取
```

未配置 `DEEPSEEK_API_KEY` 时 `refresh.py --run` 会直接跳过刷新；未配置 `TAVILY_API_KEY` 时退化为纯模型模式。

### 2. 月度更新（标准流程）

```powershell
# 1. AI 检索刷新（Tavily 检索 → DeepSeek 抽取 → 增量合并 → 重生成 data.js）
python refresh.py --run
# 2. 一键体检（数据合规 + 前端语法）
python check_all.py
# 3. 硬刷新(Ctrl+F5) index.html 验证
```

### 3. 历史回填

```powershell
python refresh.py --backfill 2020-01 2026-08          # 按年（成本低）
python refresh.py --backfill 2024-09 2026-08 --monthly # 按月（更精确）
```

回填后同样跑 `python check_all.py` 并硬刷新验证。

### 4. 质量体检

```powershell
python check_all.py
```

退出码 `0`=通过，`1`=有异常。数据合规问题改 `data.json` 再 `export_data.py`；前端语法问题多半在 `index.html` 内联脚本。

### 5. 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| 刷新 0/0 | 未配置 `DEEPSEEK_API_KEY` | 配置密钥后重跑 |
| 检索失败 | `TAVILY_API_KEY` 无效/超额 | 检查密钥或降级纯模型 |
| `UnicodeEncodeError` | Windows 终端编码 | `python -X utf8 refresh.py --run` |
| 页面白屏/各省标签丢失 | `index.html` 脚本语法错 | 跑 `check_all.py` 定位修复 |
| 图表 `instance has been disposed` | ECharts 重复初始化 | 切换区域先 `dispose` 再重建 |

---

## 二、Git 部署

在 `全国算力看板/` 子目录独立管理 git 仓库。`data.json`、`.md` 文档均入库；密钥/`.env` 不入库。

### 1. Git 常规流程

```powershell
# 数据更新后提交版本
git add data.json data.js
git commit -m "data: 更新 2026-09 数据"
git push
```

### 2. 托管平台

- **GitHub Pages**（免费 + 自动 HTTPS）：
  仓库 → Settings → Pages → Source 选 `Deploy from a branch`，Branch 选 `main`、目录 `/ (root)`。
  站点地址：`https://<用户名>.github.io/<仓库名>/`
- **Vercel / Netlify**（备选，国内访问更稳）：导入 GitHub 仓库，Output/Publish directory 留根目录即可。

推代码即自动重新部署，发布后硬刷新线上地址验证。

### 3. 安全提示

- 密钥（`DEEPSEEK_API_KEY`、`TAVILY_API_KEY` 等）**只放环境变量，绝不写入文档或代码**，也不入库。
- `.gitignore` 已忽略 `.env`、`*.key`、`__pycache__/`、`*.pyc`。
- 若公开仓库，请勿在 md/代码中写入任何真实密钥。

---

## 三、域名与 ICP 备案

| 场景 | 是否需备案 |
|---|---|
| 使用 `*.github.io` / `*.vercel.app` / `*.netlify.app` | 否 |
| 绑定国内服务器 + 自有域名 | 是（需 ICP） |
| 绑定自有域名到国外静态托管 | 否，但国内访问速度可能受限 |

> 国内访问 `github.io` 可能不稳定；面向国内用户可改用 Vercel/Netlify 或国内 CDN（需备案）。