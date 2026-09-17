from __future__ import annotations

import io
import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from statistics import median
from typing import Dict, List, Sequence, Tuple

TRANSITIONS = ["首先","其次","再次","最后","此外","同时","因此","由此可见","综上所述","总而言之","值得注意的是","需要指出的是","需要注意的是","从而","进而","一方面","另一方面","具体而言","具体来说","在此基础上","基于此","与此同时","相较而言","总体而言","据此","由此","基于上述"]
GENERIC_POLICY = ["加强","完善","健全","提升","推动","促进","优化","构建","建立","强化","深化","推进","保障","落实","创新","规范","提高","增强","形成","实现","发挥","有效","持续","进一步","统筹","协同","赋能","夯实"]
ABSTRACT_NOUNS = ["机制","体系","水平","能力","效能","质量","路径","模式","格局","作用","意义","价值","需求","问题","发展","建设","治理","管理","服务","协同","保障","改革","维度","逻辑","内涵","范式"]
FUNCTION_WORDS = ["的","了","在","是","与","和","及","对","为","从","将","其","该","而","并","但","也","等","由","于"]
AIISH_PATTERNS = [r"不仅.{0,18}而且",r"既.{0,18}又",r"一方面.{0,40}另一方面",r"通过.{0,24}(?:进一步|从而|进而|实现)",r"有助于.{0,30}(?:提升|推动|促进|增强|实现)",r"对于.{0,30}(?:具有|有着).{0,16}(?:意义|作用|价值)",r"在.{0,20}背景下",r"随着.{0,24}(?:发展|推进|变化|提升)",r"从.{0,16}角度来看",r"既要.{0,30}又要"]
CITATION_PATTERNS = [r"\[[0-9]{1,3}\]",r"\[[0-9]{1,3}(?:[-,，][0-9]{1,3})+\]",r"（[^）]{1,40}(?:19|20)\d{2}[^）]*）",r"\([^)]{1,40}(?:19|20)\d{2}[^)]*\)"]
SKIP_SECTION_PATTERNS = [r"^目录$", r"^参考文献$", r"^致谢$", r"^附录(?:\s|$)"]
PROFILE_CONFIG = {
    "general": {"name":"通用硕士论文","transition":1.0,"generic":1.0,"abstract":1.0,"discount":1.0},
    "public_management": {"name":"公共管理 / 政策类论文","transition":0.92,"generic":0.66,"abstract":0.78,"discount":1.15},
    "strict": {"name":"严格模式","transition":1.12,"generic":1.12,"abstract":1.08,"discount":0.9},
}

@dataclass
class ParagraphResult:
    index:int; chapter:str; text:str; chars:int; score:float; level:str; reasons:str
    transition_density:float; generic_density:float; citation_count:int; digit_density:float
    sentence_cv:float; repetition_score:float; lexical_diversity:float=0.0; style_shift:float=0.0
    cross_similarity:float=0.0; cross_match_index:int=0; context_adjustment:float=0.0
    sentence_mean:float=0.0; function_density:float=0.0; punctuation_entropy:float=0.0

def _clean_text(text:str)->str:
    text=text.replace("\u3000"," ").replace("\xa0"," ").replace("\ufeff","")
    return re.sub(r"\n{3,}","\n\n",re.sub(r"[ \t]+"," ",text)).strip()
def _compact(text:str)->str:return re.sub(r"[\s，。！？；：、“”‘’（）()\[\]【】{}《》,.!?;:'\"\-—…·]","",text)
def _visible_chars(text:str)->int:return len(re.sub(r"\s+","",text))
def _sentences(text:str)->List[str]:return [p.strip() for p in re.split(r"(?<=[。！？!?；;])",text) if _visible_chars(p)>=4]
def _mean(xs:Sequence[float])->float:return sum(xs)/len(xs) if xs else 0.0
def _cv(xs:Sequence[float])->float:
    if len(xs)<2:return 1.0
    m=_mean(xs)
    return math.sqrt(sum((x-m)**2 for x in xs)/len(xs))/m if m else 0.0
def _count_hits(text:str,lexicon:Sequence[str])->int:return sum(text.count(x) for x in lexicon)
def _citation_count(text:str)->int:return sum(len(re.findall(p,text)) for p in CITATION_PATTERNS)
def _digit_density(text:str)->float:
    c=_visible_chars(text);return len(re.findall(r"\d",text))/c if c else 0.0
def _ngram_repetition(text:str,n:int=4)->float:
    c=_compact(text)
    if len(c)<n*3:return 0.0
    grams=[c[i:i+n] for i in range(len(c)-n+1)];counts=Counter(grams)
    return min(1.0,sum(v-1 for v in counts.values() if v>1)/max(1,len(grams))*4)
