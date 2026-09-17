from __future__ import annotations

import io
import math
import os
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Sequence, Tuple

TRANSITIONS = [
    "首先","其次","再次","最后","此外","同时","因此","由此可见","综上所述","总而言之",
    "值得注意的是","需要指出的是","需要注意的是","从而","进而","一方面","另一方面",
    "具体而言","具体来说","在此基础上","基于此","与此同时","相较而言","总体而言",
    "据此","由此","基于上述","针对上述","实验结果表明","结果表明","鉴于此","值得一提的是",
]
GENERIC_POLICY = [
    "加强","完善","健全","提升","推动","促进","优化","构建","建立","强化","深化","推进",
    "保障","落实","创新","规范","提高","增强","形成","实现","发挥","有效","持续","进一步",
    "统筹","协同","赋能","夯实",
]
ABSTRACT_NOUNS = [
    "机制","体系","水平","能力","效能","质量","路径","模式","格局","作用","意义","价值","需求",
    "问题","发展","建设","治理","管理","服务","协同","保障","改革","维度","逻辑","内涵","范式",
    "结构","特征","模型","表征","性能","效果","方法",
]
FUNCTION_WORDS = ["的","了","在","是","与","和","及","对","为","从","将","其","该","而","并","但","也","等","由","于"]

AIISH_PATTERNS = [
    r"不仅.{0,18}而且", r"既.{0,18}又", r"一方面.{0,40}另一方面",
    r"通过.{0,24}(?:进一步|从而|进而|实现)", r"有助于.{0,30}(?:提升|推动|促进|增强|实现)",
    r"对于.{0,30}(?:具有|有着).{0,16}(?:意义|作用|价值)", r"在.{0,20}背景下",
    r"随着.{0,24}(?:发展|推进|变化|提升|增长|涌现)", r"从.{0,16}角度来看",
    r"既要.{0,30}又要", r"针对上述.{0,35}(?:本文|研究)", r"实验结果(?:表明|显示|证实)",
    r"后续工作将|未来工作将", r"为(?:了)?充分(?:验证|评估)", r"值得一提的是",
]

CITATION_PATTERNS = [
    r"\[[0-9]{1,3}\]",
    r"\[[0-9]{1,3}(?:[-,，][0-9]{1,3})+\]",
    r"（[^）]{1,40}(?:19|20)\d{2}[^）]*）",
    r"\([^)]{1,40}(?:19|20)\d{2}[^)]*\)",
]

PROFILE_CONFIG = {
    "general": {"name":"通用硕士论文","transition":1.0,"generic":1.0,"abstract":1.0,"evidence_discount":1.0},
    "public_management": {"name":"公共管理 / 政策类论文","transition":0.9,"generic":0.68,"abstract":0.82,"evidence_discount":1.08},
    "strict": {"name":"严格模式","transition":1.14,"generic":1.10,"abstract":1.08,"evidence_discount":0.90},
}

SECTION_PATTERNS = {
    "abstract": [r"^摘要", r"摘要(?:：|:)"],
    "literature": [r"研究现状", r"文献综述", r"国内外研究", r"相关研究"],
    "theory": [r"相关理论", r"基本原理", r"理论基础", r"原理"],
    "method": [
        r"模型设计", r"模型构建", r"研究方法", r"网络结构", r"架构", r"架构设计", r"算子选择",
        r"优化策略", r"工程调优", r"训练过程", r"解决方案", r"方法设计",
    ],
    "experiment": [
        r"实验", r"实测", r"测试结果", r"指标对比", r"结果分析", r"数据集",
        r"失败案例", r"局限性", r"实证",
    ],
    "conclusion": [r"结论", r"讨论与总结", r"结果讨论", r"总结与展望", r"总结", r"改进思考", r"展望"],
    "references": [r"^参考文献$", r"^References$"],
}

