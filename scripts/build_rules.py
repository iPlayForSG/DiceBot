"""Make concise Chinese play guides from official rules where a hosted Chinese PDF is absent."""

from pathlib import Path
import shutil

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web/public/rules"
OUT.mkdir(parents=True, exist_ok=True)
pdfmetrics.registerFont(TTFont("SimHei", "C:/Windows/Fonts/simhei.ttf"))

TITLE = ParagraphStyle("title", fontName="SimHei", fontSize=22, leading=28, textColor=colors.HexColor("#283449"), spaceAfter=15)
INTRO = ParagraphStyle("intro", fontName="SimHei", fontSize=10.5, leading=17, textColor=colors.HexColor("#566275"), spaceAfter=16)
HEAD = ParagraphStyle("head", fontName="SimHei", fontSize=14, leading=20, textColor=colors.HexColor("#28576a"), spaceBefore=13, spaceAfter=7)
BODY = ParagraphStyle("body", fontName="SimHei", fontSize=10.3, leading=16, textColor=colors.HexColor("#273440"), spaceAfter=7)
SOURCE = ParagraphStyle("source", fontName="SimHei", fontSize=8.5, leading=13, textColor=colors.HexColor("#687789"), spaceBefore=13)


def make(slug, title, intro, sections, source):
    path = OUT / f"{slug}.pdf"
    story = [Paragraph(title, TITLE), Paragraph(intro, INTRO)]
    for heading, lines in sections:
        story.append(Paragraph(heading, HEAD))
        for line in lines:
            story.append(Paragraph(line, BODY))
    story.append(Paragraph("本中文说明为本站依据所列原版规则整理的游玩指南。卡牌文字与特殊情况以牌面及原版规则为准。", SOURCE))
    story.append(Paragraph(f"原版规则：{source}", SOURCE))
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=45, rightMargin=45, topMargin=47, bottomMargin=48,
                      title=title, author="桌游夜航").build(story)
    print(path, path.stat().st_size)


make("love-letter", "情书 Love Letter｜中文游玩指南", "2–6 人｜2019 新版 21 张人物牌。每轮尽量留下更有价值的手牌，也可让其他玩家出局。", [
    ("准备", ["洗混 21 张人物牌，暗置 1 张；双人局另外明置 3 张。每人发 1 张手牌。准备好好感标记，并公开已打出及弃掉的牌。" ]),
    ("回合与轮次", ["顺时针行动：抽 1 张，在两张手牌中选 1 张面朝上打出，执行效果，另一张留在手中。出局时公开弃掉手牌，本轮不再行动。", "若牌堆用尽，仍在场的玩家公开手牌；牌面点数最高者赢得本轮，平手者各得 1 个好感标记。若仅剩 1 人在场，该玩家立即赢得本轮。下一轮重新洗牌、暗置牌并发牌。"]),
    ("人物牌速查", ["0 间谍×2：本轮只有你打出或弃掉过间谍时，轮末额外得 1 个标记。", "1 卫兵×6：猜一名其他玩家手牌的人物，不能猜卫兵；猜中则对方出局。", "2 牧师×2：私下查看一名其他玩家的手牌。3 男爵×2：与另一人私下比较手牌点数，较低者出局。", "4 侍女×2：到你的下个回合开始前，其他人不能指定你。5 王子×2：指定任一玩家（可选自己）弃掉手牌并补抽；弃掉公主会出局。", "6 大臣×2：额外抽 2 张，从手中 3 张选 1 张保留，另 2 张依自选顺序暗放牌堆底。7 国王×1：与另一玩家交换手牌。", "8 伯爵夫人×1：若另一张手牌是国王或王子，必须打出伯爵夫人。9 公主×1：只要打出或弃掉就立即出局。"]),
    ("整局获胜", ["所需好感标记：2 人 6 个；3 人 5 个；4 人 4 个；5–6 人 3 个。达到门槛者获胜。经典 2–4 人版可移除 1 张卫兵、2 张大臣与 2 张间谍。"]),
], "https://cdn.svc.asmodee.net/production-zman/uploads/2024/09/LL_Rulebook_with_Bag-1.pdf")

