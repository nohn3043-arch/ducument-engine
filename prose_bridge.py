"""B1 抽取层：把古典白话散文转成带时空坐标的因果节点，再交给 Creator 引擎审。

为什么需要这一层（实测依据）：
    Creator 引擎的 `parse_outline_to_nodes` 依赖 `->` 箭头分句。把原文直接喂
    `audit_text()`，整回会被压成一个节点（前提=全段、结论=「（待续）」），且
    `time`/`place` 恒为空 —— 于是 `audit_spacetime_consistency` 的
    `checked_nodes` 恒为 0，时空校验空跑，`all_passed` 恒为 True（假阴性）。

本层职责（只做抽取，不做判定）：
    1. 繁简归一        —— 窄表 1:1 映射，下标不变；匹配用简体，展示用原文
    2. 分句            —— 古典标点切分，引号未闭合不切
    3. 人物抽取        —— 说话/动作/处置位候选 + 频次过滤 + 尾缀净化
    4. 时间标记        —— 次日/是夜/建安五年/月令/季节
    5. 地点标记        —— 方位上下文双通道确认，动宾短语与官职代称分别剔除
    6. 死亡事件索引    —— 正文显式死亡陈述 + 回目题名双通道
    7. 年龄陈述索引    —— 「年方X歲」等显式年龄
    所有产物一律带原文位置（回次 + 句序 + 原文片段），便于回原文核验。

设计取舍（记录在案，便于复核）：
    - 人物名为**简体规范形**（張飛→张飞），这样同名的繁简写法自动归一；
      报告展示亦为简体，原文片段保留繁体。
    - 时空冲突以「回内时间键」为作用域（`ch007:次日`），避免跨回同名时间词互撞。
      代价：同一回跨多日的「次日」会被视为同一时点，属已知误报源，输出为候选。
    - 死后出场只认「活跃语境」，排除追封/祭/梦/显圣等回溯与灵异语境。

用法：
    python prose_bridge.py extract --book 三国演义
    python prose_bridge.py audit                 # 四部全量
    python prose_bridge.py audit --book 红楼梦 --limit 5
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(ROOT, "corpus")
OUTDIR = os.path.join(ROOT, "corpus_audit")
ENGINE_FILE = os.path.join(ROOT, "Story Engine for Creator.py")

BOOKS = ["三国演义", "水浒传", "西游记", "红楼梦"]
CH_RE = re.compile(r"^(\d{3})\s+(.+?)\.txt$")


# =============================================================================
# 0. 载入引擎
# =============================================================================
def load_engine():
    spec = importlib.util.spec_from_file_location("creator_engine", ENGINE_FILE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# =============================================================================
# 1. 繁简归一（窄表，1:1，下标不变）
# =============================================================================
# 只收本层**模式词表**用到的字：地名后缀 / 死亡 / 年龄 / 时间 / 说话与动作动词 /
# 过滤用虚词 / 少数高频人名用字。
#
# 为什么要归一：模式是用简体写的，而语料是繁体。不归一会导致
#   `歲` 匹配不到 `岁` —— 实测年龄索引因此恒为 0；
#   `關/縣/樓/觀/營` 等地名后缀全部失配 —— 实测地点从 209 掉到 8。
#
# 表结构为**二元组列表**（每条自身就是一对），从根本上排除"奇数字符串 zip 错位"。
# 逐字 1:1 映射，因此归一化前后**下标完全一致**，可用同一下标回原文切片展示。
T2S_PAIRS = (
    # —— 地名后缀 ——
    ("關", "关"), ("縣", "县"), ("嶺", "岭"), ("橋", "桥"), ("臺", "台"),
    ("樓", "楼"), ("閣", "阁"), ("觀", "观"), ("廟", "庙"), ("宮", "宫"),
    ("營", "营"), ("莊", "庄"), ("驛", "驿"), ("園", "园"), ("館", "馆"),
    ("齋", "斋"), ("軒", "轩"), ("鎮", "镇"), ("島", "岛"), ("陽", "阳"),
    ("陰", "阴"), ("濱", "滨"), ("灣", "湾"), ("灘", "滩"),
    # —— 死亡 ——
    ("斬", "斩"), ("殺", "杀"), ("誅", "诛"), ("殞", "殒"), ("斃", "毙"),
    ("殮", "殓"), ("殯", "殡"), ("喪", "丧"),
    # —— 年龄 / 时间 ——
    ("歲", "岁"), ("臘", "腊"), ("閏", "闰"), ("時", "时"), ("晝", "昼"),
    ("夜", "夜"), ("頃", "顷"), ("須", "须"),
    # —— 说话动词 ——
    ("說", "说"), ("問", "问"), ("謂", "谓"), ("諫", "谏"), ("勸", "劝"),
    ("罵", "骂"), ("嘆", "叹"), ("喚", "唤"),
    # —— 动作动词 ——
    ("見", "见"), ("聞", "闻"), ("聽", "听"), ("視", "视"), ("戰", "战"),
    ("陣", "阵"), ("敗", "败"), ("勝", "胜"), ("討", "讨"), ("誘", "诱"),
    ("詐", "诈"), ("獵", "猎"), ("獲", "获"), ("釋", "释"), ("應", "应"),
    ("撥", "拨"), ("隨", "随"), ("卻", "却"),
    # —— 过滤用虚词 / 群称 ——
    ("與", "与"), ("於", "于"), ("為", "为"), ("過", "过"), ("這", "这"),
    ("個", "个"), ("們", "们"), ("還", "还"), ("來", "来"), ("內", "内"),
    ("萬", "万"), ("兩", "两"), ("軍", "军"), ("將", "将"), ("眾", "众"),
    ("後", "后"), ("書", "书"), ("詩", "诗"), ("贊", "赞"), ("評", "评"),
    ("論", "论"), ("諸", "诸"), ("進", "进"), ("點", "点"), ("親", "亲"),
    ("敵", "敌"), ("計", "计"), ("議", "议"), ("糧", "粮"), ("鎧", "铠"),
    # —— 高频人名 / 姓氏 ——
    ("張", "张"), ("趙", "赵"), ("孫", "孙"), ("馬", "马"), ("劉", "刘"),
    ("長", "长"), ("飛", "飞"), ("東", "东"), ("呂", "吕"), ("董", "董"),
    ("鐘", "钟"), ("鍾", "钟"), ("傳", "传"), ("葉", "叶"), ("萬", "万"),
    ("龐", "庞"), ("鄧", "邓"), ("維", "维"), ("統", "统"), ("術", "术"),
    ("權", "权"), ("肅", "肃"), ("華", "华"), ("費", "费"), ("賈", "贾"),
    ("黃", "黄"), ("魯", "鲁"), ("諸", "诸"), ("喬", "乔"), ("韓", "韩"),
    ("雲", "云"), ("詡", "诩"), ("淵", "渊"), ("謖", "谡"), ("詔", "诏"),
    ("諭", "谕"), ("範", "范"), ("蓋", "盖"), ("蔣", "蒋"), ("許", "许"),
    ("謝", "谢"), ("識", "识"), ("護", "护"), ("蘇", "苏"), ("盧", "卢"),
    ("讓", "让"), ("陳", "陈"), ("陸", "陆"), ("衛", "卫"), ("韋", "韦"),
    ("閻", "阎"), ("顏", "颜"), ("顧", "顾"), ("顯", "显"), ("諶", "谌"),
    ("譚", "谭"), ("鄒", "邹"), ("龔", "龚"), ("嚴", "严"), ("賀", "贺"),
    ("孫", "孙"), ("蔡", "蔡"), ("藺", "蔺"), ("麋", "麋"), ("蒯", "蒯"),
    # —— 情绪/状态字（缺了它们，「大驚」「后趕」会混进人名表）——
    ("驚", "惊"), ("懼", "惧"), ("憤", "愤"), ("憂", "忧"), ("慟", "恸"),
    ("慘", "惨"), ("慶", "庆"), ("戲", "戏"), ("體", "体"), ("趕", "赶"),
    ("癒", "愈"), ("戀", "恋"), ("驛", "驿"), ("蹤", "踪"), ("鐵", "铁"),
    ("銀", "银"), ("銅", "铜"), ("錢", "钱"), ("鏡", "镜"), ("鑼", "锣"),
    ("戰", "战"), ("敵", "敌"), ("敗", "败"), ("傷", "伤"), ("劍", "剑"),
    ("箭", "箭"), ("糧", "粮"), ("馬", "马"), ("騎", "骑"), ("驅", "驱"),
    ("荊", "荆"), ("鄴", "邺"), ("隴", "陇"), ("岷", "岷"), ("濮", "濮"),
    # —— 回溯语境过滤词用字（缺则「追赠/谥号/显圣/梦」全部漏过，实测致 16/16 误报）——
    ("後", "后"), ("贈", "赠"), ("諡", "谥"), ("墳", "坟"), ("憶", "忆"),
    ("當", "当"), ("舊", "旧"), ("夢", "梦"), ("靈", "灵"), ("聖", "圣"),
    ("陰", "阴"), ("遺", "遗"), ("託", "托"), ("嘗", "尝"), ("銘", "铭"),
    ("圖", "图"), ("畫", "画"), ("塑", "塑"), ("柩", "柩"), ("訃", "讣"),
    ("臨", "临"), ("屬", "属"), ("害", "害"), ("殘", "残"), ("戮", "戮"),
    ("稱", "称"), ("蹉", "蹉"), ("跎", "跎"), ("誅", "诛"), ("謹", "谨"),
)
T2S = {ord(a): b for a, b in T2S_PAIRS}


def normalize(text: str) -> str:
    """繁体 → 简体规范形（窄表，1:1，长度与下标不变）。"""
    return text.translate(T2S)


def split_with_spans(text: str) -> list:
    """按古典标点分句，返回 [(归一化句, 起, 止)]；引号未闭合时不切。"""
    out, buf, start = [], [], 0
    open_q = 0
    for i, ch in enumerate(text):
        buf.append(ch)
        if ch in "「『“‘":
            open_q += 1
        elif ch in "」』”’":
            open_q = max(0, open_q - 1)
        if ch in "。！？；" and open_q == 0:
            seg = "".join(buf).strip()
            if seg:
                out.append((seg, start, i + 1))
            buf, start = [], i + 1
    tail = "".join(buf).strip()
    if tail:
        out.append((tail, start, len(text)))
    return out


# =============================================================================
# 2. 人物抽取
# =============================================================================
LEAD_NOISE = (
    "只见", "却说", "且说", "话说", "原来", "于是", "然后", "因此", "所以",
    "当下", "当时", "次日", "是日", "忽见", "忽然", "忽地", "又见", "但见",
    "遂即", "随即", "即便", "却才", "方才", "原来那", "只见那", "应声",
    "谓", "拨", "随", "却", "又", "也", "再", "便", "乃", "遂", "即", "方",
    "因", "故", "而", "则", "就", "亦", "都", "还",
)
# 尾缀噪声：说话/情绪/动作动词黏在名字尾部时剥掉
TAIL_NOISE = (
    "笑道", "怒道", "哭道", "答道", "问道", "大笑道", "大怒", "大喜", "大惊",
    "大笑", "大哭", "笑曰", "怒曰", "答曰", "问曰", "叹曰", "谏曰",
    "笑", "怒", "哭", "喜", "惊", "曰", "道", "云", "言", "说", "问", "答",
    "喝", "叫", "唤", "拜", "奏", "起", "来", "去", "走", "出", "入",
    "见", "闻", "听", "坐", "立", "视", "得", "着", "了",
)
# 人名末字禁止集：出现在末位则整条候选作废（防止「坚守不」「应声而」「拨马便」成词）
BAD_LAST_CHARS = set("不没无而则乃遂便之于其者也矣焉哉乎兮与所为都又再更最甚极将把被向从对谓应拨之者得着了过自然等的个們们")
# 人名内含禁止集：候选名**任何位置**出现这些字即作废
#   —— 时间字：星夜 / 连夜 / 次日 这类表时间词不是人
#   —— 动词与情绪字：操大 / 后赶 / 大惊 这类未剥净的残片不是人
BAD_ANY_CHARS = set("夜昼日月年时刻早晚晨昏春夏秋冬" + "大怒喜惊哭叫喊喝走跑打骂问答曰道参见闻听赶追斗杀")
SPEAK_VERB = sorted(
    ("笑道", "怒道", "哭道", "答道", "问道", "又曰", "亦曰", "笑曰", "怒曰",
     "答曰", "问曰", "叹曰", "奏曰", "谏曰", "言曰", "曰", "道", "云", "言",
     "说", "问", "答", "喝", "叫", "喊", "唤", "吩咐", "禀", "奏", "告",
     "劝", "谏", "骂"),
    key=len, reverse=True,
)
ACT_VERB = sorted(
    ("大怒", "大喜", "大惊", "大笑", "大哭", "起身", "引兵", "领兵", "带兵",
     "点兵", "拔", "挺", "提", "拜", "奏", "走", "奔", "来", "去", "出", "入",
     "见", "闻", "听", "观", "坐", "立"),
    key=len, reverse=True,
)
# 群称 / 代词 / 职官（非人名）
GROUP_WORDS = set(
    """众人 众将 众官 众军 众皆 军士 士卒 左右 二人 三人 两人 一人 四人 五人
    大家 我等 我们 你们 他们 自己 别人 有人 那人 此人 其人 何人 百姓 朝廷
    天子 陛下 娘娘 太后 殿下 丞相 太尉 太守 都督 刺史 将军 元帅 先锋 军师
    主公 明公 足下 先生 尊兄 贤弟 老兄 大兄 小弟 哥哥 兄弟 父亲 母亲 爹爹
    娘亲 孩儿 儿郎 娘子 夫人 女儿 儿子 丈夫 妻子 看官 列位 诸位 各位
    内中 其中 于是 然后 因此 所以 当下 次日 是日 上回 下回 今日 明日
    某日 一日 众贼 诸将 两军 三军 后军 前军 中军 伏兵 追兵 救兵 援兵
    忽然 忽地 忽而 遂即 随即 即便 却才 方才 原来 于是 然后 因此 所以
    吾自 吾等 我等 吾今 吾观 吾闻 汝等 尔等 彼等 近臣 左右 内侍 太监
    回报 回马 国太 太后 太君 老身 老奴 小厮 丫鬟 丫头 嬷嬷 婆子
    如今 已经 只是 可怜 可憐 若是 如何 什么 为什麼 为什么 奴才 老太太
    女孩儿 女孩子 银子 许多人 小人 在地下 我两个 妖精 长老 众位 二位
    替天行 了一 我这 你这 他那 你我 他等 尔等 有甚 不见 只得 不过""".split()
)
# 繁体形（同一类缺陷的第三次发作：GROUP_WORDS 只写简体，繁体正文命中不到）
GROUP_WORDS.update(
    """已經 已經 為什麼 什麼 銀子 許多人 在地下 我兩個 我這 你這 他那
    可憐 若是 如何 奴才 老太太 女孩子 女孩兒 長者 眾位 二位 不見 只得
    不過 鳥人 潑賊 你這廝 我這廝 那廝 這廝 廝們 們的 兩個 三個 幾個""".split()
)
# 职役/泛称（非人名）：实测「做公的」被判为人物并在 ch20 死、ch21 起活跃 15 回。
# 这是**普通名词误当专名**，与「诸葛亮」这类真专名不同，必须整体剔除。
GROUP_WORDS.update(
    """做公的 做公 差撥 差拨 節級 节级 孔目 押司 都頭 都头 虞候 承局
    小嘍囉 嘍囉 嘍羅 嘍啰 嘍儸 伴當 伴当 莊客 庄客 親隨 亲随 從人 从人""".split()
)
# 叙述套语（文本自身的评赞，非人物）
NARRATOR_RE = re.compile(r"詩|诗|贊|赞|歎|叹|評|评|論|论|書|书|史官|後人|后人|有詩|有诗")


def _clean(tok: str) -> str:
    """剥首衬字与尾缀动词，得到名字规范形。

    尾缀剥离**不设最短长度保护**：`操笑` 应剥成 `操`（单字名，后续会被长度过滤丢弃），
    若保护长度就会把 `操笑` 整条留下当成名字。宁可丢弃，不可污染。
    """
    base = tok
    changed = True
    while changed:
        changed = False
        for lead in LEAD_NOISE:
            if base.startswith(lead) and len(base) > len(lead):
                base = base[len(lead):]
                changed = True
                break
    changed = True
    while changed:
        changed = False
        for tail in TAIL_NOISE:
            if base.endswith(tail) and len(base) > len(tail):
                base = base[: -len(tail)]
                changed = True
                break
    return base


def candidate_names(text: str) -> Counter:
    """收集「说话位 / 动作位 / 处置位」人名候选频次（非贪婪，最短合法名优先）。"""
    cnt: Counter = Counter()
    speak = "|".join(SPEAK_VERB)
    for m in re.finditer(r"([\u4e00-\u9fa5]{2,3}?)(?:" + speak + r")", text):
        cnt[_clean(m.group(1))] += 1
    act = "|".join(ACT_VERB)
    for m in re.finditer(r"([\u4e00-\u9fa5]{2,3}?)(?:" + act + r")", text):
        cnt[_clean(m.group(1))] += 1
    for m in re.finditer(r"(?:斩了|杀了|擒了|拿了|放了|捉了|见了)([\u4e00-\u9fa5]{2,3})", text):
        cnt[_clean(m.group(1))] += 1
    return cnt


PLACE_BAD_WORDS = set(
    """回头 口头 开头 手头 心头 眉头 念头 外头 里头 上头 下头 店头
    一口 入口 出口 门口 路口 关口 渡口 洞口 巷口 心口 开口
    山上 山下 山中 水中 手中 心中 空中 面上 口中 台下
    大门 后门 家门 房门 城门 关门 衙门 一门 柴门
    上台 下台 台上 台下 台前 台后 一场 当场 现场 战场 道场 场地
    大殿 宫殿 殿上 殿下 金殿 庄园 田庄 村庄 庄上 庄子
    学堂 祠堂 中堂 堂上 堂前 书房 库房 厨房 房上 房内 房中
    荷花 落花 开花 花朵 江水 河水 湖水 海水 山水 江湖
    山门 山前 山后 山头 山峰 山岭 马鞍 马头 车轮
    后院 前院 跨院 院落 戏院""".split()
)
# 官职/称谓后缀：命中说明这是**人物**被地名通道吞掉，不是地名。
# 实测：「蔡九知府」「慕容知府」因末字「府」进地名表，伪造出
#       「宋江于 ch041 同时出现在[蔡九知府]与[江州]」这类假时空冲突。
OFFICE_SUFFIX = (
    "知府", "知州", "知县", "太守", "太尉", "相公", "将军", "將軍", "提辖", "提轄",
    "都头", "都頭", "孔目", "押司", "制使", "教头", "教頭", "统制", "統制", "先锋",
    "先鋒", "侍郎", "观察", "觀察", "节级", "節級", "虞候", "承局", "侍诏", "侍詔",
    "元帅", "元帥", "都督", "刺史", "丞相", "夫人", "娘子", "哥哥", "兄弟", "太公",
)
# 地名 token 内含功能字 -> 残片（见宋江 / 与宋江 / 军马在村 / 人来到庄 / 江正在营）
# 汉语地名几乎不含这些字；宁可漏收，不可收错。
BAD_INTERNAL = set("见見与與在到至来來去这這那正也是了的着過过和同把将被將其所曰道我你咱俺")

SURNAMES = set("刘关张赵孙马诸曹袁术权维邓统庞肃周吴鲁陆吕黄董卓韩魏蜀")
PLACE_SUFFIX = "城关州府郡县镇邑山岭峰谷洞河江溪湖海浦渡口桥亭台楼阁寺院观庙庵宫殿营寨村庄店驿街巷园苑院堂馆斋轩池塘井陵墓"
STRONG_TOPONYM_SUFFIX = "州府郡县镇关城"
# 通道一：介词/趋向动词后紧随的地名 —— 保证 token 起点干净，不会被前置动词吞掉
LOC_PREP_RE = re.compile(
    r"(?:于|在|到|至|往|向|自|由|入|出|抵|驻|屯|扎|奔|赴|过|离|回|下|上)"
    r"([\u4e00-\u9fa5]{1,3}[" + PLACE_SUFFIX + r"])"
)
# 通道二：地名 + 方位/行政词
LOC_AZI_RE = re.compile(
    r"([\u4e00-\u9fa5]{1,3}[" + PLACE_SUFFIX + r"])(?:里|中|上|下|内|外|界|地|郡|口)"
)
# 通道三：强地名后缀 + 高频（荆州/益州/长安 这类出现上百次）
STRONG_RE = re.compile(r"([\u4e00-\u9fa5]{1,3}[" + STRONG_TOPONYM_SUFFIX + r"])")
# 动词前缀：地名通道会把「出城 / 到营 / 攻城 / 渡江」这类动宾短语吞成地名
# （实测：STRONG 通道因「城」高频准入，把「出城」当地名用，进而制造假时空冲突）
VERB_PREFIX = set("出入攻守取围下上进退回到至过离奔赴发引领带屯扎驻抵犯困救战胜败夺弃走逃追赶迎接送还归援袭击伐征讨破陷降投搆构渡临跨据侵掠于於")


def place_candidates(text: str) -> tuple:
    """地点候选三通道抽取，返回 (上下文确认计数, 强后缀计数, 官职代称计数)。"""
    ctx: Counter = Counter()
    strong: Counter = Counter()
    aliases: Counter = Counter()

    def _classify(tok: str, bucket: Counter) -> None:
        if len(tok) < 2 or tok in PLACE_BAD_WORDS:
            return
        # 首字为虚词/副词/动词 —— 后缀通道吞进了衬字或动宾短语
        if tok[0] in "乃遂便即却而则因故又亦都还":
            return
        if tok[0] in VERB_PREFIX:
            return
        # 官职/称谓后缀 -> 是人物，不是地点
        if tok.endswith(OFFICE_SUFFIX):
            return
        # 内含功能字 -> 残片
        if any(ch in BAD_INTERNAL for ch in tok):
            return
        # 官职+地名代称（刘豫州 / 曹丞相式）：首字为姓、长 3、后缀州郡府
        if len(tok) == 3 and tok[0] in SURNAMES and tok[-1] in "州郡府":
            aliases[tok] += 1
            return
        bucket[tok] += 1

    for rx, bucket in ((LOC_PREP_RE, ctx), (LOC_AZI_RE, ctx), (STRONG_RE, strong)):
        for m in rx.finditer(text):
            _classify(m.group(1), bucket)
    return ctx, strong, aliases


def build_name_set(all_counts: Counter, min_freq: int = 6) -> set:
    """频次过滤后定名；剔除非人名、套语残片、虚词残片、地名。"""
    names = set()
    for name, c in all_counts.items():
        if c < min_freq:
            continue
        if not (2 <= len(name) <= 3):
            continue
        if name in GROUP_WORDS:
            continue
        if NARRATOR_RE.search(name):
            continue
        # 首字：数字、指示代词、否定词、量词 —— 一律非人名
        if name[0] in "一二三四五六七八九十百千万两几这那哪什么不没无有很就都也还又再":
            continue
        # 末字：虚词 / 助词 / 副词 —— 说明尾缀未剥净
        if name[-1] in BAD_LAST_CHARS:
            continue
        # 任意位置含时间字或动词/情绪字 —— 残片，非人名
        if any(ch in BAD_ANY_CHARS for ch in name):
            continue
        # 注：**曾有一条「末字是地名后缀则丢弃」的规则，已移除**。
        # 该规则误杀「宋江」（江）、「贾雨村」（村）——两位主要人物，
        # 导致他们转而被判成地点，伪造出「宋江与鄄城同时出现」这类假时空冲突。
        # 反向校验（places -= names，人名优先）足以处理真正的同形冲突。
        names.add(name)
    # 子串净化：短名是长名子串且频次不低于其半，保留短名（规范形）
    for n in sorted(names, key=len, reverse=True):
        for m in sorted(names, key=len):
            if m != n and m in n and len(m) >= 2 and all_counts[m] >= all_counts[n] * 0.5:
                names.discard(n)
                break
    return names


# =============================================================================
# 3. 时间 / 死亡 / 年龄
# =============================================================================
TIME_PATTERNS = [
    r"次日(?:天明|早起|一早)?", r"翌日", r"明日", r"昨日", r"前日", r"今日",
    r"是夜", r"当夜", r"此夜", r"那夜", r"今夜", r"明夜", r"连夜", r"一夜",
    r"是日", r"当日", r"此日", r"那日", r"这日", r"一日", r"某日",
    r"少顷", r"须臾", r"顷刻", r"不一时", r"不多时", r"不一日", r"顿饭时",
    r"正月(?:十五)?", r"二月", r"三月", r"四月", r"五月", r"六月", r"七月",
    r"八月(?:十五)?", r"九月", r"十月", r"十一月", r"十二月", r"腊月",
    r"元宵", r"清明", r"端午", r"七夕", r"中秋", r"重阳", r"除夕", r"元旦",
    r"春日", r"夏日", r"秋日", r"冬日", r"春天", r"夏天", r"秋天", r"冬天",
    r"[建延嘉正景泰咸永光大天宝万兴洪武宣德靖康淳熙绍]{1,3}[元二三四五六七八九十]{1,4}年",
    r"[一二三四五六七八九十百千]{1,5}年(?:前|后)?",
    r"[一二三四五六七八九十百千]{1,3}(?:个)?月(?:余|后)?",
    r"[一二三四五六七八九十百千]{1,3}(?:日|天)",
    r"旬日", r"月余", r"半年", r"一年", r"数年",
]
TIME_RES = [re.compile(p) for p in TIME_PATTERNS]

# 时空坐标只认**绝对纪时**（年号纪年 / 年月 / 月日）。
# 根因：初版拿「章号:今日」当坐标键，同一回里所有「今日/次日/一日」共用一个键，
# 于是「同一回内先后到过梁山与江州」被判成「同一时刻出现在两地」——
# 实测 31 条时空冲突 100% 由此产生。相对时间词根本无法锚定时刻，不配作坐标。
ABS_TIME_RE = re.compile(
    r"(?:[建延嘉正景泰咸永光大天宝万兴洪武宣德靖康淳熙绍宣政重至元丰和]{1,3}年"
    r"|[一二三四五六七八九十百千]{1,4}年[一二三四五六七八九十]{1,2}月"
    r"|[一二三四五六七八九十]{1,2}月[一二三四五六七八九十]{1,3}日)"
)

# 死亡上下文否定词：命中则**该条死亡陈述不可信**，不计入死亡索引。
#   ① 梦话/戏言：「李逵說到殺了蔡京…如此也不枉了做夢」(ch93) —— 是梦，不是事实；
#   ② 谎报/假称：「小人回称『柴進已死』」(ch54) —— 是狱卒搪塞上级的假话，
#      柴进此时活着，后面还出场 26 回。若不剔除，就会伪造出整条人物漂移。
DEATH_UNREAL = (
    "夢", "梦", "做夢", "做梦", "夢中", "梦中", "夢見", "梦见", "說夢", "说梦",
    "戲言", "戏言", "取笑", "說笑", "说笑", "玩笑", "哄",
    "謊", "谎", "假稱", "假称", "詐稱", "诈称", "偽稱", "伪称", "冒充",
    "回稱", "回称", "只推", "推道", "推說", "推说", "報稱", "报称", "妄稱", "妄称",
)
# 死亡：正文显式陈述（归一化后按简体匹配）
DEATH_PATTERNS = [
    r"([\u4e00-\u9fa5]{2,3})(?:已死|身死|身故|病故|病亡|而亡|而死|身亡|阵亡|遇害|殒命|丧命|归天|去世|亡故|病逝)",
    r"([\u4e00-\u9fa5]{2,3})(?:自刎|自尽|自缢|投江|撞死|气绝|咽气)",
    # 处置式。修复记录：初版只写「打死」，实测「我打死了殷天錫」(ch53) 匹配失败 ——
    # 「打死」后紧跟的是「了」而非人名，group(1) 取成了「了殷天」。凡「动词+了」
    # 形式必须把「了」写进模式。
    r"(?:斩了|殺了|杀了|斩却|斬卻|砍了|杀死|殺死|打死了|勒死|射死|刺死|打死|害死|踢死|燒死|烧死|淹死|毒死|逼死|斩死|斬死)([\u4e00-\u9fa5]{2,3})",
    r"([\u4e00-\u9fa5]{2,3})(?:被|为)[^\u4e00-\u9fa5]{0,4}?(?:所)?(?:杀|斩|诛|戮)",
    r"([\u4e00-\u9fa5]{2,3})(?:遂亡|乃亡|既亡|已亡|遂死|乃死)",
    r"([\u4e00-\u9fa5]{2,3})(?:崩|薨|殂)",
]
DEATH_RES = [re.compile(p) for p in DEATH_PATTERNS]

# 回目题名死亡通道：高精度，题名是结构化文本
TITLE_DEATH_RE = re.compile(
    r"([\u4e00-\u9fa5]{2,3})(?:遇害|殒命|身亡|归天|病亡|自刎|身死|丧命|被戮|受诛|被诛|殒身)"
)

AGE_PATTERNS = [
    r"(?:年方|年已|年近|年才|年将|时年|亡年|年方有|年逾|年已及)[^\u4e00-\u9fa5]{0,2}([一二三四五六七八九十百廿卅]{1,4})岁",
    r"([一二三四五六七八九十百廿卅]{1,4})岁",
    r"年[^，。]{0,4}?([一二三四五六七八九十百廿卅]{1,4})岁",
]
# 比较级与亲属指示：命中则本句年龄不归属句中人名
AGE_COMPARATIVE = ("长", "大", "小", "少", "多", "幼", "长于", "大于")
AGE_DEPENDENT = ("之女", "之子", "之妻", "之弟", "之妹", "之兄", "之姐", "其女", "其子", "女儿", "儿子")
AGE_RES = [re.compile(p) for p in AGE_PATTERNS]
CN_NUM = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6,
          "七": 7, "八": 8, "九": 9, "十": 10, "廿": 20, "卅": 30}


def cn2int(s: str):
    if not s:
        return None
    if s in CN_NUM:
        return CN_NUM[s]
    if "十" in s:
        head, _, tail = s.partition("十")
        h = CN_NUM.get(head, 1) if head == "" else CN_NUM.get(head)
        t = CN_NUM.get(tail, 0) if tail == "" else CN_NUM.get(tail)
        if h is None or t is None:
            return None
        return h * 10 + t
    return None


# 回溯语境过滤词表 —— **简繁双形并列，比对原文（premise）**。
#
# 修法说明（重要）：初版只写简体，拿去比繁体正文，`死后` 匹配不到 `死後`，
# 实测致 16 条「死后仍活跃」候选 100% 误报。随后改成"先归一化再比对"，
# 又因窄表漏收 `終` 而再次失效（`臨終` 归一成 `临終`）。
# 结论：窄表方案结构性脆弱，故此处直接双形并列，不再依赖归一化。
RETRO_MARK = (
    # 丧葬仪式
    "追封", "追贈", "追赠", "追諡", "追谥", "諡", "谥", "贈", "赠", "祭",
    "廟", "庙", "祠", "墳", "坟", "墓", "柩", "喪", "丧", "殯", "殡", "訃", "讣",
    "靈位", "灵位", "神位", "塑像", "畫像", "画像", "圖畫", "图画", "壁畫", "壁画",
    # 追忆语境
    "追念", "憶", "忆", "昔日", "昔", "當初", "当初", "當日", "当日", "當年", "当年",
    "先是", "初時", "初时", "生前", "臨終", "临终", "遺言", "遗言", "遺囑", "遗嘱",
    "遺命", "遗命", "舊部", "旧部", "舊將", "旧将", "舊日", "旧日", "在日",
    # 灵异与梦
    "夢", "梦", "魂", "陰魂", "阴魂", "顯聖", "显圣", "顯靈", "显灵", "鬼",
    "託夢", "托梦", "地獄", "地狱", "陰司", "阴司",
    # 后设陈述
    "已死", "已亡", "身死", "之死", "死後", "死后", "既亡", "既死", "死於", "死于",
    "先帝有言", "嘗聞", "尝闻", "曾言", "嘗言", "尝言", "有言",
    # 被害与亲属/从属指称
    "所害", "被害", "遇害", "之害", "女婿", "之婿", "第六子", "長子", "长子",
    "次子", "之女", "之子", "之弟", "之兄", "之妻", "之母", "之父", "之孫", "之孙",
    "字子", "之役", "稱帝", "称帝", "稱王", "称王", "改元", "篡",
    "遺表", "遗表", "遺書", "遗书", "遺孤", "遗孤",
    # 追述 / 转述 / 阵亡名册（水浒传实测新增）
    #   ch47「自從火併王倫之後」· ch85「前番因打高唐州」· ch93「又說到殺了蔡京…」
    #   ch119「亡正偏將佐五十九員：…周通…」为阵亡名册，属汇总清单而非人物行动
    "自從", "自从", "之後", "之后", "前番", "後來", "后来", "說起", "说起",
    "說到", "说到", "講起", "讲起", "夢中", "梦中", "說夢", "说梦", "夢見", "梦见",
    "將佐", "将佐", "正將", "正将", "偏將", "偏将", "陣亡", "阵亡",
    "之屍", "之尸", "的屍", "的尸", "遺骸", "遗骸",
)
# 叙述者后设评论：诗赞 / 评语 / 铭碑 —— 一律不算「人物在行动」
POEM_RE = re.compile(
    r"詩曰|诗曰|有詩|有诗|贊曰|赞曰|評曰|评曰|史官|後人|后人|歎曰|叹曰|"
    r"論曰|论曰|銘曰|铭曰|碑|獨憑|独凭"
)


# =============================================================================
# 4. 抽取主流程
# =============================================================================
def list_chapters(book: str) -> list:
    d = os.path.join(CORPUS, book)
    if not os.path.isdir(d):
        return []
    out = []
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".txt"):
            continue
        m = CH_RE.match(fn)
        out.append({
            "book": book,
            "idx": int(m.group(1)) if m else 0,
            "title": normalize(m.group(2)) if m else fn,
            "path": os.path.join(d, fn),
        })
    return out


def read_text(path: str) -> str:
    """读取一章；实测漢川草廬为 UTF-8 带 BOM，故 utf-8-sig 必须排第一。"""
    with open(path, "rb") as fh:
        raw = fh.read()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "big5"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def extract_book(book: str, verbose: bool = True) -> dict:
    chaps = list_chapters(book)
    if not chaps:
        raise SystemExit("未找到语料：%s（先跑 corpus_fetch.py）" % os.path.join(CORPUS, book))

    orig_texts = [read_text(c["path"]) for c in chaps]
    norm_texts = [normalize(t) for t in orig_texts]

    name_cnt: Counter = Counter()
    ctx_cnt: Counter = Counter()
    strong_cnt: Counter = Counter()
    alias_cnt: Counter = Counter()
    for nt in norm_texts:
        name_cnt.update(candidate_names(nt))
        c, s, a = place_candidates(nt)
        ctx_cnt.update(c)
        strong_cnt.update(s)
        alias_cnt.update(a)
    names = build_name_set(name_cnt)
    # 地名准入：上下文通道 ≥2 次，或强后缀通道 ≥8 次（荆州/长安这类高频地名）
    places = {
        p for p in (set(ctx_cnt) | set(strong_cnt))
        if len(p) >= 2 and p not in PLACE_BAD_WORDS
        and (ctx_cnt[p] >= 2 or strong_cnt[p] >= 8)
    }
    places -= names
    # 地名去污（子串级）：token 内含已定人物名 -> 残片（「見宋江」「與宋江」），非地名。
    # `places -= names` 只做精确相等，抓不到这类，故补一层子串检查。
    if names:
        places = {p for p in places if not any(nm in p for nm in names)}

    name_re = re.compile("|".join(sorted(map(re.escape, names), key=len, reverse=True))) if names else None
    place_re = re.compile("|".join(sorted(map(re.escape, places), key=len, reverse=True))) if places else None

    chapters = []
    death_index: dict = defaultdict(list)
    death_stmt: dict = defaultdict(dict)
    age_index: dict = defaultdict(list)
    name_visit: dict = defaultdict(list)
    place_visit: dict = defaultdict(list)
    title_deaths: dict = defaultdict(list)

    for ch, otext, ntext in zip(chaps, orig_texts, norm_texts):
        idx = ch["idx"]
        # 回目题名死亡通道
        for m in TITLE_DEATH_RE.finditer(normalize(ch["title"])):
            who = m.group(1)
            if who in names:
                title_deaths[who].append(idx)
        nodes = []
        for si, (seg, s, e) in enumerate(split_with_spans(ntext)):
            display = otext[s:e].strip()
            time_hits = []
            for r in TIME_RES:
                m = r.search(seg)
                if m and m.group(0) not in time_hits:
                    time_hits.append(m.group(0))
            abs_m = ABS_TIME_RE.search(seg)
            abs_time = abs_m.group(0) if abs_m else ""
            place_hits = []
            if place_re:
                for m in place_re.finditer(seg):
                    if m.group(0) not in place_hits:
                        place_hits.append(m.group(0))
            char_hits = []
            if name_re:
                for m in name_re.finditer(seg):
                    if m.group(0) not in char_hits:
                        char_hits.append(m.group(0))
            nodes.append({
                "chapter": idx, "sent": si,
                "premise": display[:200],
                # premise_norm：归一架，仅供**标记比对**使用（回溯语境/诗词判定）。
                # 关键：初版拿简体 RETRO_MARK 去比繁体正文，`死后` 匹配不到 `死後`，
                # 实测使 16 条「死后仍活跃」候选全部误报。展示仍用 premise 原文。
                "premise_norm": seg[:200],
                "character": char_hits[0] if char_hits else "",
                "characters": char_hits,
                # time 仅在有绝对纪时时才落值，否则留空 —— 空坐标不参与时空比对
                # （引擎 audit_spacetime_consistency 明令「缺坐标者跳过」）。
                "time": ("ch%03d:" % idx) + abs_time if abs_time else "",
                "time_hits": time_hits,
                "place": place_hits[0] if place_hits else "",
                "places": place_hits,
            })
            for c in char_hits:
                if idx not in name_visit[c]:
                    name_visit[c].append(idx)
            for p in place_hits:
                if idx not in place_visit[p]:
                    place_visit[p].append(idx)
            for r in DEATH_RES:
                for m in r.finditer(seg):
                    who = m.group(1)
                    if who not in names:
                        continue
                    # 反事实守卫：含「若/倘若/假如」的假设句不是死亡陈述。
                    # 实测：「吾若殺了曹洪，今日必死於馬超之手也」被误判为曹洪之死，
                    # 进而伪造出「曹洪死后仍在 ch59 交战」的假漏洞。
                    if re.search(r"若|倘若|倘或|假如|如若|万一|萬一", seg[max(0, m.start() - 12): m.start()]):
                        continue
                    # 计划/判决/威胁守卫：杀意在文书或口头上，不是既成事实。
                    # 实测（水浒传）：ch40「教來日押赴市曹…斬了宋江、戴宗」是蔡九知府的
                    # 判決（實為黃孔目拖延未行刑），被当成宋江已死，伪造出 ch41 起 75 回
                    # 「死后仍活跃」；ch54「要取柴進出來施刑」是威胁，也被当成柴进之死。
                    ctx = seg[max(0, m.start() - 20): m.end() + 8]
                    if re.search(
                        r"分付|押赴|來日|来日|明日|次日|即日|請旨|请旨|擬|拟|議|议"
                        r"|奏|問成|问成|判|施刑|示眾|示众|行刑|待|欲|要取",
                        ctx,
                    ):
                        continue
                    # 不可信死亡陈述守卫：梦话 / 谎报 / 假称。
                    # 必须比对**整段**而非就近窗口 —— 实测 ch93「又說到殺了蔡京…」
                    # 与句末「如此也不枉了做夢」相隔 40 余字，±26 窗口漏网。
                    if any(k in seg for k in DEATH_UNREAL):
                        continue
                    if idx not in death_index[who]:
                        death_index[who].append(idx)
                    # 存下死亡陈述原文，供人工复核「这条死亡判定本身对不对」
                    death_stmt.setdefault(who, {}).setdefault(idx, display[:110])
            # 年龄归属（宁缺毋滥）：只在年龄词**前方 14 字窗口**内找人名，
            # 取窗口内最后一个（最靠近者）。窗口内无人名 -> 丢弃，不猜。
            # 初版用「全文最近人名」，实测把陶谦的 63 岁记到糜竺头上（糜竺只是
            # 被请来议事的人），属错误归属，故改为窗口 + 前置优先。
            if name_re:
                hit = None
                for r in AGE_RES:
                    for m in r.finditer(seg):
                        val = cn2int(m.group(1))
                        if not (val and 1 <= val <= 120):
                            continue
                        nlen = len(m.group(1))          # 数字跨度，越长越可信
                        if hit is None or nlen > hit[0]:
                            hit = (nlen, m.start(), val)
                if hit:
                    _, apos, val = hit
                    win_lo = max(0, apos - 14)
                    pre = seg[win_lo:apos]
                    # 比较级（「臣长关兴一岁」）与亲属从属（「张飞之女…年十七岁」）
                    # 均不把年龄算到窗口里那个人头上 —— 宁缺毋滥。
                    if not any(k in pre for k in AGE_COMPARATIVE) and \
                       not any(k in pre for k in AGE_DEPENDENT):
                        owners = [m.group(0) for m in name_re.finditer(pre)]
                        if owners:
                            owner = owners[-1]
                            rec = (idx, val, display[:70])
                            if rec not in age_index[owner]:
                                age_index[owner].append(rec)
        chapters.append({"idx": idx, "title": ch["title"], "nodes": nodes,
                         "n_sent": len(nodes)})

    for who, chs in title_deaths.items():
        for c in chs:
            if c not in death_index[who]:
                death_index[who].append(c)

    return {
        "book": book, "chapters": chapters,
        "names": sorted(names, key=lambda n: -name_cnt[n]),
        "name_counts": dict(name_cnt.most_common(300)),
        "places": sorted(places, key=lambda p: -max(ctx_cnt[p], strong_cnt[p])),
        "place_counts": {"ctx": dict(ctx_cnt.most_common(150)),
                         "strong": dict(strong_cnt.most_common(150))},
        "aliases": dict(alias_cnt.most_common(60)),
        "death_index": {k: sorted(v) for k, v in death_index.items()},
        "death_statements": {k: v for k, v in death_stmt.items()},
        "title_deaths": {k: sorted(v) for k, v in title_deaths.items()},
        "age_index": dict(age_index),
        "name_visit": {k: sorted(v) for k, v in name_visit.items()},
    }


# =============================================================================
# 5. 交引擎审
# =============================================================================
def audit_book(book: str, limit: int = 0, verbose: bool = True) -> dict:
    eng_mod = load_engine()
    ex = extract_book(book, verbose=verbose)

    engine = eng_mod.UltimateCausalNovelEngine(
        "四大名著审计·%s" % book, eng_mod.GlobalState()
    )
    chapters = ex["chapters"][: limit or None]

    per_chapter = []
    jump_hits: Counter = Counter()
    jump_examples = defaultdict(list)
    pres_hits = defaultdict(list)
    spacetime_conflicts = []
    logical_fail = []

    for ch in chapters:
        text = "\n".join(n["premise"] for n in ch["nodes"])
        rep = engine.audit_text(text=text, include_causal=False)

        for issue in ((rep.get("logical") or {}).get("issues") or []):
            w = issue.split("'")[1] if "'" in issue else issue
            jump_hits[w] += 1
            if len(jump_examples[w]) < 3:
                jump_examples[w].append("第%d回 %s" % (ch["idx"], ch["title"]))
        if rep.get("logical") and not rep["logical"].get("overall_passed"):
            logical_fail.append(ch["idx"])
        for k, v in (rep.get("presentation") or {}).items():
            if isinstance(v, dict) and v.get("hits"):
                for h in v["hits"][:3]:
                    pres_hits[k].append("第%d回: %s" % (ch["idx"], str(h)[:100]))

        cnodes = []
        for n in ch["nodes"]:
            cn = eng_mod.CausalNode(premise=n["premise"], conclusion="（回内续）")
            cn.character = n["character"]
            cn.time = n["time"]
            cn.place = n["place"]
            cnodes.append(cn)
        sp = eng_mod.audit_spacetime_consistency(cnodes)
        for c in sp["conflicts"]:
            spacetime_conflicts.append({"chapter": ch["idx"], "detail": c})

        per_chapter.append({
            "idx": ch["idx"], "title": ch["title"], "n_sent": ch["n_sent"],
            "logical_passed": (rep.get("logical") or {}).get("overall_passed"),
            "spacetime_checked": sp["checked_nodes"],
            "spacetime_conflicts": len(sp["conflicts"]),
            "audit_hash": rep.get("audit_hash"),
        })
        if verbose and ch["idx"] % 20 == 0:
            print("    ...%s 第 %d 回" % (book, ch["idx"]))

    # 死后出场（B1 索引 + 活跃语境判定）
    # 关键修复：比对必须用 premise_norm（归一架），不能用 premise（繁体原文），
    # 否则简体过滤词全部失效 —— 实测曾因此把 16 条「追述/诗赞/谥号」全判为活跃。
    post_mortem = []
    for who, death_chs in ex["death_index"].items():
        d_ch = max(death_chs)
        later = [c for c in ex["name_visit"].get(who, []) if c > d_ch]
        if not later:
            continue
        active, samples = [], []
        for ch in ex["chapters"]:
            if ch["idx"] <= d_ch or ch["idx"] not in later:
                continue
            for n in ch["nodes"]:
                if who not in n["characters"]:
                    continue
                txt = n.get("premise", "")
                if POEM_RE.search(txt):
                    continue                      # 叙述者诗赞/评语，非人物行动
                if any(k in txt for k in RETRO_MARK):
                    continue                      # 追述/丧葬/灵异/谥号/关系指称语境
                # 该句自身就在陈述此人已死（「我打死了殷天錫」）—— 不能当作
                # 「此人仍活跃」的证据，否则等于用死亡陈述自证未死。
                if any(m.group(1) == who
                       for r in DEATH_RES for m in r.finditer(normalize(txt))):
                    continue
                active.append(ch["idx"])
                if len(samples) < 3:
                    samples.append("第%d回: %s" % (ch["idx"], n["premise"][:80]))
                break
        if active:
            post_mortem.append({
                "character": who, "death_chapters": death_chs,
                "death_statement": ex["death_statements"].get(who, {}),
                "last_death_chapter": d_ch, "active_after": active[:15],
                "n_active": len(active), "samples": samples,
            })

    age_conflicts = []
    for who, recs in ex["age_index"].items():
        if len({r[1] for r in recs}) < 2:
            continue
        seq = sorted(set(recs), key=lambda r: r[0])
        for i in range(len(seq) - 1):
            c1, a1, t1 = seq[i]
            c2, a2, t2 = seq[i + 1]
            if c2 > c1 and a2 < a1:
                age_conflicts.append({
                    "character": who, "from": {"chapter": c1, "age": a1, "text": t1},
                    "to": {"chapter": c2, "age": a2, "text": t2},
                })

    return {
        "book": book, "chapters_audited": len(chapters),
        "sentences_total": sum(c["n_sent"] for c in chapters),
        "names": ex["names"][:80], "name_counts": ex["name_counts"],
        "places": ex["places"][:80], "aliases": ex["aliases"],
        "death_index": ex["death_index"], "title_deaths": ex["title_deaths"],
        "death_statements": ex["death_statements"],
        "age_index": {k: v[:12] for k, v in list(ex["age_index"].items())[:60]},
        "findings": {
            "post_mortem_active": post_mortem,
            "age_regression": age_conflicts,
            "spacetime_conflicts": spacetime_conflicts[:300],
            "logical_jump_words": dict(jump_hits.most_common()),
            "logical_jump_examples": dict(jump_examples),
            "logical_failed_chapters": logical_fail[:100],
            "presentation_hits": {k: v[:5] for k, v in pres_hits.items()},
        },
        "per_chapter": per_chapter,
    }


# =============================================================================
# 6. CLI
# =============================================================================
def cmd_extract(book: str):
    ex = extract_book(book)
    print("=== %s 抽取结果 ===" % book)
    print("回数            : %d" % len(ex["chapters"]))
    print("句数            : %d" % sum(c["n_sent"] for c in ex["chapters"]))
    print("识别人物数      : %d" % len(ex["names"]))
    print("  高频人物 top25: %s" % "、".join(ex["names"][:25]))
    print("识别地点数      : %d" % len(ex["places"]))
    print("  高频地点 top20: %s" % "、".join(ex["places"][:20]))
    print("官职代称 top10  : %s" % "、".join("%s(%d)" % (k, v) for k, v in list(ex["aliases"].items())[:10]))
    print("死亡索引        : %d 人" % len(ex["death_index"]))
    for k, v in list(ex["death_index"].items())[:15]:
        print("    %-8s 回 %s" % (k, v[:8]))
    print("年龄索引        : %d 人" % len(ex["age_index"]))
    for k, v in list(ex["age_index"].items())[:10]:
        print("    %-8s %s" % (k, v[:4]))
    print()
    print("--- 样本节点（第 1 回前 4 句）---")
    for n in ex["chapters"][0]["nodes"][:4]:
        print(json.dumps(n, ensure_ascii=False)[:300])


def cmd_audit(books, limit: int):
    os.makedirs(OUTDIR, exist_ok=True)
    all_res = {}
    for b in books:
        print("== 审计 %s ==" % b)
        res = audit_book(b, limit=limit)
        all_res[b] = res
        f = res["findings"]
        print("   回数 %d / 句数 %d" % (res["chapters_audited"], res["sentences_total"]))
        print("   死后仍活跃候选 : %d" % len(f["post_mortem_active"]))
        print("   年龄倒退候选   : %d" % len(f["age_regression"]))
        print("   时空冲突候选   : %d" % len(f["spacetime_conflicts"]))
        print("   逻辑跳跃词     : %s" % (f["logical_jump_words"] or "无"))
    path = os.path.join(OUTDIR, "report.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(all_res, fh, ensure_ascii=False, indent=1)
    print("\n完整报告 -> %s" % path)
    return all_res


def main():
    ap = argparse.ArgumentParser(description="B1 散文→节点抽取层 + Creator 引擎审计驱动")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch", help="下载语料")
    p_ex = sub.add_parser("extract", help="只跑抽取")
    p_ex.add_argument("--book", default="三国演义")
    p_au = sub.add_parser("audit", help="抽取 + 引擎审计 + 出报告")
    p_au.add_argument("--book", default="all")
    p_au.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    if args.cmd == "fetch":
        import subprocess
        return subprocess.call([sys.executable, os.path.join(ROOT, "corpus_fetch.py")])
    if args.cmd == "extract":
        cmd_extract(args.book)
        return 0
    cmd_audit(BOOKS if args.book == "all" else [args.book], args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