TEMPLATE_PATTERNS = {
    "abstract": [
        r"随着.{0,30}(?:发展|增长|涌现)", r"针对上述.{0,35}",
        r"本文(?:系统)?(?:研究|提出|构建|设计)", r"本文首先", r"其次",
        r"实验结果(?:表明|显示|证实)", r"本研究.{0,35}(?:提供|具有|形成)",
    ],
    "literature": [
        r"主要分为.{0,30}两大类", r"经典的.{0,30}如", r"虽然.{0,50}但",
        r"为解决.{0,25}问题", r"近年来", r"逐渐成为.{0,30}(?:热点|方向)",
    ],
    "experiment": [
        r"为(?:了)?(?:充分)?(?:评估|验证).{0,40}(?:效果|性能|能力)",
        r"在.{0,30}(?:数据集|空间)后", r"实验数据(?:表明|显示)",
        r"具有最(?:高|小|优)", r"显著(?:提升|降低|优于)",
    ],
    "conclusion": [
        r"本文针对", r"系统(?:构建|研究|设计|验证)", r"通过.{0,40}(?:实现|提升|构建)",
        r"实验结果(?:表明|证实|显示)", r"后续工作将|未来(?:工作)?将|后续(?:计划|考虑|拟)",
        r"进一步(?:拓展|提升|研究|探索)",
    ],
}

CLAIM_WORDS = ["显著","优越","最高","最小","优异","强大","有效","大幅","极大","明显提升","显著降低","最佳","领先"]
CAVEAT_WORDS = ["限制","不足","异常","失败","误差","标准差","方差","置信区间","噪声","偏差","局限","代价","敏感性","问题","震荡","模糊","混淆"]

EXPERIMENT_DETAIL_GROUPS = {
    "split": ["训练集","验证集","测试集","train","validation","test","划分比例"],
    "seed": ["随机种子","random seed","seed"],
    "epoch": ["epoch","轮训练","训练轮数"],
    "batch": ["batch","批大小","batch size"],
    "hardware": ["GPU","CPU","显卡","显存","RTX","A100","V100","MPS","CUDA","单卡"],
    "optimizer": ["Adam","AdamW","SGD","优化器"],
    "lr": ["学习率","learning rate","1e-"],
    "regularization": ["dropout","weight decay","权重衰减","梯度裁剪","gradient clipping","早停","L1","稀疏约束"],
    "uncertainty": ["标准差","方差","置信区间","重复实验","多次实验","显著性检验"],
    "ablation": ["消融","ablation","敏感性分析","超参数分析"],
    "failure": ["失败案例","神经元死亡","梯度消失","梯度震荡","模糊","混淆","无法区分","踩坑"],
    "time_cost": ["耗费了","小时","天时间","训练耗时","秒","分钟"],
}

HUMAN_DETAIL_PATTERNS = [
    r"踩坑", r"跑了一下", r"跑训练", r"死了(?:一大片)?", r"神经元(?:死亡|死)",
    r"耗费了.{0,12}(?:小时|天)", r"让人头疼", r"才(?:终于)?(?:稳住|收敛|好转)",
    r"不光.{0,20}还", r"扔进", r"卡死", r"搞了几组", r"这事", r"情况才",
    r"第\s*\d+\s*个\s*Epoch", r"RTX\s*\d+", r"Threshold\s*=\s*[\d.]+",
    r"alpha\s*=\s*[\d.]+", r"Lambda\s*=\s*[\deE.+-]+", r"Batch\s*Size\s*设到\s*\d+",
]
COLLOQUIAL_PATTERNS = [
    r"搞", r"踩坑", r"跑得", r"扔进", r"不行", r"卡死", r"头疼", r"稳住",
    r"一大片", r"直接", r"同学应该都有体会", r"这事", r"一点", r"拉高一个台阶",
]

@dataclass
class ParagraphResult:
    index:int
    chapter:str
    section_type:str
    block_kind:str
    text:str
    chars:int
    score:float
    level:str
    reasons:str
    transition_density:float
    generic_density:float
    citation_count:int
    digit_density:float
    sentence_cv:float
    repetition_score:float
    lexical_diversity:float=0.0
    style_shift:float=0.0
    cross_similarity:float=0.0
    cross_match_index:int=0
    context_adjustment:float=0.0
    sentence_mean:float=0.0
    function_density:float=0.0
    punctuation_entropy:float=0.0
    template_score:float=0.0
    evidence_score:float=0.0
    lm_score:float|None=None