make("sushi-go", "寿司 Go！｜中文游玩指南", "2–5 人｜3 轮选牌传手。看自己与其他玩家面前的寿司，收集最有利的组合。", [
    ("准备与选牌", ["洗混 108 张牌。每轮按人数发牌：2 人各 10 张，3 人各 9 张，4 人各 8 张，5 人各 7 张。剩余牌面朝下留在中央。", "所有人同时从手中选 1 张暗放，随后一同翻开，再把剩余手牌传给左侧玩家。反复进行，直到手牌用完。每轮结算后，除布丁外的牌弃掉，重新发相同数量的手牌。"]),
    ("卡牌计分", ["天妇罗：每 2 张 5 分；生鱼片：每 3 张 10 分；饺子：1/2/3/4/5 张及以上分别得 1/3/6/10/15 分。", "饭团／握寿司：鱿鱼 3 分、鲑鱼 2 分、鸡蛋 1 分。已有芥末时，下一张握寿司放在其上，分数乘 3；每张芥末只搭配 1 张。", "寿司卷：比较每人寿司卷图标总数。最多者合分 6 分，次多者合分 3 分；第一名并列时不颁第二名分数。并列分数平均分配，余数舍去。", "筷子：打出后的后续某个选牌回合，可拿 2 张牌，再把筷子放回手中传走；筷子本身 0 分。"]),
    ("布丁与胜负", ["布丁跨轮保留，在第三轮结束后计分。最多者平分 6 分，最少者平分负 6 分；所有人数量相同时无人得失分。双人局不扣最少者的分。", "三轮总分最高者获胜；同分时布丁较多者胜出。若使用双人虚拟玩家变体或改变传牌方向，请赛前商定。"]),
], "https://gamewright.com/pdfs/Rules/SushiGoTM-RULES.pdf")

make("once-upon-a-time", "从前从前｜中文游玩指南", "2–6 人｜边讲故事边打出故事牌。先把自己的故事牌自然地用进故事，再合理地接上自己的结局牌。", [
    ("准备", ["故事牌与结局牌分别洗混。每人取 1 张结局牌；故事牌数量：2 人各 10 张、3 人各 8 张、4 人各 7 张、5 人各 6 张、6 人各 5 张。选出第一位讲述者。", "故事牌分人物、地点、物品、特征和事件等类别；特别的打断牌可按普通故事牌使用，也可在类别匹配时打断。"]),
    ("讲故事与打牌", ["讲述者自由续写共同故事。讲到手中某张牌所示的元素，且该元素对情节有实际作用时，可把该牌打到桌面；每张牌应在不同句子中自然出现。", "讲述者可主动让出讲述权：抽 1 张故事牌，还可弃掉 1 张手牌，然后轮到左侧玩家。停顿过久、情节明显矛盾时，其他玩家可共同决定交接讲述权。"]),
    ("打断与结束", ["若讲述者提到了你手牌里的故事元素，你可打出该牌接管讲述；若讲述者刚打出故事牌，你也可用相应类别的打断牌接管。前讲述者抽 1 张故事牌，新讲述者必须承接已有情节。", "有争议的打断由其他玩家表决。无效打断通常弃掉尝试打出的牌并抽 2 张。", "讲述者打完所有故事牌后，若自己的结局牌能合乎情理地结束故事，就打出结局牌并获胜。若众人认为结局明显不通顺，则改抽 1 张结局牌和 1 张故事牌，讲述权交给左侧玩家。"]),
], "https://atlas-games.com/pdf_storage/ouat_rulebook.pdf")

make("flip-city", "翻转城市 Flip City｜中文游玩指南", "1–4 人｜冒险翻开城市卡，控制不满值，再用收入购买、翻转或开发卡牌。", [
    ("准备与目标", ["按卡牌所示准备公共供应堆与每位玩家的初始牌组，洗混自己的牌组。轮流进行行动；在同一回合的出牌阶段达到至少 8 点胜利分，并撑到建造阶段结束，即可获胜。部分卡牌还有替代胜利条件。"]),
    ("出牌阶段", ["从自己的牌组顶逐张翻牌并立即结算，可随时选择停止。牌组耗尽时洗混弃牌堆组成新牌组。打出的牌给出临时金钱、胜利分及不满值，牌面特殊效果优先执行。", "若本回合已打出的卡累计达到 3 点不满值，立即爆牌：本回合提前结束，打出的牌移到弃牌堆。可回收的弃牌可依牌面能力翻面并取得临时效果；具体费用和限制见牌面。"]),
    ("建造阶段与回合结束", ["保有的临时金钱可用于一次建造行动：购买公共供应卡放入自己的弃牌堆；支付翻转费用，把自己弃牌堆中的卡翻到另一面；或支付购买价加翻转费用，直接取得翻面后的公共卡。", "已打出的牌此时仍不属于弃牌堆。建造结束后检查胜利条件，再把本回合打出的牌放入弃牌堆。临时金钱、胜利分和不满值均不带到下个回合。"]),
], "https://cs.uwaterloo.ca/~dtompkin/dtlib/base/Flip%20City.pdf")

for slug in ("azul", "hanamikoji"):
    source = ROOT / "data/rules-sources" / f"{slug}.pdf"
    target = OUT / f"{slug}.pdf"
    shutil.copyfile(source, target)
    print(target, target.stat().st_size)
