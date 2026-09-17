from io import BytesIO

from docx import Document

from analyzer import analyze_document, extract_docx
from app import app


def make_docx() -> BytesIO:
    document = Document()
    document.add_heading("第一章 绪论", level=1)
    document.add_paragraph("首先，应进一步完善基层治理机制。其次，应加强部门之间的协同联动，推动治理资源有效整合。此外，还应不断优化公共服务体系，从而进一步提升基层治理效能。")
    document.add_paragraph("根据2024年公开数据，样本中共有53所学校，其中31所为小学，22所为初中[1]。这一事实用于说明样本结构，而不是泛化提出政策建议。")
    document.add_paragraph("首先，应进一步完善基层治理机制。其次，应加强部门之间的协同联动，推动治理资源有效整合。此外，还应不断优化公共服务体系，从而进一步提升基层治理效能。")
    buffer = BytesIO(); document.save(buffer); buffer.seek(0); return buffer


def make_structured_docx() -> BytesIO:
    document = Document()
    document.add_paragraph("基于深度学习的测试论文")
    abstract = document.add_table(rows=1, cols=1)
    abstract.cell(0, 0).text = (
        "摘要：随着信息技术的发展，高维数据大规模涌现。针对上述挑战，本文系统研究相关方法。"
        "本文首先构建模型，其次开展对比实验。实验结果表明，模型性能显著提升。本研究为相关任务提供了可行路线。"
    )
    document.add_paragraph("1. 绪论")
    document.add_paragraph("1.2 国内外研究现状")
    document.add_paragraph(
        "相关方法主要分为线性与非线性两大类。经典方法如PCA。为解决非线性问题，近年来深度模型逐渐成为研究热点。"
        "现有研究通常从特征映射、流形保持和重构性能等角度展开讨论，不同方法在计算复杂度、泛化能力和新样本映射方面各有差异。"
        "随着数据规模持续增长，研究者也逐渐关注深层网络在复杂非线性结构提取方面的应用。"
    )
    document.add_paragraph("4. 实验设计与结果分析")
    document.add_paragraph("4.2 实验结果分析")
    document.add_paragraph("实验数据表明，本文模型具有最高准确率和最小重构损失。")
    table = document.add_table(rows=3, cols=3)
    for j, v in enumerate(["方法", "准确率", "MSE"]): table.cell(0, j).text = v
    for j, v in enumerate(["PCA", "88.4", "3.42"]): table.cell(1, j).text = v
    for j, v in enumerate(["本文模型", "96.8", "1.15"]): table.cell(2, j).text = v
    document.add_paragraph("5.2 结论")
    document.add_paragraph("本文针对相关问题系统构建并验证模型。通过多目标约束实现有效压缩。实验结果证实模型具有优越性。后续工作将进一步探索相关应用。")
    document.add_paragraph("参考文献")
    document.add_paragraph("[1] Example reference (2020).")
    buffer = BytesIO(); document.save(buffer); buffer.seek(0); return buffer


def test_healthz():
    response = app.test_client().get("/healthz")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_docx_analysis_v04():
    response = app.test_client().post("/api/analyze", data={"file": (make_docx(), "sample.docx"), "medium_threshold": "40", "high_threshold": "65", "profile": "public_management"}, content_type="multipart/form-data")
    assert response.status_code == 200
    payload = response.json
    assert payload["profile"] == "public_management"
    assert payload["summary"]["total_chars"] > 0
    assert "document_signals" in payload["summary"]
    assert payload["summary"]["document_signals"]["cross_duplicate_count"] >= 1
    assert payload["summary"]["document_signals"]["calibration_center"] == 34.0
    assert "template_score" in payload["results"][0]
    assert "evidence_score" in payload["results"][0]


def test_docx_reads_table_abstract_and_stops_references():
    raw = make_structured_docx().getvalue()
    rows = extract_docx(raw)
    texts = [row[1] for row in rows]
    assert any(text.startswith("摘要：") for text in texts)
    assert any(row[2] == "table_data" for row in rows)
    assert not any("Example reference" in text for text in texts)
    results, summary = analyze_document(rows, profile="general")
    assert summary["document_signals"]["table_data_blocks"] == 1
    assert summary["document_signals"]["citation_gap_score"] == 100
    assert summary["document_signals"]["evidence_gap_score"] > 0
    assert summary["estimated_ratio"] > 50
    assert any(r.section_type == "abstract" for r in results)


def test_document_style_signals():
    rows = [("第二章", "首先，应当加强机制建设。其次，应当完善治理体系。此外，应当持续推动协同治理，从而进一步提升治理效能。"), ("第二章", "根据2025年调查数据，受访者共126人，其中84人认为流程存在延迟[2]。访谈P03进一步说明审批节点主要集中在两个部门。"), ("第二章", "首先，应当加强机制建设。其次，应当完善治理体系。此外，应当持续推动协同治理，从而进一步提升治理效能。")]
    results, summary = analyze_document(rows, profile="general")
    assert len(results) == 3
    assert summary["document_signals"]["cross_duplicate_count"] >= 1
    assert results[2].cross_match_index == 1


def test_section_classification_prefers_heading_over_body_words():
    rows = [
        ("3.3 失败案例与局限性深挖", "从表 1 能看出来，模型整体表现不错，但在 Fashion-MNIST 上出现了衬衫与外套混淆。我们在单卡 RTX 4090 上跑训练，Batch Size 设到 256 时第 30 个 Epoch 出现梯度震荡。"),
        ("4. 总结与改进思考", "这次实测跑下来，模型效果符合预期，但调参成本较高。总结下来，数据归一化和隐层维度需要特别注意，后续计划再比较自监督方法。"),
    ]
    results, summary = analyze_document(rows, profile="general")
    assert results[0].section_type == "experiment"
    assert results[1].section_type == "conclusion"
    assert summary["document_signals"]["calibration_status"] == "provisional-heuristic"


def test_rejects_bad_extension():
    response = app.test_client().post("/api/analyze", data={"file": (BytesIO(b"hello"), "sample.txt")}, content_type="multipart/form-data")
    assert response.status_code == 400


def test_rejects_unknown_profile():
    response = app.test_client().post("/api/analyze", data={"file": (make_docx(), "sample.docx"), "profile": "unknown"}, content_type="multipart/form-data")
    assert response.status_code == 400