def _clean_text(text:str)->str:
    text=(text or "").replace("\u3000"," ").replace("\xa0"," ").replace("\ufeff","")
    return re.sub(r"\n{3,}","\n\n",re.sub(r"[ \t]+"," ",text)).strip()

def _compact(text:str)->str:
    return re.sub(r"[\s，。！？；：、“”‘’（）()\[\]【】{}《》,.!?;:'\"\-—…·]","",text)

def _visible_chars(text:str)->int:
    return len(re.sub(r"\s+","",text or ""))

def _sentences(text:str)->List[str]:
    return [p.strip() for p in re.split(r"(?<=[。！？!?；;])",text or "") if _visible_chars(p)>=4]

def _mean(xs:Sequence[float])->float:
    return sum(xs)/len(xs) if xs else 0.0

def _cv(xs:Sequence[float])->float:
    if len(xs)<2:return 1.0
    m=_mean(xs)
    return math.sqrt(sum((x-m)**2 for x in xs)/len(xs))/m if m else 0.0

def _count_hits(text:str,lexicon:Sequence[str])->int:
    return sum(text.count(x) for x in lexicon)

def _citation_count(text:str)->int:
    return sum(len(re.findall(p,text,re.I)) for p in CITATION_PATTERNS)

def _digit_density(text:str)->float:
    c=_visible_chars(text)
    return len(re.findall(r"\d",text))/c if c else 0.0

def _ngram_repetition(text:str,n:int=4)->float:
    c=_compact(text)
    if len(c)<n*3:return 0.0
    grams=[c[i:i+n] for i in range(len(c)-n+1)]
    counts=Counter(grams)
    return min(1.0,sum(v-1 for v in counts.values() if v>1)/max(1,len(grams))*4)

def _lexical_diversity(text:str)->float:
    c=_compact(text)
    if len(c)<12:return 0.0
    grams=[c[i:i+2] for i in range(len(c)-1)]
    return len(set(grams))/max(1,len(grams))

def _function_density(text:str)->float:
    c=max(1,_visible_chars(text))
    return sum(text.count(w) for w in FUNCTION_WORDS)/c*100

def _punctuation_entropy(text:str)->float:
    groups=["，,、","。.!！?？","；;","：:","（）()[]【】","“”‘’\"'《》","—-"]
    counts=[sum(text.count(ch) for ch in g) for g in groups]
    total=sum(counts)
    if total<=1:return 0.0
    probs=[x/total for x in counts if x]
    ent=-sum(p*math.log(p) for p in probs)
    return ent/math.log(len(probs)) if len(probs)>1 else 0.0

def _start_prefix(text:str)->str:
    ss=_sentences(text)
    if not ss:return ""
    x=_compact(re.sub(r"^[（(\d一二三四五六七八九十、.．\s]+","",ss[0]))
    return x[:4]

def _shingles(text:str,n:int=5)->set:
    c=_compact(text)
    if len(c)<n:return {c} if c else set()
    return {c[i:i+n] for i in range(len(c)-n+1)}

def _jaccard(a:set,b:set)->float:
    return len(a&b)/len(a|b) if a and b else 0.0

def _level(score:float,medium:int,high:int)->str:
    return "高" if score>=high else ("中" if score>=medium else "低")

def _section_type(chapter:str,text:str="")->str:
    chapter=_clean_text(chapter or "")
    for name,patterns in SECTION_PATTERNS.items():
        if any(re.search(p,chapter,re.I) for p in patterns):
            return name
    if re.match(r"^1(?:\.|\s)",chapter):
        return "introduction"
    if chapter in {"正文","PDF正文","未识别章节",""}:
        probe=_clean_text(text[:60])
        if probe.startswith(("摘要：","摘要:")):
            return "abstract"
    return "body"

def _is_heading(text:str,style:str="")->bool:
    if style.lower().startswith("heading") or style.startswith("标题"):
        return True
    x=_clean_text(text)
    if _visible_chars(x)>55:return False
    if any(re.match(p,x,re.I) for p in [r"^摘要$",r"^关键词",r"^参考文献$",r"^致谢$",r"^附录(?:\s|$)",r"^References$"]):
        return True
    return bool(re.match(r"^(第[一二三四五六七八九十百0-9]+[章节篇]|[1-9]\d*(?:\.\d+){0,3}[\.．]?\s*)",x))