def _pattern_hits(text:str)->int:return sum(1 for p in AIISH_PATTERNS if re.search(p,text))
def _lexical_diversity(text:str)->float:
    c=_compact(text)
    if len(c)<12:return 0.0
    grams=[c[i:i+2] for i in range(len(c)-1)]
    return len(set(grams))/max(1,len(grams))
def _function_density(text:str)->float:
    c=max(1,_visible_chars(text));return sum(text.count(w) for w in FUNCTION_WORDS)/c*100
def _punctuation_entropy(text:str)->float:
    groups=["，,、","。.!！?？","；;","：:","（）()[]【】","“”‘’\"'《》"]
    counts=[sum(text.count(ch) for ch in g) for g in groups];total=sum(counts)
    if total<=1:return 0.0
    probs=[x/total for x in counts if x];ent=-sum(p*math.log(p) for p in probs)
    return ent/math.log(len(probs)) if len(probs)>1 else 0.0
def _start_prefix(text:str)->str:
    ss=_sentences(text)
    if not ss:return ""
    x=_compact(re.sub(r"^[（(\d一二三四五六七八九十、.．\s]+","",ss[0]));return x[:4]
def _shingles(text:str,n:int=5)->set:
    c=_compact(text)
    if len(c)<n:return {c} if c else set()
    return {c[i:i+n] for i in range(len(c)-n+1)}
def _jaccard(a:set,b:set)->float:
    return len(a&b)/len(a|b) if a and b else 0.0
def _level(score:float,medium:int,high:int)->str:return "高" if score>=high else ("中" if score>=medium else "低")
def _is_skipped_section(chapter:str)->bool:
    x=re.sub(r"\s+","",chapter);return any(re.search(p,x) for p in SKIP_SECTION_PATTERNS)

def _base_features(text:str, profile:str="general")->Dict:
    cfg=PROFILE_CONFIG.get(profile,PROFILE_CONFIG["general"]);text=_clean_text(text);chars=_visible_chars(text)
    ss=_sentences(text);lengths=[_visible_chars(s) for s in ss];scv=_cv(lengths)
    td=_count_hits(text,TRANSITIONS)/max(1,chars)*100;gd=_count_hits(text,GENERIC_POLICY)/max(1,chars)*100;ad=_count_hits(text,ABSTRACT_NOUNS)/max(1,chars)*100
    cites=_citation_count(text);digits=_digit_density(text);rep=_ngram_repetition(text);patterns=_pattern_hits(text)
    score=8.0;reasons=[]
    if td>=1.5:
        add=min(18,7+td*4)*cfg["transition"];score+=add;reasons.append((add,"模板化连接词密度较高"))
    elif td>=0.7:
        add=7*cfg["transition"];score+=add;reasons.append((add,"连接词使用偏规律"))
    if gd>=3:
        add=min(18,6+gd*2)*cfg["generic"];score+=add;reasons.append((add,"泛化政策动词较密集"))
    elif gd>=1.6:
        add=7*cfg["generic"];score+=add;reasons.append((add,"泛化政策动词偏多"))
    if ad>=4:
        add=7*cfg["abstract"];score+=add;reasons.append((add,"抽象概念密度高、具体信息偏少"))
    if len(lengths)>=3 and scv<0.28:
        add=min(15,(0.28-scv)*45+5);score+=add;reasons.append((add,"句长分布过于均匀"))
    elif len(lengths)>=3 and scv<0.42:score+=5;reasons.append((5,"句式节奏较规则"))
    if patterns:
        add=min(15,patterns*5);score+=add;reasons.append((add,f"命中 {patterns} 类模板化句式"))
    if rep>=0.12:
        add=min(13,rep*35);score+=add;reasons.append((add,"段内短语重复度偏高"))
    if chars>=180 and cites==0 and digits<0.006:score+=9;reasons.append((9,"长段落缺少引文/数字等可核查信息"))
    elif chars>=120 and cites==0 and digits<0.003:score+=5;reasons.append((5,"具体事实线索较少"))
    lex=_lexical_diversity(text)
    if chars>=160 and lex<0.58:score+=4;reasons.append((4,"词汇/短语多样性偏低"))
    if chars<45:score*=0.55
    elif chars<80:score*=0.8
    discount=min(18,(cites*5+(6 if digits>=0.02 else 0))*cfg["discount"]);score-=discount
    return {"score":score,"reasons":reasons,"chars":chars,"sentence_cv":scv,"sentence_mean":_mean(lengths),"transition_density":td,"generic_density":gd,"citation_count":cites,"digit_density":digits,"repetition_score":rep,"lexical_diversity":lex,"function_density":_function_density(text),"punctuation_entropy":_punctuation_entropy(text),"start_prefix":_start_prefix(text),"shingles":_shingles(text)}

