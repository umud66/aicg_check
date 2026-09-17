from io import BytesIO

from docx import Document

from analyzer import analyze_document
from app import app


def make_docx() -> BytesIO:
    document = Document()
    document.add_heading("第一章 绪论", level=1)
    document.add_paragraph("首先，应进一步完善基层治理机制。其次，应加强部门之间的协同联动，推动治理资源有效整合。此外，还应不断优化公共服务体系，从而进一步提升基层治理效能。")
    document.add_paragraph("根据2024年公开数据，样本中共有53所学校，其中31所为小学，22所为初中[1]。这一事实用于说明样本结构，而不是泛化提出政策建议。")
    document.add_paragraph("首先，应进一步完善基层治理机制。其次，应加强部门之间的协同联动，推动治理资源有效整合。此外，还应不断优化公共服务体系，从而进一步提升基层治理效能。")
    buffer = BytesIO(); document.save(buffer); buffer.seek(0); return buffer


def test_healthz():
    response = app.test_client().get("/healthz")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_docx_analysis_v02():
    response = app.test_client().post("/api/analyze", data={"file": (make_docx(), "sample.docx"), "medium_threshold": "40", "high_threshold": "65", "profile": "public_management"}, content_type="multipart/form-data")
    assert response.status_code == 200
    payload = response.json
    assert payload["profile"] == "public_management"
    assert payload["summary"]["total_chars"] > 0
    assert "document_signals" in payload["summary"]
    assert payload["summary"]["document_signals"]["cross_duplicate_count"] >= 1
    assert len(payload["results"]) == 3
    assert "lexical_diversity" in payload["results"][0]
    assert "style_shift" in payload["results"][0]


def test_document_style_signals():
    rows = [("第二章", "首先，应当加强机制建设。其次，应当完善治理体系。此外，应当持续推动协同治理，从而进一步提升治理效能。"), ("第二章", "根据2025年调查数据，受访者共126人，其中84人认为流程存在延迟[2]。访谈P03进一步说明审批节点主要集中在两个部门。"), ("第二章", "首先，应当加强机制建设。其次，应当完善治理体系。此外，应当持续推动协同治理，从而进一步提升治理效能。")]
    results, summary = analyze_document(rows, profile="general")
    assert len(results) == 3
    assert summary["document_signals"]["cross_duplicate_count"] >= 1
    assert results[2].cross_match_index == 1


def test_rejects_bad_extension():
    response = app.test_client().post("/api/analyze", data={"file": (BytesIO(b"hello"), "sample.txt")}, content_type="multipart/form-data")
    assert response.status_code == 400


def test_rejects_unknown_profile():
    response = app.test_client().post("/api/analyze", data={"file": (make_docx(), "sample.docx"), "profile": "unknown"}, content_type="multipart/form-data")
    assert response.status_code == 400