def _looks_formula(text:str)->bool:
    c=_visible_chars(text)
    if c<8:return False
    chinese=len(re.findall(r"[\u4e00-\u9fff]",text))
    mathish=len(re.findall(r"[=∈Σλθφσ̂₂²×→+\-*/^]",text))
    return mathish>=2 and chinese/max(1,c)<0.28

def _template_hits(section:str,text:str)->Tuple[int,List[str]]:
    pats=TEMPLATE_PATTERNS.get(section,[])
    hits=[p for p in pats if re.search(p,text,re.I)]
    return len(hits),hits

def _detail_groups(text:str)->set:
    low=text.lower()
    found=set()
    for name,items in EXPERIMENT_DETAIL_GROUPS.items():
        if any(x.lower() in low for x in items):
            found.add(name)
    return found

def _human_detail_score(text:str)->float:
    chars=max(1,_visible_chars(text))
    hits=sum(1 for p in HUMAN_DETAIL_PATTERNS if re.search(p,text,re.I))
    colloq=sum(1 for p in COLLOQUIAL_PATTERNS if re.search(p,text,re.I))
    numeric_specific=len(re.findall(r"(?:\d+(?:\.\d+)?%|(?:alpha|lambda|threshold|batch(?: size)?|epoch|lr|学习率)\s*[=:设到为]*\s*[\deE.+-]+)",text,re.I))
    caveat=sum(text.count(w) for w in CAVEAT_WORDS)
    raw=hits*10 + colloq*4 + min(20,numeric_specific*4) + min(15,caveat*3)
    if chars<80:raw*=0.7
    return min(100,raw)

def _base_features(text:str,profile:str="general",section:str="body")->Dict[str,Any]:
    cfg=PROFILE_CONFIG.get(profile,PROFILE_CONFIG["general"])
    text=_clean_text(text)
    chars=_visible_chars(text)
    ss=_sentences(text)
    lengths=[_visible_chars(s) for s in ss]
    td=_count_hits(text,TRANSITIONS)/max(1,chars)*100
    gd=_count_hits(text,GENERIC_POLICY)/max(1,chars)*100
    ad=_count_hits(text,ABSTRACT_NOUNS)/max(1,chars)*100
    cites=_citation_count(text)
    digits=_digit_density(text)
    rep=_ngram_repetition(text)
    patterns=sum(1 for p in AIISH_PATTERNS if re.search(p,text,re.I))
    scv=_cv(lengths)
    lex=_lexical_diversity(text)
    th,_=_template_hits(section,text)
    template_score=min(100,th/max(1,len(TEMPLATE_PATTERNS.get(section,[])))*100) if TEMPLATE_PATTERNS.get(section) else 0.0
    human=_human_detail_score(text)

    score=10.0
    reasons=[]

    if td>=1.25:
        add=min(18,7+td*4)*cfg["transition"];score+=add;reasons.append((add,"模板化连接/总结表达密度较高"))
    elif td>=0.5:
        add=6*cfg["transition"];score+=add;reasons.append((add,"连接与总结表达偏规律"))

    if gd>=2.8:
        add=min(12,4+gd*1.5)*cfg["generic"];score+=add;reasons.append((add,"泛化动词密度偏高"))
    elif gd>=1.5:
        add=4.5*cfg["generic"];score+=add;reasons.append((add,"泛化动词偏多"))

    if ad>=5:
        add=5.5*cfg["abstract"];score+=add;reasons.append((add,"抽象概念密集"))

    if len(lengths)>=4:
        if scv<0.22:
            score+=11;reasons.append((11,"段内句长分布过于均匀"))
        elif scv<0.36:
            score+=5;reasons.append((5,"段内句式节奏较规则"))

    if patterns:
        add=min(18,patterns*5.5);score+=add;reasons.append((add,f"命中 {patterns} 类高频生成式句式"))

    if rep>=0.12:
        add=min(9,rep*26);score+=add;reasons.append((add,"段内短语重复度偏高"))

    if chars>=150 and lex<0.60:
        score+=4;reasons.append((4,"词汇/短语多样性偏低"))

    if th>=4:
        score+=21;reasons.append((21,f"{section} 章节模板链高度完整"))
    elif th>=3:
        score+=14;reasons.append((14,f"{section} 章节模板链明显"))
    elif th>=2:
        score+=7;reasons.append((7,f"{section} 章节存在模板化结构"))

    claim_hits=sum(text.count(w) for w in CLAIM_WORDS)
    caveat_hits=sum(text.count(w) for w in CAVEAT_WORDS)
    if claim_hits>=2 and caveat_hits==0:
        add=min(10,3+claim_hits*2);score+=add;reasons.append((add,"强结论/优势表述集中且缺少限制性讨论"))

    if section=="literature" and chars>=100 and cites==0:
        score+=12;reasons.append((12,"研究现状段落缺少逐项文献引用"))

    if chars>=160 and cites==0 and digits<0.004 and human<25:
        score+=5;reasons.append((5,"长段落缺少可核查事实或引文"))

    citation_discount=min(10,cites*3.5*cfg["evidence_discount"])
    if citation_discount:
        score-=citation_discount

    if chars<45:score*=0.68
    elif chars<80:score*=0.88

    score=max(4.0,score)
    return {
        "score":score,"reasons":reasons,"chars":chars,"sentence_cv":scv,"sentence_mean":_mean(lengths),
        "transition_density":td,"generic_density":gd,"citation_count":cites,"digit_density":digits,
        "repetition_score":rep,"lexical_diversity":lex,"function_density":_function_density(text),
        "punctuation_entropy":_punctuation_entropy(text),"start_prefix":_start_prefix(text),
        "shingles":_shingles(text),"template_score":template_score,"detail_groups":_detail_groups(text),
        "human_detail_score":human,
    }