def analyze_paragraph(text:str,index:int,chapter:str,medium_threshold:int=40,high_threshold:int=65,profile:str="general")->ParagraphResult:
    f=_base_features(text,profile);score=max(0.0,min(100.0,round(f["score"],1)))
    pos=[r for w,r in sorted(f["reasons"],key=lambda x:abs(x[0]),reverse=True) if w>0][:4] or ["未发现明显模板化特征"]
    return ParagraphResult(index,chapter or "未识别章节",_clean_text(text),f["chars"],score,_level(score,medium_threshold,high_threshold),"；".join(pos),round(f["transition_density"],2),round(f["generic_density"],2),f["citation_count"],round(f["digit_density"]*100,2),round(f["sentence_cv"],3),round(f["repetition_score"],3),round(f["lexical_diversity"],3),sentence_mean=round(f["sentence_mean"],1),function_density=round(f["function_density"],2),punctuation_entropy=round(f["punctuation_entropy"],3))

def extract_docx(data:bytes)->List[Tuple[str,str]]:
    from docx import Document
    document=Document(io.BytesIO(data));rows=[];current="正文"
    for paragraph in document.paragraphs:
        text=_clean_text(paragraph.text)
        if not text:continue
        style=(paragraph.style.name or "") if paragraph.style else ""
        is_heading=style.lower().startswith("heading") or style.startswith("标题")
        if not is_heading:is_heading=bool(re.match(r"^(第[一二三四五六七八九十百0-9]+[章节篇]|\d+(?:\.\d+){0,3}\s+)",text)) and _visible_chars(text)<=45
        if is_heading:current=text;continue
        if not _is_skipped_section(current):rows.append((current,text))
    return rows

def extract_pdf(data:bytes)->List[Tuple[str,str]]:
    from pypdf import PdfReader
    reader=PdfReader(io.BytesIO(data));rows=[];current="PDF正文"
    for page_no,page in enumerate(reader.pages,start=1):
        text=(page.extract_text() or "").replace("\r","\n")
        blocks=[b.strip() for b in re.split(r"\n{2,}",text) if b.strip()]
        if len(blocks)<=1:
            lines=[x.strip() for x in text.splitlines() if x.strip()];blocks=[];buf=""
            for line in lines:
                heading=bool(re.match(r"^(第[一二三四五六七八九十百0-9]+[章节篇]|\d+(?:\.\d+){0,3}\s+)",line)) and len(line)<=45
                if heading:
                    if buf:blocks.append(buf);buf=""
                    blocks.append(line)
                else:
                    buf+=line
                    if line.endswith(("。","！","？",";","；")) and len(buf)>=100:blocks.append(buf);buf=""
            if buf:blocks.append(buf)
        for block in blocks:
            block=_clean_text(block)
            heading=bool(re.match(r"^(第[一二三四五六七八九十百0-9]+[章节篇]|\d+(?:\.\d+){0,3}\s+)",block)) and _visible_chars(block)<=45
            if heading:current=block;continue
            if block and not _is_skipped_section(current):rows.append((f"{current}（第{page_no}页）",block))
    return rows

