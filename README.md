# AICG Check

一个可自行部署的论文 AIGC **文本风险分析器**。它不调用任何收费 AIGC API，而是使用透明的启发式规则，对论文段落中的模板化表达、泛化政策动词、抽象概念密度、句长规律、常见平衡句式、短语重复度、引用和数字线索进行综合评分。

> **重要：** 本项目输出的是“文本生成式特征风险估算”，不是对文本来源的鉴定，也不等同于知网、万方或学校系统的官方 AIGC 检测结果。

## 功能

- DOCX（推荐）与文字型 PDF。
- 全文综合风险指数。
- AIGC 风险估算占比。
- 高风险 / 中高风险文本占比。
- 章节级汇总。
- 段落级风险分、命中特征和统计指标。
- 前端筛选、搜索。
- CSV / HTML 报告导出。
- Flask 单体服务：页面、上传、解析、分析都由同一个 Python 应用提供。
- Docker / Docker Compose / 直接 Python 部署。

## 快速部署

### Docker Compose

```bash
git clone https://github.com/umud66/aicg_check.git
cd aicg_check
docker compose up -d --build
```

浏览器打开：

```text
http://你的服务器IP:8000
```

### Docker

```bash
docker build -t aicg-check .
docker run -d \
  --name aicg-check \
  --restart unless-stopped \
  -p 8000:8000 \
  -e MAX_UPLOAD_MB=50 \
  aicg-check
```

### 直接运行

需要 Python 3.10+（推荐 3.12）：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
gunicorn --bind 0.0.0.0:8000 --workers 1 --threads 4 --timeout 180 app:app
```

Windows 本地调试也可以：

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---:|---|
| `PORT` | `8000` | HTTP 监听端口 |
| `MAX_UPLOAD_MB` | `50` | 单文件上传大小限制 |
| `FLASK_DEBUG` | `0` | 仅本地调试时可设为 `1` |

## Nginx 反向代理示例

```nginx
server {
    listen 80;
    server_name example.com;

    client_max_body_size 50m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 180s;
    }
}
```

## 算法概要

每个段落先得到 0–100 风险分，当前主要特征包括：

1. “首先 / 其次 / 此外 / 综上所述”等模板连接词密度；
2. “加强 / 完善 / 提升 / 推动 / 优化”等泛化政策动词密度；
3. 抽象概念密度；
4. 多句段落的句长变异系数；
5. “不仅……而且”“一方面……另一方面”等模板化句式；
6. 4-gram 短语重复；
7. 长段落是否缺少引文、年份、数字等可核查信息；
8. 明确引文与数据会对部分风险分进行抵扣。

`AIGC 风险估算占比`的计算方式：30 分以下作为背景噪声，30–100 分线性映射到 0–100% 风险权重，再按照段落字符数加权。

`高风险文本占比`：达到高风险阈值的段落字符数 / 全文有效正文字符数。

默认忽略“目录、参考文献、致谢、附录”等章节，以减少对正文统计的干扰。

## 隐私与存储

上传文件通过 HTTP 请求进入服务器内存，当前应用代码**不会主动把论文保存到磁盘、数据库或第三方接口**。但服务器运营者仍应自行处理：

- HTTPS；
- Web 服务器访问日志；
- 反向代理、WAF 或 CDN 的请求策略；
- 宿主机监控与备份策略；
- 多用户环境下的资源限制。

如果论文具有保密要求，建议部署在自己的可信服务器，并使用 HTTPS 和访问控制。

## PDF 限制

PDF 的文字通常是坐标化内容而不是稳定的文档结构。复杂分栏、页眉页脚、公式以及扫描图片可能影响段落和章节识别。扫描版 PDF 请先 OCR，论文检测优先使用 DOCX。

## 健康检查

```bash
curl http://127.0.0.1:8000/healthz
```

返回：

```json
{"status":"ok"}
```

## Release

仓库中的 GitHub Actions 会读取 `VERSION`。当 `master` 分支更新时：

- 若对应 `vX.Y.Z` Release 不存在，会自动创建；
- 自动打包并上传 `.zip` 与 `.tar.gz`；
- 若 Release 已存在，则刷新同版本附件。

发布新版本时修改 `VERSION` 与 `RELEASE_NOTES.md` 后推送即可。