def _load_lm():
    if os.getenv("AICG_LM_ENABLE","0")!="1":
        return None,"disabled"
    try:
        from lm_scorer import LocalPerplexityScorer
        return LocalPerplexityScorer(os.getenv("AICG_LM_MODEL","uer/gpt2-chinese-cluecorpussmall")),"enabled"
    except Exception as exc:
        return None,f"unavailable: {exc}"

def extract_docx(data:bytes)->List[Tuple[str,str,str]]:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document=Document(io.BytesIO(data))
    rows=[]
    current="正文"
    stopped=False

    def add_text(text:str,kind:str="paragraph"):
        nonlocal current,stopped
        text=_clean_text(text)
        if not text or stopped:return
        if re.match(r"^参考文献\s*$",text,re.I) or re.match(r"^References\s*$",text,re.I):
            stopped=True;return
        if current=="正文" and not rows and _visible_chars(text)<=65 and not re.search(r"[。！？!?；;]",text):
            return
        if text.startswith("摘要：") or text.startswith("摘要:"):
            current="摘要";rows.append((current,text,kind));return
        if _is_heading(text):
            current=text;return
        if re.match(r"^关键词[:：]",text):
            current="摘要"
        if current in {"目录","致谢"} or current.startswith("附录"):
            return
        rows.append((current,text,kind))

    for child in document.element.body.iterchildren():
        if child.tag.endswith("}p"):
            p=Paragraph(child,document)
            add_text(p.text,"paragraph")
        elif child.tag.endswith("}tbl"):
            table=Table(child,document)
            cells=[[_clean_text(c.text) for c in row.cells] for row in table.rows]
            nonempty=[c for row in cells for c in row if c]
            if not nonempty:continue
            if len(cells)==1 and len(cells[0])==1:
                add_text(cells[0][0],"table_text")
            else:
                table_text=" | ".join(" ; ".join(c for c in row if c) for row in cells if any(row))
                if not stopped:
                    rows.append((current,table_text,"table_data"))
    return rows