def analyze_document(rows:List[Tuple[str,str]],medium_threshold:int=40,high_threshold:int=65,profile:str="general")->Tuple[List[ParagraphResult],Dict]:
    results=[];features=[]
    for index,(chapter,text) in enumerate(rows,start=1):
        if _visible_chars(text)<10:continue
        results.append(analyze_paragraph(text,index,chapter,medium_threshold,high_threshold,profile));features.append(_base_features(text,profile))
    total_chars=sum(r.chars for r in results)
    if not total_chars:return results,{"total_chars":0,"weighted_score":0,"estimated_ratio":0,"high_ratio":0,"medium_high_ratio":0,"chapters":[],"document_signals":{}}

    # 全文级：跨段近似重复
    for i,r in enumerate(results):
        best=0.0;best_idx=0
        for j in range(max(0,i-40),i):
            sim=_jaccard(features[i]["shingles"],features[j]["shingles"])
            if sim>best:best=sim;best_idx=results[j].index
        r.cross_similarity=round(best,3);r.cross_match_index=best_idx
        if best>=0.48:
            add=min(16,4+(best-0.48)*35);r.score=min(100,round(r.score+add,1));r.reasons += f"；与段落 #{best_idx} 存在较高跨段相似度"

    # 全文级：同章节相邻文风突变
    for i in range(1,len(results)):
        a,b=results[i-1],results[i]
        if a.chapter!=b.chapter:continue
        fa,fb=features[i-1],features[i]
        d=abs(fa["sentence_mean"]-fb["sentence_mean"])/max(18,(fa["sentence_mean"]+fb["sentence_mean"])/2)
        d+=abs(fa["transition_density"]-fb["transition_density"])/4
        d+=abs(fa["generic_density"]-fb["generic_density"])/6
        d+=abs(fa["lexical_diversity"]-fb["lexical_diversity"])*1.4
        d+=abs(fa["function_density"]-fb["function_density"])/8
        b.style_shift=round(min(1.5,d/3),3)
        if b.style_shift>=0.52 and b.chars>=80:
            add=min(10,3+b.style_shift*8);b.context_adjustment+=round(add,1);b.score=min(100,round(b.score+add,1));b.reasons += "；与前一段存在明显文风突变"

    # 全文级：重复句首和长度过稳
    prefixes=[features[i]["start_prefix"] for i in range(len(features)) if features[i]["start_prefix"]]
    pc=Counter(prefixes)
    repeated_prefixes={p for p,n in pc.items() if n>=3}
    para_lengths=[r.chars for r in results if r.chars>=50]
    length_cv=_cv(para_lengths)
    sentence_means=[f["sentence_mean"] for f in features if f["sentence_mean"]>0]
    sentence_mean_cv=_cv(sentence_means)
    for i,r in enumerate(results):
        p=features[i]["start_prefix"]
        if p and p in repeated_prefixes and r.chars>=70:
            r.score=min(100,round(r.score+4,1));r.context_adjustment+=4;r.reasons += f"；全文多次出现相同句首“{p}”"
        r.level=_level(r.score,medium_threshold,high_threshold)

    weighted_score=sum(r.score*r.chars for r in results)/total_chars
    estimated_ratio=sum(max(0,(r.score-30)/70)*r.chars for r in results)/total_chars*100
    high_chars=sum(r.chars for r in results if r.level=="高");mh_chars=sum(r.chars for r in results if r.level in ("中","高"))
    chapter_map=defaultdict(lambda:{"chars":0,"weighted":0.0,"high_chars":0,"mh_chars":0,"paragraphs":0,"lex":[],"sent":[]})
    for r in results:
        x=chapter_map[r.chapter];x["chars"]+=r.chars;x["weighted"]+=r.score*r.chars;x["paragraphs"]+=1;x["lex"].append(r.lexical_diversity);x["sent"].append(r.sentence_mean)
        if r.level=="高":x["high_chars"]+=r.chars
        if r.level in ("中","高"):x["mh_chars"]+=r.chars
    chapters=[]
    for chapter,x in chapter_map.items():
        c=x["chars"];chapters.append({"chapter":chapter,"chars":c,"avg_score":round(x["weighted"]/c,1),"high_ratio":round(x["high_chars"]/c*100,1),"medium_high_ratio":round(x["mh_chars"]/c*100,1),"paragraphs":x["paragraphs"],"lexical_diversity":round(_mean(x["lex"]),3),"sentence_mean":round(_mean(x["sent"]),1)})
    chapters.sort(key=lambda x:x["avg_score"],reverse=True)
    signals={"profile":profile,"profile_name":PROFILE_CONFIG.get(profile,PROFILE_CONFIG["general"])["name"],"paragraph_length_cv":round(length_cv,3),"sentence_mean_cv":round(sentence_mean_cv,3),"cross_duplicate_count":sum(1 for r in results if r.cross_similarity>=0.48),"style_shift_count":sum(1 for r in results if r.style_shift>=0.52),"repeated_sentence_starts":sorted(repeated_prefixes),"avg_lexical_diversity":round(_mean([r.lexical_diversity for r in results]),3),"avg_function_density":round(_mean([r.function_density for r in results]),2),"regularity_warning":bool(len(para_lengths)>=8 and length_cv<0.30),"sentence_regularity_warning":bool(len(sentence_means)>=8 and sentence_mean_cv<0.25)}
    summary={"total_chars":total_chars,"weighted_score":round(weighted_score,1),"estimated_ratio":round(estimated_ratio,1),"high_ratio":round(high_chars/total_chars*100,1),"medium_high_ratio":round(mh_chars/total_chars*100,1),"chapters":chapters,"document_signals":signals}
    return results,summary

def results_as_dicts(results:List[ParagraphResult])->List[Dict]:return [asdict(r) for r in results]
