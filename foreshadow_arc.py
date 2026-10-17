# -*- coding: utf-8 -*-
"""红楼梦：跨章伏笔对账 + 判词谶语解析（决定论、零依赖、不臆造）。

产出（corpus_audit/ 下）：
    红楼梦_伏笔谶语对账.md
    红楼梦_伏笔谶语对账.json

三条设计铁律：
  1. 事实节点 = 谶语/物名 token 在全书各回的字面出现（可回原文逐条核验）；
  2. 评估节点 = 「该谶语指向谁」「是否已应验」的解释，一律标注 [评估] 并给出依据来源；
  3. 不引入引擎内部类（避免与 Creator/Business 引擎的同名类冲突），只读语料文本。

用法：
    python foreshadow_arc.py                # 全部三节
    python foreshadow_arc.py --section arc  # 只做跨章伏笔对账
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "corpus", "红楼梦")
OUTDIR = os.path.join(HERE, "corpus_audit")

# ============================================================================
# 一、谶语原文（逐字抄自语料 005 回，含语料异文；异文处加 [语料原文] 标注）
# ============================================================================
# image_tokens：从谶语字面抽出的可检索意象词（决定论：必须是原文子串）
# person / rationale：指向判断与依据（评估节点）
PROPHECIES = [
    # —— 又副册 ——
    {"id": "又副册01", "text": "霽月難逢，彩雲易散。心比天高，身為下賤。風流靈巧招人怨，壽夭多因誹謗生，多情公子空牽念。",
     "person": ["晴雯"], "rationale": "画面「水墨染，滿紙烏雲濁霧」+ 判词「心比天高，身為下賤」，通行红学共识指向晴雯。",
     "image_tokens": ["霽月", "彩雲", "心比天高", "身為下賤", "招人怨", "誹謗", "空牽念"]},
    {"id": "又副册02", "text": "枉自溫柔和順，空云似桂如蘭。堪羡優伶有福，誰知公子無緣。",
     "person": ["襲人"], "rationale": "「溫柔和順」「似桂如蘭」（花袭人之花/桂）与「優伶有福」（蒋玉菡）指向袭人改嫁蒋玉菡。",
     "image_tokens": ["溫柔和順", "似桂如蘭", "優伶", "公子無緣"]},
    # —— 副册 ——
    {"id": "副册01", "text": "根并荷花一莖香，平生遭際實堪傷。自從兩地生孤木，致使香魂返故鄉。",
     "person": ["香菱"], "rationale": "「荷花」（英莲/香菱）、「兩地生孤木」拆字为「桂」（薛蟠之妻夏金桂），指向香菱被夏金桂折磨致死。",
     "image_tokens": ["荷花", "一莖香", "遭際", "兩地", "孤木", "香魂", "故鄉"]},
    # —— 正册（12 人 11 首，黛玉宝钗合一）——
    {"id": "正册01", "text": "可嘆停機德，堪憐詠絮才。玉帶林中掛，金簪雪裏埋。",
     "person": ["薛寶釵", "林黛玉"], "rationale": "画面「兩株枯木，木上懸著一圍玉帶；地下又有一堆雪，雪中一股金簪」；「玉帶林中」嵌「林」，「金簪雪裏」嵌「薛」。",
     "image_tokens": ["停機德", "詠絮才", "玉帶", "林中", "金簪", "雪裏"]},
    {"id": "正册02", "text": "二十年來辨是非，榴花開處照官闈。三春爭及初春景，虎兔相逢大夢歸。",
     "person": ["賈元春"], "rationale": "画面「一張弓，弓上掛著一個香櫞」（弓谐宮、櫞谐元），指向元春入宫与早逝。",
     "image_tokens": ["二十年", "辨是非", "榴花", "官闈", "三春", "初春", "虎兔", "大夢歸"]},
    {"id": "正册03", "text": "才自清明志自高，生於末世運偏消。清明涕泣江邊望，千里東風一夢遙。",
     "person": ["賈探春"], "rationale": "画面「兩個人放風箏，一片大海，一只大船，船中有一女子掩面泣涕」，指向探春远嫁。",
     "image_tokens": ["才自清明", "末世", "運偏消", "涕泣", "江邊", "千里", "東風"]},
    {"id": "正册04", "text": "富貴又何為？襁褓之間父母違。展眼吊斜輝，湘江水逝楚雲飛。",
     "person": ["史湘雲"], "rationale": "「湘江水逝楚雲飛」嵌「湘」「雲」二字；「襁褓之間父母違」合湘云自幼父母双亡。",
     "image_tokens": ["富貴又何為", "襁褓", "父母違", "吊斜輝", "湘江", "楚雲"]},
    {"id": "正册05", "text": "欲潔何曾潔？云空未必空。可憐金玉質，終陷淖泥中。",
     "person": ["妙玉"], "rationale": "「欲潔」「云空」（妙玉自号槛外人）与「終陷淖泥中」指向妙玉结局。",
     "image_tokens": ["欲潔", "云空", "金玉質", "淖泥"]},
    {"id": "正册06", "text": "子係中山狼，得志便猖狂。金閨花柳質，一載赴黃粱。",
     "person": ["賈迎春"], "rationale": "「中山狼」通行指迎春之夫孙绍祖；「一載赴黃粱」指婚后一年即亡。",
     "image_tokens": ["中山狼", "得志", "猖狂", "金閨", "花柳質", "一載", "黃粱"]},
    {"id": "正册07", "text": "勘破三春景不長，緇衣頓改昔年妝。可憐繡戶侯門女，獨臥青燈古佛旁。",
     "person": ["賈惜春"], "rationale": "「緇衣」「青燈古佛」指向惜春出家。",
     "image_tokens": ["勘破三春", "緇衣", "昔年妝", "繡戶侯門", "青燈古佛"]},
    {"id": "正册08", "text": "凡鳥偏從末世來，都知愛慕此生才。一從二令三人木，哭向金陵事更哀。",
     "person": ["王熙鳳"], "rationale": "「凡鳥」合为「鳳」；「一從二令三人木」拆字为「休」（人+木），指向熙鳳被休/败亡。",
     "image_tokens": ["凡鳥", "末世", "愛慕", "一從二令三人木", "哭向金陵"]},
    {"id": "正册09", "text": "勢敗休云貴，家亡莫論親。偶因濟村婦，巧得遇恩人。",
     "person": ["巧姐"], "rationale": "「濟村婦」「遇恩人」通行指刘姥姥救巧姐；「巧」字入判。",
     "image_tokens": ["勢敗", "家亡", "濟村婦", "巧得", "恩人"]},
    {"id": "正册10", "text": "桃李春風結子完，到頭誰似一盆蘭。如冰水好空相妒，枉與他人作笑談。",
     "person": ["李紈"], "rationale": "「桃李春風結子完」（李紈丧夫守节、教子），「一盆蘭」指其子贾兰。",
     "image_tokens": ["桃李春風", "結子", "一盆蘭", "如冰水好", "笑談"]},
    {"id": "正册11", "text": "情天情海幻情深，情既相逢必主淫。漫言不肖皆榮出，造舋開瑞實在寧。",
     "person": ["秦可卿"], "rationale": "画面「高樓，上有一美人懸樑自盡」；「榮」「寧」对举点出宁府。「造舋開瑞」通行本作「造衅开端」，属语料异文。[语料原文]",
     "image_tokens": ["情天情海", "幻情", "相逢", "不肖", "皆榮出", "實在寧"]},
]

# —— 红楼梦曲 14 支（引子 + 12 支 + 收尾），原文抄自语料 005 回 ——
SONGS = [
    {"id": "曲·引子", "text": "開辟鴻蒙，誰為情種？都只為風月情濃。奈何天，傷懷日，寂寥時，試遣愚衷。因此上演出這悲金悼玉的紅樓夢。",
     "person": ["全書"], "rationale": "总起，点出「悲金悼玉」主题。",
     "image_tokens": ["開辟鴻蒙", "情種", "風月情濃", "悲金悼玉"]},
    {"id": "曲·終身誤", "text": "都道是金玉良緣，俺只念木石前盟。空對著山中高士晶瑩雪，終不忘世外仙姝寂寞林。嘆人間美中不足今方信。縱然是齊眉舉案，到底意難平。",
     "person": ["賈寶玉", "薛寶釵", "林黛玉"], "rationale": "「金玉良緣」对「木石前盟」，「晶瑩雪」谐薛、「寂寞林」谐林。",
     "image_tokens": ["金玉良緣", "木石前盟", "晶瑩雪", "寂寞林", "齊眉舉案", "意難平"]},
    {"id": "曲·枉凝眉", "text": "一個是閬苑仙葩，一個是美玉無瑕。若說沒奇緣，今生偏又遇著他；若說有奇緣，如何心事終虛話？一個枉自嗟呀，一個空勞牽掛。一個是水中月，一個是鏡中花。想眼中能有多少淚珠兒，怎禁得秋流到冬，春流到夏！",
     "person": ["林黛玉", "賈寶玉"], "rationale": "「閬苑仙葩」（绛珠仙草）与「美玉無瑕」（通灵宝玉）；「淚珠兒」合绛珠还泪。",
     "image_tokens": ["閬苑仙葩", "美玉無瑕", "奇緣", "水中月", "鏡中花", "淚珠兒"]},
    {"id": "曲·恨無常", "text": "喜榮華正好，恨無常又到，眼睜睜把萬事全拋，蕩悠悠芳魂銷耗。望家鄉路遠山高。故向娘夢裏邊尋告：兒命己入黃泉，天倫呵，須要退步抽身早！",
     "person": ["賈元春"], "rationale": "「望家鄉路遠山高」「兒命己入黃泉」合元春之死。「己」[语料原文]（通行作「已」）。",
     "image_tokens": ["恨無常", "芳魂", "望家鄉", "路遠山高", "黃泉", "退步抽身"]},
    {"id": "曲·分骨肉", "text": "一帆風雨路三千，把骨肉家園，齊來拋閃。恐哭損殘年，告爹娘休把兒懸念。自古窮通皆有定，離合豈無緣？從今分兩地，各自保平安。奴去也，莫牽連。",
     "person": ["賈探春"], "rationale": "「一帆風雨路三千」「告爹娘」合探春远嫁别亲。",
     "image_tokens": ["一帆風雨", "路三千", "骨肉家園", "殘年", "分兩地", "莫牽連"]},
    {"id": "曲·樂中悲", "text": "襁褓中，父母嘆雙亡。縱居那綺羅叢誰知嬌養？幸生來英豪闊大寬宏量，從未將兒女私情略縈心上。好一似霽月光風耀玉堂，廝配得才貌仙郎，博得個地久天長，准折得幼年時坎坷形狀。終久是雲散高唐，永涸湘江。",
     "person": ["史湘雲"], "rationale": "「襁褓中父母雙亡」「英豪闊大寬宏量」「永涸湘江」合湘云。",
     "image_tokens": ["父母嘆雙亡", "綺羅叢", "英豪闊大", "霽月光風", "才貌仙郎", "雲散高唐", "永涸湘江"]},
    {"id": "曲·世難容", "text": "氣質美如蘭，才華馥比仙。天生成孤癖人皆罕。你道是啖肉食腥膻，視綺羅俗厭。卻不知好高人愈妒，過潔世同嫌。可嘆這青燈古殿人將老，孤負了紅粉朱樓春色闌，到頭來依舊是風塵骯髒違心願。分一似無瑕白玉遭泥陷，又何須王孫公子嘆無緣？",
     "person": ["妙玉"], "rationale": "「孤癖」「過潔」「青燈古殿」「白玉遭泥陷」合妙玉。",
     "image_tokens": ["氣質美如蘭", "才華馥比仙", "孤癖", "過潔", "青燈古殿", "紅粉朱樓", "白玉遭泥陷"]},
    {"id": "曲·喜冤家", "text": "中山狼，無情獸，全不念當日根由。一味的嬌奢淫蕩貪歡媾。覷著那侯門艷質同蒲柳，作踐的公府千金似下流。嘆芳魂艷魂，一栽蕩悠悠。",
     "person": ["賈迎春"], "rationale": "「中山狼」「侯門艷質」「公府千金」合迎春嫁孙绍祖。「一栽」[语料原文]（通行作「一載」）。",
     "image_tokens": ["中山狼", "無情獸", "侯門艷質", "蒲柳", "公府千金", "芳魂"]},
    {"id": "曲·虛花悟", "text": "將那三春勘破，桃紅柳綠待如何？把這韶華打滅，覓那清淡天和。說什麼天上夭桃盛，雲中杏蕊多，到頭來誰見把秋捱過？則看那白揚村裏人鳴咽，青楓林下鬼吟哦，更兼著連天衰草遮墳墓。這的是昨貧今富人勞碌，春榮秋謝花折磨。似這般生關死動誰能躲？聞說道西方寶樹喚婆娑，上結著長生果。",
     "person": ["賈惜春"], "rationale": "「三春勘破」「覓清淡天和」「西方寶樹」合惜春出家。「白揚」[语料原文]（通行作「白楊」）、「生關死動」[语料原文]（通行作「生關死劫」）。",
     "image_tokens": ["三春勘破", "桃紅柳綠", "夭桃", "杏蕊", "白揚村", "青楓林", "衰草", "墳墓", "婆娑", "長生果"]},
    {"id": "曲·聰明累", "text": "機關算盡太聰明，反算了卿卿性命。生前心己碎，死後性空靈。家富人寧，終有個家亡人散各奔騰。枉費了意懸懸半世心，好一似蕩悠悠三更夢。忽喇喇似大廈傾，昏慘慘似燈將盡。呀！一場歡喜忽悲辛，嘆人世終難定！",
     "person": ["王熙鳳"], "rationale": "「機關算盡」「卿卿性命」「家亡人散」合熙鳳。「心己碎」[语料原文]（通行作「心已碎」）。",
     "image_tokens": ["機關算盡", "卿卿性命", "心己碎", "家亡人散", "大廈傾", "燈將盡"]},
    {"id": "曲·留餘慶", "text": "留餘慶，留餘慶，忽遇恩人；幸娘親，親娘親，積得陰功。勸人生濟困扶窮，休似俺那愛銀錢忘骨肉的狠舅奸兄。正是乘除加減，上有蒼穹。",
     "person": ["巧姐"], "rationale": "「忽遇恩人」「濟困扶窮」「狠舅奸兄」合巧姐被救。",
     "image_tokens": ["留餘慶", "恩人", "積得陰功", "濟困扶窮", "狠舅奸兄"]},
    {"id": "曲·晚韶華", "text": "鏡裏恩情，更哪堪夢裏功名！那美韶華去之何迅，再休提繡帳鴦衾。只這戴珠冠披鳳襖也抵不了無常性命。雖說是人生莫受老來貧，也須要陰騭積兒孫。氣昂昂頭戴簪纓，光燦燦胸懸金印，威赫赫爵祿高登，昏慘慘黃泉路近！問古來將相可還有？也只是虛名而後人欽敬。",
     "person": ["李紈"], "rationale": "「戴珠冠披鳳襖」「爵祿高登」「黃泉路近」合李紈晚年丧子（贾兰早逝，通行本解）。",
     "image_tokens": ["鏡裏恩情", "夢裏功名", "珠冠", "鳳襖", "陰騭", "簪纓", "金印", "爵祿", "黃泉路近"]},
    {"id": "曲·好事終", "text": "畫梁春盡落香生。擅風情，秉月貌，便是敗家的根本。箕裘頹墮皆從敬，家聲消亡首罪寧。宿孳總因情。",
     "person": ["秦可卿"], "rationale": "「擅風情，秉月貌」「家聲消亡首罪寧」合可卿。「宿孳」[语料原文]（通行作「宿孽」）。",
     "image_tokens": ["畫梁", "落香", "擅風情", "秉月貌", "箕裘頹墮", "家聲消亡", "首罪寧", "宿孳"]},
    {"id": "曲·飛鳥各投林", "text": "為官的家業凋零，富貴的金銀散盡。有恩的死裏逃生，無情的分明報應。欠命的命己還，欠淚的淚已盡。冤冤相報自非輕，分離聚合皆前定。欲知命短問前生，老來富貴也真僥倖。看破的循入空門，痴迷的枉送了性命。好一似食盡鳥投林，落了片白茫茫大地真干淨！",
     "person": ["全書"], "rationale": "总收十二钗，逐句对点各人结局；「欠淚的淚已盡」合绛珠还泪数尽。「命己還」「循入」[语料原文]（通行作「命已还」「遁入」）、「真干淨」[语料原文]（通行作「真乾淨」）。",
     "image_tokens": ["家業凋零", "金銀散盡", "死裏逃生", "分明報應", "欠命的", "欠淚的", "冤冤相報", "分離聚合", "看破的", "痴迷的", "食盡鳥投林", "白茫茫"]},
]

# ============================================================================
# 二、跨章伏笔对账：以「专名/物名」为锚，追踪全书出现回（决定论）
# ============================================================================
# 只做「字面出现追踪」，不做「是否回收」的自动判定（那需文学判断，标 [评估] 人工给）
ARC_ITEMS = [
    {"item": "通靈寶玉", "tokens": ["通靈寶玉", "通靈", "銜玉而生"], "note": "全书核心信物，第 1 回缘起"},
    {"item": "金鎖", "tokens": ["金鎖", "金瓔珞", "不離不棄", "芳齡永繼"], "note": "宝钗佩物，与通灵宝玉成「金玉良缘」"},
    {"item": "金麒麟", "tokens": ["金麒麟"], "note": "湘云所佩，第 29 回清虚观再得一只"},
    {"item": "絳珠仙草", "tokens": ["絳珠", "還淚", "甘露"], "note": "黛玉前世，第 1 回交代"},
    {"item": "冷香丸", "tokens": ["冷香丸"], "note": "宝钗药方，第 7 回"},
    {"item": "舊帕題詩", "tokens": ["舊帕", "題帕"], "note": "宝玉赠帕、黛玉题帕"},
    {"item": "晴雯撕扇", "tokens": ["撕扇", "扇子作千金一笑"], "note": "第 31 回"},
    {"item": "香囊", "tokens": ["香囊", "剪香囊"], "note": "黛玉剪香囊（第 17 回）"},
    {"item": "白海棠", "tokens": ["白海棠", "海棠社", "海棠詩"], "note": "诗社缘起，第 37 回"},
    {"item": "菊花詩", "tokens": ["菊花詩", "詠菊", "訪菊", "對菊", "問菊"], "note": "第 38 回诗社"},
    {"item": "柳絮詞", "tokens": ["柳絮詞", "柳絮"], "note": "第 70 回诗社"},
    {"item": "螃蟹詠", "tokens": ["螃蟹詠", "螃蟹"], "note": "第 38 回"},
    {"item": "芙蓉女兒誄", "tokens": ["芙蓉女兒誄", "芙蓉誄"], "note": "宝玉祭晴雯，第 78 回"},
    {"item": "大觀園", "tokens": ["大觀園"], "note": "省亲别院"},
    {"item": "金釧之死", "tokens": ["金釧"], "note": "金钏投井，第 32 回"},
    {"item": "馬道婆魘魔法", "tokens": ["馬道婆"], "note": "第 25 回"},
    {"item": "石頭記", "tokens": ["石頭記"], "note": "书名自指，第 1 回"},
]

# —— 人物结局回目（[评估] 节点：依据程高本 120 回通行回目；版本不同则不同）——
OUTCOMES = {
    "晴雯": {"chapter": 77, "basis": "程高本第 77 回「俏丫鬟抱屈夭風流」"},
    "秦可卿": {"chapter": 13, "basis": "程高本第 13 回「秦可卿死封龍禁尉」"},
    "賈元春": {"chapter": 95, "basis": "程高本第 95 回「因訛成實元妃薨逝」"},
    "賈迎春": {"chapter": 80, "basis": "程高本第 80 回迎春被虐后离园（死亡在第 109 回交代）"},
    "王熙鳳": {"chapter": 114, "basis": "程高本第 114 回「王熙鳳歷幻返金陵」"},
    "賈探春": {"chapter": 100, "basis": "程高本第 100 回「悲遠嫁寶玉感離情」"},
    "林黛玉": {"chapter": 98, "basis": "程高本第 98 回「苦絳珠魂歸離恨天」"},
    "賈惜春": {"chapter": 115, "basis": "程高本第 115 回惜春出家（第 118 回正式削发）"},
    "史湘雲": {"chapter": 108, "basis": "程高本第 108 回「史湘雲」夫死情节"},
    "巧姐": {"chapter": 118, "basis": "程高本第 118 回巧姐获救"},
    "襲人": {"chapter": 120, "basis": "程高本第 120 回袭人嫁蒋玉菡"},
    "李紈": {"chapter": 119, "basis": "程高本第 119 回李紈获诰命（贾兰中举）"},
    "薛寶釵": {"chapter": 120, "basis": "程高本第 120 回宝钗有孕、宝玉出家"},
    "妙玉": {"chapter": 112, "basis": "程高本第 112 回妙玉遭劫"},
    "香菱": {"chapter": 120, "basis": "程高本第 120 回香菱被扶正后病亡（第 103 回交代遗腹子）"},
}


# —— 专有/特指意象词白名单 ——
# 只有列在这里的 token 才被计入「意象呼应」统计；其余 image_tokens 视为通用词
# （如「雪裏」「東風」「笑談」「恩人」「黃泉」），其命中多为同字偶合而非意象复现。
# 判据：该词是否只在红楼梦的特定语境/人物身上使用（可回原文逐条核验）。
# 已剔除（核验后为假阳性）：「彩雲」全书 68 次多为丫鬟彩云之名；「結子」第 24/32 回指
# 打结子（编织物）而非「結子完」（结果实）。保留但属弱相关：「優伶」（第 18/33 回泛指戏子）、
# 「荷花」（第 7 回指冷香丸配方白荷花蕊）。
_QUOTE_SPLIT = re.compile(r"[，。！？；：、\s]+")

SPECIFIC_TOKENS = {
    # 判词
    "霽月", "心比天高", "身為下賤", "空牽念", "溫柔和順", "似桂如蘭", "優伶", "公子無緣",
    "荷花", "一莖香", "香魂", "孤木", "兩地",
    "停機德", "詠絮才", "玉帶", "林中", "金簪",
    "榴花", "虎兔", "官闈",
    "才自清明", "運偏消",
    "湘江", "楚雲", "襁褓", "父母違",
    "欲潔", "云空", "淖泥",
    "中山狼", "花柳質", "一載",
    "勘破三春", "緇衣", "青燈古佛",
    "凡鳥", "一從二令三人木", "哭向金陵",
    "濟村婦", "巧得",
    "一盆蘭",
    "情天情海", "幻情", "皆榮出", "實在寧",
    # 曲文
    "開辟鴻蒙", "悲金悼玉",
    "金玉良緣", "木石前盟", "晶瑩雪", "寂寞林", "齊眉舉案",
    "閬苑仙葩", "美玉無瑕", "淚珠兒", "水中月", "鏡中花",
    "恨無常", "芳魂", "黃泉", "退步抽身",
    "一帆風雨", "路三千", "骨肉家園", "莫牽連",
    "父母嘆雙亡", "英豪闊大", "霽月光風", "才貌仙郎", "雲散高唐", "永涸湘江",
    "氣質美如蘭", "才華馥比仙", "孤癖", "過潔", "青燈古殿", "白玉遭泥陷",
    "無情獸", "侯門艷質", "蒲柳", "公府千金",
    "白揚村", "青楓林", "墳墓", "長生果",
    "機關算盡", "卿卿性命", "心己碎", "家亡人散", "大廈傾",
    "留餘慶", "積得陰功", "濟困扶窮", "狠舅奸兄",
    "鏡裏恩情", "珠冠", "鳳襖", "簪纓", "金印", "爵祿", "黃泉路近",
    "秉月貌", "箕裘頹墮", "家聲消亡", "首罪寧", "宿孳",
    "食盡鳥投林", "欠淚的", "看破的", "痴迷的",
}


def build_quote_rows(corpus, items, label):
    """整句级显式引用检测（强证据）：判词/曲文的整句在正文中的出现。

    与词级匹配的区别：整句（≥6 字）偶合概率极低，命中即可判定为**显式引用/回收**。
    这是本轮唯一通过核验的高判别力指标。
    """
    rows = []
    for p in items:
        segs = [s for s in _QUOTE_SPLIT.split(p["text"]) if len(s) >= 6]
        found = []
        for s in segs:
            h = [x for x in locate(s, corpus) if x["chapter"] != 5]
            if h:
                found.append({"segment": s, "hits": h})
        rows.append({
            "id": p["id"], "label": label, "person": p["person"],
            "segments": len(segs), "quoted": found,
            "quoted_front80": sum(x["count"] for f in found for x in f["hits"] if x["chapter"] <= 80),
            "quoted_back40": sum(x["count"] for f in found for x in f["hits"] if x["chapter"] > 80),
            "quoted_chapters": sorted({x["chapter"] for f in found for x in f["hits"]}),
        })
    return rows


def load_corpus():
    out = {}
    for f in sorted(os.listdir(CORPUS)):
        if f.endswith(".txt"):
            out[int(f[:3])] = open(os.path.join(CORPUS, f), encoding="utf-8").read()
    return out


def locate(token, corpus):
    """返回 token 在全书出现的 [(回号, 次数, 首处上下文片段)]。"""
    hits = []
    for ch in sorted(corpus):
        t = corpus[ch]
        n = t.count(token)
        if n:
            p = t.find(token)
            hits.append({"chapter": ch, "count": n,
                         "snippet": t[max(0, p - 18):p + len(token) + 18].replace("\n", " ")})
    return hits


def build_prophecy_rows(corpus, items, label):
    rows = []
    for p in items:
        toks = []
        for tk in p["image_tokens"]:
            h = locate(tk, corpus)
            toks.append({"token": tk, "total": sum(x["count"] for x in h),
                         "chapters": [x["chapter"] for x in h],
                         "hits": h,
                         "specific": tk in SPECIFIC_TOKENS,
                         "sample": h[0]["snippet"] if h else ""})
        spec = [t for t in toks if t["specific"]]
        gen = [t for t in toks if not t["specific"]]

        def half(lst, lo, hi):
            return sum(x["count"] for t in lst for x in t["hits"] if lo <= x["chapter"] <= hi)

        rows.append({
            "kind": label, "id": p["id"], "text": p["text"],
            "person_estimate": p["person"], "rationale": p["rationale"],
            "tokens": toks,
            "token_total": sum(t["total"] for t in toks),
            "token_hit_chapters": sorted({c for t in toks for c in t["chapters"]}),
            # 专有词（有判别力）
            "specific_total": sum(t["total"] for t in spec),
            "specific_outside_ch5": sum(x["count"] for t in spec for x in t["hits"] if x["chapter"] != 5),
            "specific_front80": half(spec, 1, 80),
            "specific_back40": half(spec, 81, 120),
            "specific_tokens": [t["token"] for t in spec],
            # 通用词（无判别力，仅备查；同时留作对照检验）
            "generic_total": sum(t["total"] for t in gen),
            "generic_front80": half(gen, 1, 80),
            "generic_back40": half(gen, 81, 120),
            "generic_tokens": [t["token"] for t in gen],
            "outcome_chapters": [{"person": x, "chapter": OUTCOMES[x]["chapter"],
                                  "basis": OUTCOMES[x]["basis"]}
                                 for x in p["person"] if x in OUTCOMES],
            "persons_with_outcome": len([x for x in p["person"] if x in OUTCOMES]),
        })
    return rows


def build_arc_rows(corpus):
    rows = []
    for it in ARC_ITEMS:
        per_tok = []
        for tk in it["tokens"]:
            h = locate(tk, corpus)
            if h:
                per_tok.append({"token": tk, "total": sum(x["count"] for x in h),
                                "chapters": [x["chapter"] for x in h]})
        chs = sorted({c for t in per_tok for c in t["chapters"]})
        rows.append({
            "item": it["item"], "note": it["note"], "tokens": per_tok,
            "hit_total": sum(t["total"] for t in per_tok),
            "first_chapter": chs[0] if chs else None,
            "last_chapter": chs[-1] if chs else None,
            "spread_chapters": len(chs),
            "chapters": chs,
        })
    return rows


# —— 已逐条回原文核验的确凿误录（每项都在下方 locate 后可见上下文）——
KNOWN_ERRATA = [
    ("紅摟", "紅樓", "第 005 回〔紅摟夢引子〕标目"),
    ("己入黃泉", "已入黃泉", "第 005 回〔恨無常〕"),
    ("心己碎", "心已碎", "第 005 回〔聰明累〕"),
    ("命己還", "命已還", "第 005 回〔飛鳥各投林〕"),
    ("造舋開瑞", "造衅开端", "第 005 回正册判词（秦可卿）"),
    ("宿孳", "宿孽", "第 005 回〔好事終〕"),
    ("一栽蕩悠悠", "一載蕩悠悠", "第 005 回〔喜冤家〕"),
    ("白揚村", "白楊村", "第 005 回〔虛花悟〕"),
    ("循入空門", "遁入空門", "第 005 回〔飛鳥各投林〕"),
    ("生關死動", "生關死劫", "第 005 回〔虛花悟〕"),
    ("真干淨", "真乾淨", "第 005 回〔飛鳥各投林〕"),
]

# 反面案例：这些字看起来像「误录标记」，核验后证明是正常用字或情节差异
FALSE_MARKERS = [
    ("摟", "误以为「樓」之误；核验：全书 26 次中 25 次为「摟入懷中」「摟著」等正常用字，"
           "仅 1 次「紅摟夢」为误录。前 80 回 24 次 vs 后 40 回 2 次的差异源于情节"
           "（前 80 多亲昵场景），非录入质量。"),
    ("己", "误以为「已」之误；抽样 10 例中 7 例为「自己」「體己」等正确用法，"
           "真正误录集中于第 005 回曲文（3 例）。"),
]


def build_quality_rows(corpus):
    """确凿误录的逐项定位（事实节点）+ 反面案例（防频率误读）。"""
    rows = []
    for bad, good, note in KNOWN_ERRATA:
        h = locate(bad, corpus)
        rows.append({"errata": bad, "should_be": good, "note": note,
                     "count": sum(x["count"] for x in h),
                     "chapters": [x["chapter"] for x in h],
                     "front80": sum(x["count"] for x in h if x["chapter"] <= 80),
                     "back40": sum(x["count"] for x in h if x["chapter"] > 80)})
    return rows


def write_md(prop_rows, song_rows, quote_rows, arc_rows, q_rows, path, front_chars, back_chars, corpus):
    L = []
    A = L.append
    A("# 《红楼梦》伏笔对账 + 判词谶语解析")
    A("")
    A("模块：`foreshadow_arc.py`（决定论、零依赖）。语料：`corpus/红楼梦`（120 回繁体）。")
    A("")
    A("> 节点分两类：**事实节点**（token 在全书各回的字面出现，可逐条回原文核验）与")
    A("> **评估节点 [评估]**（指向谁、是否应验的解释，依据随附）。本报告不把评估当事实。")
    A("")
    A("## 一、判词谶语 × 人物 × 应验章节")
    A("")
    A("「专有词」= 只在红楼梦特定语境使用的意象词（可作判别）；「通用词」= 同字偶合可能")
    A("（如雪裏/東風/笑談），已从判别统计中剔除，仅在 JSON 中备查。")
    A("")
    for label, rows in (("又副册 / 副册 / 正册判词", prop_rows), ("红楼梦曲", song_rows)):
        A("### %s" % label)
        A("")
        A("| 条目 | 谶语（语料原文） | 指向 [评估] | 专有词命中 前80/后40 | 应验章节 [评估·程高本] |")
        A("|---|---|---|---|---|")
        for r in rows:
            if r["specific_tokens"]:
                hit = "、".join("%s×%d" % (t["token"], t["total"])
                                for t in r["tokens"] if t["specific"] and t["total"])
                hit = (hit or "—") + "（%d/%d）" % (r["specific_front80"], r["specific_back40"])
            else:
                hit = "无专有词"
            oc = "、".join("%s 第%d回" % (x["person"], x["chapter"]) for x in r["outcome_chapters"]) or "—"
            A("| %s | %s | %s | %s | %s |" % (r["id"], r["text"], "/".join(r["person_estimate"]), hit, oc))
        A("")
    all_rows = prop_rows + song_rows
    sf = sum(r["specific_front80"] for r in all_rows)
    sb = sum(r["specific_back40"] for r in all_rows)
    gf = sum(r["generic_front80"] for r in all_rows)
    gb = sum(r["generic_back40"] for r in all_rows)
    n_spec = sum(len(r["specific_tokens"]) for r in all_rows)
    n_zero = sum(1 for r in all_rows if r["specific_outside_ch5"] == 0)
    # 人物名对照基线（排除「人物出场变少」这一解释）
    NAMES_BASE = ["寶玉", "黛玉", "寶釵", "鳳姐", "賈母", "襲人", "晴雯", "湘雲",
                  "探春", "李紈", "妙玉", "迎春", "惜春", "巧姐", "可卿", "香菱", "平兒", "鴛鴦"]
    nf = sum(corpus[c].count(n) for n in NAMES_BASE for c in corpus if c <= 80)
    nb = sum(corpus[c].count(n) for n in NAMES_BASE for c in corpus if c > 80)
    r_spec = (sb / back_chars) / max(1e-9, sf / front_chars)
    r_gen = (gb / back_chars) / max(1e-9, gf / front_chars)
    r_name = (nb / back_chars) / max(1e-9, nf / front_chars)
    A("### 指标对照检验（本节是上一版「核心指标」的自我证伪）")
    A("")
    A("| 词组 | 前 80 回（每万字） | 后 40 回（每万字） | 后/前 比值 |")
    A("|---|---|---|---|")
    A("| 谶语专有词（%d 个） | %.3f | %.3f | **%.2f** |" % (n_spec, 10000 * sf / front_chars, 10000 * sb / back_chars, r_spec))
    A("| 谶语通用词（对照组） | %.3f | %.3f | **%.2f** |" % (10000 * gf / front_chars, 10000 * gb / back_chars, r_gen))
    A("| 主角名（%d 个，第二对照组） | %.3f | %.3f | **%.2f** |" % (len(NAMES_BASE), 10000 * nf / front_chars, 10000 * nb / back_chars, r_name))
    A("")
    A("**结论（事实节点）**：三组词的衰减比**互不相同**（专有词 %.2f、通用词 %.2f、主角名 %.2f）；"
      % (r_spec, r_gen, r_name))
    A("而整句引用指标给出的方向**相反**（前 80 回 0 → 后 40 回 6，见下节）。")
    A("")
    A("**推论 [评估]**：词级命中的衰减主要由**词性与语体**决定（谶语词汇属诗词雅言，雅言密度")
    A("在后 40 回本就更低；人物出场密度前后一致，说明不是人物缺席），**不具备续书判别力**；")
    A("且与整句引用指标方向相反，进一步说明词级指标不可靠。")
    A("**上一版把它称作「核心指标」是错的，此处更正。**")
    A("")
    A("保留价值在这三点（均不受上述证伪影响）：")
    A("① 谶语原文结构化收录（%d 条，含语料异文标注）；" % len(all_rows))
    A("② 每条意象词的字面出现回次（可逐条回原文核验，见 JSON 的 tokens[].chapters）；")
    A("③ 语料文本质量核验（第三节）。")
    A("")
    qf = sum(r["quoted_front80"] for r in quote_rows)
    qb = sum(r["quoted_back40"] for r in quote_rows)
    cited = [r for r in quote_rows if r["quoted"]]
    A("### 整句级显式引用（本轮唯一通过核验的强指标）")
    A("")
    A("方法：把判词/曲文按标点切为整句，只保留 ≥6 字者，在全书中检索整句。")
    A("长句偶合概率极低，命中即可判定为**正文显式引用**（而非词级偶合）。")
    A("")
    A("| 谶语 | 指向 [评估] | 被引用的整句 | 出现回 |")
    A("|---|---|---|---|")
    for r in cited:
        for f in r["quoted"]:
            A("| %s | %s | %s | %s |" % (r["id"], "/".join(r["person"]), f["segment"],
                                        "、".join("第 %d 回" % x["chapter"] for x in f["hits"])))
    A("")
    A("| 项 | 值 |")
    A("|---|---|")
    A("| 有显式引用的谶语条数 | %d / %d |" % (len(cited), len(quote_rows)))
    A("| 引用次数 前 80 回 / 后 40 回 | **%d / %d** |" % (qf, qb))
    A("| 引用集中回目 | %s |" % ("、".join("第 %d 回" % c for c in sorted({c for r in cited for c in r["quoted_chapters"]})) or "—"))
    A("")
    A("**事实节点**：整句引用全部出现在后 40 回（第 116、118 回），前 80 回为 0。")
    A("")
    A("**推论 [评估]**：前 80 回对判词是**意象渗透**式承接（不点名，故词级有命中、整句无）；")
    A("后 40 回转为**点名引用**式承接（第 116 回宝玉回想「青燈古佛旁」，第 118 回惜春出家时")
    A("整首判词被念出）。两种承接方式不同，这是可复现的文体差异事实。")
    A("**但它不证明任何一方非原作者**：两种方式都可出自同一人或不同人，需与版本学证据合看。")
    A("")
    A("### 事实样本：专有词的最强复现（可回原文逐条核验）")
    A("")
    A("| 谶语 | 专有词 | 总数 | 出现回 |")
    A("|---|---|---|---|")
    strongest = sorted([(r, t) for r in all_rows for t in r["tokens"]
                        if t["specific"] and t["total"] > 0],
                       key=lambda x: -x[1]["total"])[:10]
    for r, t in strongest:
        chs = "、".join(map(str, t["chapters"][:12])) + ("…" if len(t["chapters"]) > 12 else "")
        A("| %s | %s | %d | %s |" % (r["id"], t["token"], t["total"], chs))
    A("")
    A("### 应验依据（[评估] 节点，依据程高本 120 回通行回目）")
    A("")
    A("| 人物 | 结局回 | 依据 |")
    A("|---|---|---|")
    for k, v in OUTCOMES.items():
        A("| %s | 第 %d 回 | %s |" % (k, v["chapter"], v["basis"]))
    A("")
    A("## 二、跨章伏笔对账（专名/物名追踪，事实节点）")
    A("")
    A("| 伏笔物 | 命中总次数 | 首现回 | 末现回 | 覆盖回数 | 涉及回目 |")
    A("|---|---|---|---|---|---|")
    for r in sorted(arc_rows, key=lambda x: -(x["hit_total"] or 0)):
        chs = r["chapters"]
        show = "、".join(map(str, chs[:14])) + ("…" if len(chs) > 14 else "")
        A("| %s | %d | %s | %s | %d | %s |" % (r["item"], r["hit_total"],
                                              r["first_chapter"], r["last_chapter"],
                                              r["spread_chapters"], show))
    A("")
    A("说明：本节只给「字面出现回次」；「是否回收」需文学判断，不自动判定。")
    A("")
    A("## 三、语料文本质量核验")
    A("")
    A("### 3.1 已逐条回原文核验的确凿误录（事实节点）")
    A("")
    A("| 误录串 | 应为 | 出现回 | 次数 | 前80 | 后40 | 出处 |")
    A("|---|---|---|---|---|---|---|")
    for r in q_rows:
        A("| %s | %s | %s | %d | %d | %d | %s |" % (
            r["errata"], r["should_be"], "、".join(map(str, r["chapters"])) or "—",
            r["count"], r["front80"], r["back40"], r["note"]))
    tot_f = sum(r["front80"] for r in q_rows)
    tot_b = sum(r["back40"] for r in q_rows)
    A("| **合计** |  |  | **%d** | **%d** | **%d** |  |" % (tot_f + tot_b, tot_f, tot_b))
    A("")
    A("事实：本轮核验到的确凿误录共 %d 处，其中第 005 回占 %d 处。"
      % (tot_f + tot_b, sum(r["count"] for r in q_rows if 5 in r["chapters"])))
    A("")
    A("### 3.2 反面案例：频率差异 ≠ 质量差异（本节是自我证伪）")
    A("")
    for mk, note in FALSE_MARKERS:
        A("- **「%s」**：%s" % (mk, note))
    A("")
    A("**上一版结论作废**：初稿曾据「摟」前 80 回 24 次 / 后 40 回 2 次、「己/已」比值 0.763 vs 0.930，")
    A("断言「误录密度在前 80 回更高」。逐条核验上下文后该结论不成立——两个指标方向相反，")
    A("且主因是正常用字与情节差异。**不支持的结论不得保留。**")
    A("")
    A("### 3.3 结论")
    A("")
    A("- 事实：语料存在零星形近误录，已确证的集中出现在第 005 回（曲文与判词区）；")
    A("  其余 119 回未发现确凿误录样本（本轮扫描范围有限，不等于不存在）。")
    A("- [评估] 这些误录对词频型指标的扰动幅度**未量化**——量化需要有校勘本作对照，")
    A("  当前语料没有，故不能给出「误录影响 X%」这类数字。")
    A("- 验证方式：以人民文学出版社本或庚辰本影印为对照，重跑 `foreshadow_arc.py` 与 `hlm_audit.py`，")
    A("  比较同一指标是否稳定。")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--section", default="all", choices=["all", "prophecy", "arc", "quality"])
    ap.add_argument("--out-md", default=os.path.join(OUTDIR, "红楼梦_伏笔谶语对账.md"))
    ap.add_argument("--out-json", default=os.path.join(OUTDIR, "红楼梦_伏笔谶语对账.json"))
    args = ap.parse_args()

    corpus = load_corpus()
    print("载入 %d 回，总字数 %d" % (len(corpus), sum(len(t) for t in corpus.values())))
    front_chars = sum(len(corpus[c]) for c in corpus if c <= 80)
    back_chars = sum(len(corpus[c]) for c in corpus if c > 80)

    prop_rows = build_prophecy_rows(corpus, PROPHECIES, "判词")
    song_rows = build_prophecy_rows(corpus, SONGS, "曲文")
    quote_rows = (build_quote_rows(corpus, PROPHECIES, "判词")
                  + build_quote_rows(corpus, SONGS, "曲文"))
    arc_rows = build_arc_rows(corpus)
    q_rows = build_quality_rows(corpus)

    if args.section in ("all", "prophecy"):
        print("判词 %d 条｜曲文 %d 条" % (len(prop_rows), len(song_rows)))
        for r in prop_rows + song_rows:
            print("  %-12s 意象命中 %3d 次 | 覆盖 %s 回" % (r["id"], r["token_total"], len(r["token_hit_chapters"])))
    if args.section in ("all", "arc"):
        print("伏笔物 %d 项" % len(arc_rows))
        for r in sorted(arc_rows, key=lambda x: -(x["hit_total"] or 0))[:6]:
            print("  %-10s 命中 %4d 次 | 回目 %s-%s | 覆盖 %d 回" % (r["item"], r["hit_total"], r["first_chapter"], r["last_chapter"], r["spread_chapters"]))
    if args.section in ("all", "quality"):
        print("确凿误录 %d 项，合计 %d 处（前80 %d / 后40 %d）" % (
            len(q_rows), sum(r["count"] for r in q_rows),
            sum(r["front80"] for r in q_rows), sum(r["back40"] for r in q_rows)))

    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump({"prophecies": prop_rows, "songs": song_rows, "quote_citations": quote_rows,
                   "arc_items": arc_rows, "text_quality": q_rows,
                   "outcomes": OUTCOMES}, f, ensure_ascii=False, indent=1)
    write_md(prop_rows, song_rows, quote_rows, arc_rows, q_rows, args.out_md, front_chars, back_chars, corpus)
    print("报告：%s" % args.out_md)
    print("数据：%s" % args.out_json)


if __name__ == "__main__":
    main()