def extract_pdf(data:bytes)->List[Tuple[str,str,str]]:
    from pypdf import PdfReader
    reader=PdfReader(io.BytesIO(data))
    rows=[]
    current="PDF正文"
    stopped=False
    for page_no,page in enumerate(reader.pages,start=1):
        text=(page.extract_text() or "").replace("\r","\n")
        lines=[_clean_text(x) for x in text.splitlines() if _clean_text(x)]
        buf=""
        for line in lines:
            if stopped:break
            if re.match(r"^参考文献\s*$",line,re.I):
                stopped=True;break
            if line.startswith("摘要：") or line.startswith("摘要:"):
                if buf:rows.append((f"{current}（第{page_no}页）",buf,"paragraph"));buf=""
                current="摘要";rows.append((current,line,"paragraph"));continue
            if _is_heading(line):
                if buf:rows.append((f"{current}（第{page_no}页）",buf,"paragraph"));buf=""
                current=line;continue
            buf += line
            if line.endswith(("。","！","？",";","；")) and len(buf)>=100:
                rows.append((f"{current}（第{page_no}页）",buf,"paragraph"));buf=""
        if buf and not stopped:
            rows.append((f"{current}（第{page_no}页）",buf,"paragraph"))
    return rows

def _normalize_rows(rows):
    out=[]
    for row in rows:
        if len(row)>=3:chapter,text,kind=row[:3]
        else:chapter,text=row;kind="paragraph"
        out.append((chapter,text,kind))
    return out

