from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import RequestEntityTooLarge

from analyzer import PROFILE_CONFIG, analyze_document, extract_docx, extract_pdf, results_as_dicts

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
app.config["JSON_AS_ASCII"] = False

@app.get("/")
def index():
    return render_template("index.html", max_upload_mb=MAX_UPLOAD_MB, profiles=PROFILE_CONFIG)

@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok"})

@app.post("/api/analyze")
def api_analyze():
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return jsonify({"error": "请选择 DOCX 或 PDF 文件。"}), 400
    filename = uploaded.filename.strip(); suffix = Path(filename).suffix.lower()
    if suffix not in {".docx", ".pdf"}:
        return jsonify({"error": "仅支持 .docx 和 .pdf 文件。"}), 400
    try:
        medium = int(request.form.get("medium_threshold", "40")); high = int(request.form.get("high_threshold", "65"))
    except ValueError:
        return jsonify({"error": "风险阈值必须是整数。"}), 400
    if not (25 <= medium <= 60 and 50 <= high <= 85 and high > medium):
        return jsonify({"error": "阈值无效：中风险 25–60，高风险 50–85，且高风险必须高于中风险。"}), 400
    profile = request.form.get("profile", "general")
    if profile not in PROFILE_CONFIG:
        return jsonify({"error": "未知分析配置。"}), 400
    data = uploaded.read()
    if not data:
        return jsonify({"error": "文件内容为空。"}), 400
    try:
        if suffix == ".docx":
            if not data.startswith(b"PK"): return jsonify({"error": "文件扩展名是 DOCX，但内容不像有效的 Office 文档。"}), 400
            rows = extract_docx(data)
        else:
            if not data.startswith(b"%PDF"): return jsonify({"error": "文件扩展名是 PDF，但内容不像有效的 PDF 文件。"}), 400
            rows = extract_pdf(data)
        results, summary = analyze_document(rows, medium, high, profile)
    except Exception as exc:
        app.logger.exception("document parse failed")
        return jsonify({"error": f"文档解析失败：{exc}"}), 422
    if not results:
        return jsonify({"error": "没有提取到足够的正文。扫描版 PDF 请先 OCR，或改用 DOCX。"}), 422
    return jsonify({"filename": filename,"medium_threshold": medium,"high_threshold": high,"profile": profile,"profile_name": PROFILE_CONFIG[profile]["name"],"summary": summary,"results": results_as_dicts(results),"notice": "本结果为可解释的多层文本风险分析，不等同于任何商业平台或学校系统的官方 AIGC 检测。"})

@app.errorhandler(RequestEntityTooLarge)
def handle_large_file(_error):
    return jsonify({"error": f"文件过大，当前服务器限制为 {MAX_UPLOAD_MB} MB。"}), 413

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_DEBUG") == "1")
