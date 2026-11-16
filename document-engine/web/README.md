# 合同审查引擎 · 交互测试页

纯静态页（`index.html` + `app.js`），用 Pyodide（CDN）在浏览器里运行
`compliance_engine` 的 Python 代码。文本只在用户浏览器里处理，不上传服务器。

## 文件

- `index.html`：页面结构与样式
- `app.js`：加载 Pyodide、取引擎源码与规则 JSON、跑审查、自检
- 引擎代码本身不在这里：页面运行时通过 `fetch` 从同仓库的
  `../compliance_engine/`（本地开发）或 `compliance_engine/`（部署产物）
  取 `.py` 与 `rules/*.json`、`rules/en/*.json`，写入 Pyodide 虚拟文件系统。

## 本地开发

```bash
# 在仓库根目录起一个静态服务器，让 ../compliance_engine/ 可以被 fetch 到
cd document-engine
python3 -m http.server 8000
# 打开 http://localhost:8000/document-engine/web/
```

## 部署（GitHub Pages）

`.github/workflows/pages.yml` 在每次推送到 `main` 且改动 `document-engine/`
时自动部署：把 `document-engine/web/` 的内容与 `compliance_engine/`
复制到发布产物根目录后发布到 GitHub Pages。仓库需在
Settings → Pages → Build and deployment → Source 选择 **GitHub Actions**
（只需设置一次）。