def analyze_document(rows,medium_threshold:int=40,high_threshold:int=65,profile:str="general"):
    rows=_normalize_rows(rows)
    results=[]
    features=[]
    data_blocks=[]
    lm,lm_status=_load_lm()

    for index,(chapter,text,kind) in enumerate(rows,start=1):
        chars=_visible_chars(text)
        if chars<10:continue
        section=_section_type(chapter,text)
        if kind=="table_data":
            data_blocks.append((chapter,text))
            continue
        if _looks_formula(text):
            continue
        f=_base_features(text,profile,section)
        lm_score=None
        if lm and f["chars"]>=60:
            try:
                lm_score=lm.risk_score(text)
                f["score"] += max(0,(lm_score-50)*0.25)
                if lm_score>=70:f["reasons"].append((8,"本地语言模型预测文本可预测性偏高"))
            except Exception:
                pass

        score=max(0,min(100,round(f["score"],1)))
        positive=[r for w,r in sorted(f["reasons"],key=lambda x:abs(x[0]),reverse=True) if w>0][:5]
        if not positive:positive=["未发现明显模板化特征"]
        results.append(ParagraphResult(
            index,chapter or "未识别章节",section,kind,_clean_text(text),f["chars"],score,
            _level(score,medium_threshold,high_threshold),"；".join(positive),
            round(f["transition_density"],2),round(f["generic_density"],2),f["citation_count"],
            round(f["digit_density"]*100,2),round(f["sentence_cv"],3),round(f["repetition_score"],3),
            round(f["lexical_diversity"],3),sentence_mean=round(f["sentence_mean"],1),
            function_density=round(f["function_density"],2),punctuation_entropy=round(f["punctuation_entropy"],3),
            template_score=round(f["template_score"],1),evidence_score=round(f["human_detail_score"],1),
            lm_score=None if lm_score is None else round(lm_score,1)
        ))
        features.append(f)

    total_chars=sum(r.chars for r in results)
    if not total_chars:
        return results,{"total_chars":0,"weighted_score":0,"estimated_ratio":0,"high_ratio":0,
                        "medium_high_ratio":0,"chapters":[],"document_signals":{}}

    for i,r in enumerate(results):
        best=0.0;best_idx=0
        for j in range(max(0,i-50),i):
            sim=_jaccard(features[i]["shingles"],features[j]["shingles"])
            if sim>best:best=sim;best_idx=results[j].index
        r.cross_similarity=round(best,3);r.cross_match_index=best_idx
        if best>=0.42 and r.chars>=60:
            add=min(13,4+(best-0.42)*28)
            r.score=min(100,round(r.score+add,1));r.context_adjustment+=round(add,1)
            r.reasons+=f"；与段落 #{best_idx} 存在较高跨段相似"

    for i in range(1,len(results)):
        a,b=results[i-1],results[i]
        if a.chapter!=b.chapter:continue
        fa,fb=features[i-1],features[i]
        d=abs(fa["sentence_mean"]-fb["sentence_mean"])/max(20,(fa["sentence_mean"]+fb["sentence_mean"])/2)
        d+=abs(fa["transition_density"]-fb["transition_density"])/4
        d+=abs(fa["generic_density"]-fb["generic_density"])/6
        d+=abs(fa["lexical_diversity"]-fb["lexical_diversity"])*1.2
        d+=abs(fa["function_density"]-fb["function_density"])/9
        b.style_shift=round(min(1.5,d/3),3)

    by_chapter=defaultdict(list)
    for r in results:
        if r.chars>=55:
            by_chapter[r.chapter].extend([_visible_chars(s) for s in _sentences(r.text)])
    low_burst_chapters={}
    for ch,lens in by_chapter.items():
        if len(lens)>=4:
            cv=_cv(lens)
            if cv<0.34:low_burst_chapters[ch]=cv
    for r in results:
        if r.chapter in low_burst_chapters and r.chars>=70:
            add=12 if low_burst_chapters[r.chapter]<0.24 else 7
            r.score=min(100,round(r.score+add,1));r.context_adjustment+=add
            r.reasons+="；本章节句长突发性偏低、节奏较稳定"

    prefixes=[features[i]["start_prefix"] for i in range(len(features)) if features[i]["start_prefix"]]
    pc=Counter(prefixes)
    repeated={p for p,n in pc.items() if n>=3}
    for i,r in enumerate(results):
        p=features[i]["start_prefix"]
        if p and p in repeated and r.chars>=70:
            r.score=min(100,round(r.score+4,1));r.context_adjustment+=4
            r.reasons+=f"；全文多次出现相同句首“{p}”"

    exp_text="\n".join(r.text for r in results if r.section_type in {"experiment","method"})
    exp_text += "\n" + "\n".join(t for ch,t in data_blocks if _section_type(ch,t) in {"experiment","method"})
    detail_groups=_detail_groups(exp_text)
    result_numbers=len(re.findall(r"\b\d+(?:\.\d+)?%?\b",exp_text))
    evidence_gap=0
    if result_numbers>=8 and len(detail_groups)<=3:evidence_gap=85
    elif result_numbers>=5 and len(detail_groups)<=4:evidence_gap=65
    elif result_numbers>=3 and len(detail_groups)<=2:evidence_gap=55

    if evidence_gap:
        for r in results:
            if r.section_type=="experiment" and r.chars>=60:
                add=12 if evidence_gap>=75 else 7
                r.score=min(100,round(r.score+add,1));r.context_adjustment+=add
                r.reasons+="；实验结果较完整但可复现过程细节不足"

    for r in results:
        r.level=_level(r.score,medium_threshold,high_threshold)

    prose=[r for r in results if r.chars>=55]
    para_lengths=[r.chars for r in prose]
    sentence_means=[r.sentence_mean for r in prose if r.sentence_mean>0]
    length_cv=_cv(para_lengths)
    sentence_mean_cv=_cv(sentence_means)

    template_sections={}
    for sec in ["abstract","literature","experiment","conclusion"]:
        vals=[r.template_score for r in results if r.section_type==sec]
        if vals:template_sections[sec]=round(max(vals),1)

    citation_gap=100 if any(
        r.section_type=="literature" and r.chars>=100 and r.citation_count==0 for r in results
    ) else 0

    burst_score=0
    if low_burst_chapters:
        vals=list(low_burst_chapters.values())
        burst_score=min(100,50+sum(max(0,0.34-v) for v in vals)/len(vals)*180)

    template_doc=_mean(list(template_sections.values())) if template_sections else 0
    evidence_doc=evidence_gap
    citation_doc=citation_gap
    repeated_doc=min(100,len(repeated)*18)

    human_scores=[features[i]["human_detail_score"] for i in range(len(features)) if results[i].chars>=55]
    human_doc=round(_mean(human_scores),1) if human_scores else 0.0

    applicable=[template_doc]
    if burst_score:applicable.append(burst_score)
    if evidence_doc:applicable.append(evidence_doc)
    if citation_doc:applicable.append(citation_doc)
    if repeated_doc:applicable.append(repeated_doc)
    doc_signal_score=round(_mean(applicable),1)

    weighted_para=sum(r.score*r.chars for r in results)/total_chars
    lm_vals=[r.lm_score for r in results if r.lm_score is not None]
    strong=sum(1 for x in [template_doc,burst_score,evidence_doc,citation_doc] if x>=75)
    synergy=12 if strong>=3 else (6 if strong==2 else 0)

    if lm_vals:
        lm_doc=_mean(lm_vals)
        final_score=0.50*weighted_para+0.35*doc_signal_score+0.15*lm_doc+synergy
    else:
        lm_doc=None
        final_score=0.55*weighted_para+0.45*doc_signal_score+synergy

    final_score=max(0,min(100,round(final_score,1)))

    center=float(os.getenv("AICG_CALIBRATION_CENTER","34"))
    scale=max(4.0,float(os.getenv("AICG_CALIBRATION_SCALE","12")))
    estimated_ratio=100/(1+math.exp(-(final_score-center)/scale))

    high_chars=sum(r.chars for r in results if r.level=="高")
    mh_chars=sum(r.chars for r in results if r.level in ("中","高"))

    chapter_map=defaultdict(lambda:{"chars":0,"weighted":0.0,"high":0,"mh":0,"p":0,"lex":[],"sent":[]})
    for r in results:
        x=chapter_map[r.chapter]
        x["chars"]+=r.chars;x["weighted"]+=r.score*r.chars;x["p"]+=1
        x["lex"].append(r.lexical_diversity);x["sent"].append(r.sentence_mean)
        if r.level=="高":x["high"]+=r.chars
        if r.level in ("中","高"):x["mh"]+=r.chars

    chapters=[]
    for ch,x in chapter_map.items():
        c=x["chars"]
        chapters.append({
            "chapter":ch,"chars":c,"avg_score":round(x["weighted"]/c,1),
            "high_ratio":round(x["high"]/c*100,1),"medium_high_ratio":round(x["mh"]/c*100,1),
            "paragraphs":x["p"],"lexical_diversity":round(_mean(x["lex"]),3),
            "sentence_mean":round(_mean(x["sent"]),1),
        })
    chapters.sort(key=lambda x:x["avg_score"],reverse=True)

    signals={
        "profile":profile,"profile_name":PROFILE_CONFIG.get(profile,PROFILE_CONFIG["general"])["name"],
        "paragraph_length_cv":round(length_cv,3),"sentence_mean_cv":round(sentence_mean_cv,3),
        "cross_duplicate_count":sum(1 for r in results if r.cross_similarity>=0.42),
        "style_shift_count":sum(1 for r in results if r.style_shift>=0.52),
        "repeated_sentence_starts":sorted(repeated),
        "avg_lexical_diversity":round(_mean([r.lexical_diversity for r in results]),3),
        "avg_function_density":round(_mean([r.function_density for r in results]),2),
        "low_burstiness_chapters":{k:round(v,3) for k,v in low_burst_chapters.items()},
        "template_sections":template_sections,
        "experiment_detail_groups":sorted(detail_groups),
        "experiment_result_number_count":result_numbers,
        "evidence_gap_score":evidence_gap,
        "citation_gap_score":citation_gap,
        "document_signal_score":doc_signal_score,
        "human_evidence_score":human_doc,
        "signal_synergy":synergy,
        "lm_status":lm_status,
        "lm_document_score":None if lm_doc is None else round(lm_doc,1),
        "table_data_blocks":len(data_blocks),
        "calibration_center":center,
        "calibration_scale":scale,
        "calibration_status":"provisional-heuristic",
    }
    summary={
        "total_chars":total_chars,
        "weighted_score":final_score,
        "paragraph_weighted_score":round(weighted_para,1),
        "estimated_ratio":round(estimated_ratio,1),
        "high_ratio":round(high_chars/total_chars*100,1),
        "medium_high_ratio":round(mh_chars/total_chars*100,1),
        "chapters":chapters,
        "document_signals":signals,
    }
    return results,summary

def results_as_dicts(results:List[ParagraphResult])->List[Dict]:
    return [asdict(r) for r in results]
