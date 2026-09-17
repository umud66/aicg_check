from analyzer import analyze_document


def test_long_paragraph_without_citation_does_not_trigger_removed_rule():
    text = (
        "本文围绕组织运行过程中的若干现象展开分析，并结合不同阶段的实际表现进行讨论。"
        "相关内容主要涉及工作流程、信息传递、资源配置、人员协作以及具体执行过程中的变化。"
        "通过对多个环节进行梳理，可以看到不同因素之间存在较为复杂的关联，这些关联会随着情境变化而变化。"
        "因此，分析时需要同时关注过程、条件和结果之间的联系，并避免仅依据单一现象得出结论。"
    )
    results, _ = analyze_document([("第二章 分析", text)], profile="general")
    assert results
    assert "长段落缺少可核查事实或引文" not in results[0].reasons
