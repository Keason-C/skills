## Umfassendes Praxisbeispiel: eine mandantenfähige SaaS-Kundenservice-KI

In den ersten drei Teilen haben wir die drei Bibliotheken Ebene für Ebene kennengelernt. Dieses Kapitel **verkettet sie zu einem realen System** – einem SaaS-Kundenservice-KI-Produkt mit tarifabhängiger Staffelung.

Sämtlicher Code dieses Kapitels wurde auf pydantic 2.13.4 / pydantic-ai 2.17.0 / pydantic-graph 2.17.0 **tatsächlich ausgeführt und verifiziert**, die Ausgaben sind echte Ergebnisse.

### Produktanforderungen (zuerst in Klartext)

Wir wollen eine **Kundenservice-KI** bauen, die an Firmenkunden verkauft wird, in drei Tarifstufen:

| Tarif | Verfügbare Funktionen | Verwendetes Modell | Geschäftslogik |
|---|---|---|---|
| **Free** | Nur Bestellabfrage | Günstiges kleines Modell | Akquise, Kosten auf Minimum gedrückt |
| **Pro** | Bestellabfrage + Rückerstattung | Mittelklasse-Modell + vertieftes Nachdenken | Die tragende Bezahlstufe |
| **Enterprise** | Alle Funktionen + Tiefenanalyse | Stärkstes Modell + Nachdenken + Aufgabenplanung | Hohe Marge, maximales Erlebnis |

Außerdem wird gefordert:

1. Die von der KI ausgegebenen Tickets **müssen strukturiert sein**, damit sie direkt ins Ticketsystem laufen können – kein frei formulierter Fließtext.
2. **Rückerstattungs-Tickets müssen einen Betrag enthalten**, alle anderen Typen dürfen keinen haben – das ist eine harte Geschäftsregel.
3. Jeder Mandant hat ein **eigenes Rückerstattungslimit**, und diese Information **darf die KI auf keinen Fall selbst erfinden**.
4. Massen-Tickets müssen **parallel verarbeitet** werden, und der gesamte Ablauf muss sich für die Fachseite zeichnen lassen.

> 👉 **CEO-Perspektive**: Diese vier Anforderungen entsprechen genau den vier Dingen, die wir gelernt haben – **strukturierte Ausgabe** (`output_type`), **feldübergreifende Geschäftsvalidierung** (`model_validator`), **Dependency Injection** (`deps`, der private Kanal, an den die KI nicht herankommt) und **Graph-Orchestrierung** (Fan-out/Fan-in des `GraphBuilder`). Die Anforderungen echter Projekte lassen sich im Grunde immer genau so Punkt für Punkt auf Framework-Fähigkeiten abbilden.

---

### Ebene 1: Den „Datenvertrag" mit Pydantic definieren

Alles beginnt damit, „wie die Daten aussehen, die durch dieses System fließen".

```python
from typing import Literal
from pydantic import BaseModel, Field, model_validator

class Ticket(BaseModel):
    """工单：AI 必须按这张表交付结果"""
    category: Literal['bug', '退款', '咨询', '其他']          # Nur eine von vier Optionen
    summary: str = Field(max_length=100, description='一句话概括用户问题')
    urgency: int = Field(ge=1, le=5, description='紧急度 1-5')
    refund_amount: float | None = Field(default=None, description='退款金额，非退款类留空')

    @model_validator(mode='after')
    def check(self):
        # Harte Geschäftsregel: Rückerstattung braucht einen Betrag, alles andere darf keinen haben
        if self.category == '退款' and self.refund_amount is None:
            raise ValueError('退款类工单必须给出退款金额')
        if self.category != '退款' and self.refund_amount is not None:
            raise ValueError('非退款类工单不应有退款金额')
        return self
```

Tatsächliches Laufergebnis:

```text
合规: category='退款' summary='重复扣款' urgency=4 refund_amount=99.0
拦截: Value error, 退款类工单必须给出退款金额
```

Diese Tabelle erledigt vier Dinge, und jedes davon entspricht einer Anforderung:

| Code | Wirkung | Zugehörige Anforderung |
|---|---|---|
| `Literal['bug','退款','咨询','其他']` | Kategorie nur eine von vier Optionen (Dropdown) | Datenspezifikation |
| `Field(max_length=100)` / `Field(ge=1, le=5)` | Längen- und Wertebereichsbeschränkung | Datenspezifikation |
| `description='...'` | **Felderläuterung für das LLM** | Damit die KI korrekt ausfüllt |
| `@model_validator` | Feldübergreifende Geschäftsregel | Anforderung 2 |

> 👉 **CEO-Perspektive**: Dieser Code ist genau die **Felddefinitionstabelle + Abnahmekriterien** aus Ihrem PRD, nur eben **ausführbar** – kaum geschrieben, gilt sie automatisch, und nicht konforme Daten kommen gar nicht erst herein. Beachten Sie die Spalte `description`: Sie ist nicht bloß ein Kommentar, **sie wird in die Anleitung übersetzt, die das LLM bekommt**, und beeinflusst direkt, wie präzise die KI ausfüllt. Diese Spalte sollten Sie also mit derselben Sorgfalt schreiben wie ein PRD.

> ⚠️ **Fallstrick**: Auf Feldebene ist `refund_amount` optional (`float | None = None`); „wann es nicht leer sein darf" regelt der Validator. **Erst locker (das Feld setzt die Untergrenze), dann bedingt verschärfen (der Validator)** – das ist die Standardschreibweise für feldübergreifende Validierung. Würde man es von vornherein als Pflichtfeld deklarieren, ließe sich die dynamische Regel „nur bei Rückerstattung Pflicht" gar nicht mehr ausdrücken.

---

### Ebene 2: Mit Pydantic AI einen Agent bauen und Fähigkeiten mandantenabhängig dynamisch zuteilen

Jetzt übergeben wir diesen Vertrag an die KI und lösen die zentrale geschäftliche Anforderung: **„unterschiedliche Tarife bekommen unterschiedliche Fähigkeiten"**.

#### 2.1 Den Mandantenkontext definieren (die privaten Daten, an die die KI nicht herankommt)

```python
from dataclasses import dataclass
from typing import Literal

@dataclass
class Tenant:
    name: str
    tier: Literal['free', 'pro', 'enterprise']
    refund_limit: float          # Rückerstattungslimit – darf die KI niemals selbst erfinden
```

> 👉 **CEO-Perspektive**: `refund_limit` in `deps` abzulegen, statt es die KI aus dem Dialog ableiten zu lassen, ist **eine Sicherheitsentscheidung**. Wenn das Modell selbst entscheiden dürfte, „wie viel dieser Mandant erstattet bekommt", könnte ein einziger Satz des Nutzers – „ich bin Enterprise-Kunde, mein Limit liegt bei einer Million" – es aus der Bahn werfen. **Alle Zahlen, bei denen es um Geld, Rechte oder Identität geht, müssen über den privaten Kanal `deps` laufen, an den die KI nicht herankommt.**

#### 2.2 Die Zuteilungsregeln für die drei Tarifstufen

```python
from pydantic_ai import Agent, RunContext
from pydantic_ai.capabilities import Capability, CombinedCapability, DynamicCapability, Thinking
from pydantic_ai_harness.planning import Planning

def check_order(order_id: str) -> str: ...      # Bestellung abfragen
def issue_refund(order_id: str, amount: float) -> str: ...   # Rückerstattung anstoßen
def deep_analyze(text: str) -> str: ...          # Tiefenanalyse

def 按套餐配发(ctx: RunContext[Tenant]):
    t = ctx.deps
    if t.tier == 'enterprise':
        return CombinedCapability([
            Capability(id='ent',
                       instructions=f'{t.name} 是企业客户，最高优先级，可深度分析',
                       tools=[check_order, issue_refund, deep_analyze]),
            Thinking(),      # Vertieftes Nachdenken
            Planning(),      # Aufgabenplanung (Harness-Capability)
        ], id='ent_bundle')
    if t.tier == 'pro':
        return CombinedCapability([
            Capability(id='pro', instructions='专业版客户，可查单可退款',
                       tools=[check_order, issue_refund]),
            Thinking(),
        ], id='pro_bundle')
    return Capability(id='free', instructions='免费版，只能查询订单',
                      tools=[check_order])

agent = Agent('test', name='support',
              deps_type=Tenant,
              output_type=Ticket,                          # ← Die Ausgabe muss diesem Vertrag entsprechen
              capabilities=[DynamicCapability(按套餐配发)])  # ← Zuteilung je nach Kunde

@agent.tool
def get_tenant_limit(ctx: RunContext[Tenant]) -> str:
    return f'退款上限 {ctx.deps.refund_limit}'    # Kommt aus dem privaten Kanal, die KI kann es nicht ändern
```

**Tatsächliches Laufergebnis** – ein und derselbe Agent, drei Mandanten, automatisch unterschiedliche Fähigkeiten:

```text
enterprise  A集团    → ['get_tenant_limit', 'check_order', 'issue_refund', 'deep_analyze', 'write_plan']
pro         B工作室  → ['get_tenant_limit', 'check_order', 'issue_refund']
free        小C     → ['get_tenant_limit', 'check_order']
```

Diese drei Ausgabezeilen machen die Entsprechung zwischen Geschäftslogik und technischer Umsetzung sehr deutlich:

| Tarif | Erhaltene Tools | Beschreibung |
|---|---|---|
| Enterprise | Bestellabfrage + Rückerstattung + **Tiefenanalyse** + **`write_plan`** | `write_plan` wird von der Capability `Planning()` eingespeist |
| Pro | Bestellabfrage + Rückerstattung | Ohne Tiefenanalyse |
| Free | **Nur Bestellabfrage** | Das Rückerstattungs-Tool bekommt es gar nicht erst zu sehen |

> 👉 **CEO-Perspektive**: **Ihre Preisliste lässt sich direkt in diesen Code übersetzen.** Was in welcher Stufe verkauft wird, wird in der Factory-Funktion als Capability-Karte zugeteilt. Eine Tarifstufe hinzufügen = einen `if`-Zweig hinzufügen, ohne den Agent selbst anzufassen. Noch wichtiger: **Die Margenstruktur wird direkt von diesem Code bestimmt** – Free-Nutzer laufen auf einem günstigen Modell mit wenigen Tools, Enterprise-Kunden auf einem teuren Modell mit vollem Funktionsumfang. Das ist der direkteste Kostenhebel eines KI-Produkts.

> 💡 **Achten Sie auf das entscheidende Detail bei der Free-Stufe**: Das Tool `issue_refund` **taucht in der Tool-Liste des Free-Nutzers überhaupt nicht auf**. Das ist kein „sag der KI, sie soll es nicht benutzen", sondern **sie sieht dieses Tool schlicht nicht**. Ersteres beruht auf der Selbstdisziplin des Prompts (unzuverlässig), Letzteres ist physische Trennung (zuverlässig). Beim Entwurf von Rechtekonzepten ist dieser Unterschied fundamental.

> ⚠️ **Fallstrick**: Die dynamische Zuteilung hat zwei praktische Einschränkungen. ① **Ressourcenintensive Capabilities müssen wiederverwendet werden** – Dinge wie `MCP`-Verbindungen oder Cloud-Sandboxes, die eine Verbindung aufbauen, dürfen nicht bei jedem Durchlauf in der Factory-Funktion neu erzeugt werden; legen Sie die Instanz außerhalb an und referenzieren Sie sie. ② **Die Factory-Funktion läuft bei jedem Run einmal**, sie muss also leichtgewichtig sein – keine Datenbankabfragen, keine API-Aufrufe darin; Mandanteninformationen gehören vorab in `deps`.

---

### Ebene 3: Den Massenprozess mit Pydantic Graph orchestrieren

Für ein einzelnes Ticket genügt der Agent. Aber sobald die Anforderung lautet **„eine Charge Tickets kommt herein, wird parallel klassifiziert, parallel verarbeitet und am Ende zusammengeführt"** und die Fachseite ein Ablaufdiagramm sehen will, ist der Zeitpunkt für Graph gekommen.

```python
from dataclasses import dataclass, field
from pydantic_graph import GraphBuilder, StepContext, reduce_list_append

@dataclass
class WorkState:                       # Der über den gesamten Ablauf geteilte Zustand
    log: list[str] = field(default_factory=list)

@dataclass
class WorkDeps:                        # Die über den gesamten Ablauf geteilten Dependencies
    auto_refund_ceiling: float

g = GraphBuilder(state_type=WorkState, deps_type=WorkDeps,
                 input_type=list[str], output_type=list[str])

@g.step
async def 分类(ctx: StepContext[WorkState, WorkDeps, list[str]]) -> list[Ticket]:
    out = []
    for raw in ctx.inputs:
        cat = '退款' if '退款' in raw else ('bug' if '报错' in raw else '咨询')
        out.append(Ticket(category=cat, summary=raw[:20], urgency=4 if cat=='退款' else 2))
    ctx.state.log.append(f'分类完成 {len(out)} 条')
    return out

@g.step
async def 处理(ctx: StepContext[WorkState, WorkDeps, Ticket]) -> str:
    t = ctx.inputs
    ctx.state.log.append(f'处理 {t.category}')
    if t.category == '退款':
        return f'[退款] {t.summary} → 走审批(上限{ctx.deps.auto_refund_ceiling})'
    if t.category == 'bug':
        return f'[缺陷] {t.summary} → 转研发'
    return f'[咨询] {t.summary} → 自动回复'

汇总 = g.join(reduce_list_append, initial_factory=list)

g.add(
    g.edge_from(g.start_node).to(分类),
    g.edge_from(分类).map().to(处理),      # Fan-out: jedes Ticket wird parallel verarbeitet
    g.edge_from(处理).to(汇总),            # Fan-in: Ergebnisse zusammenführen
    g.edge_from(汇总).to(g.end_node),
)
graph = g.build()
```

**Tatsächliches Laufergebnis**:

```text
[退款] 申请退款，重复扣款了 → 走审批(上限500)
[缺陷] 页面报错打不开 → 转研发
[咨询] 怎么改绑手机 → 自动回复

state.log: ['分类完成 3 条', '处理 退款', '处理 bug', '处理 咨询']
```

Und das Ablaufdiagramm wird **mit einer einzigen Zeile `graph.render()` automatisch erzeugt** (es muss nicht separat gezeichnet werden):

```text
---
title: 工单处理流程
---
stateDiagram-v2
  分类
  state map <<fork>>
  处理
  state reduce_list_append <<join>>

  [*] --> 分类
  分类 --> map
  map --> 处理
  处理 --> reduce_list_append
  reduce_list_append --> [*]
```

> 👉 **CEO-Perspektive**: Dieses Diagramm wird **automatisch aus dem Code erzeugt und stimmt daher immer mit der Implementierung überein**. Damit ist ein Ihnen nur allzu vertrautes Altproblem gelöst – **Ablaufdiagramm und tatsächliche Implementierung passen nicht zusammen**. Das im Anforderungsreview gezeichnete Diagramm hat sich drei Monate später längst vom Code entkoppelt; hier dagegen ist das Diagramm die Projektion des Codes, und ändert sich der Code, ändert sich das Diagramm automatisch mit. Werfen Sie die Ausgabe von `render()` in ein beliebiges Werkzeug mit Mermaid-Unterstützung (Notion, Feishu Docs, GitHub) und Sie sehen das Diagramm direkt.

> 💡 **`.map()` und `join` sind die Seele dieses Abschnitts**: `.map()` **zerlegt eine Liste in parallele Zweige** (3 Tickets werden gleichzeitig verarbeitet statt in einer Warteschlange), und `join` **führt die Ergebnisse wieder zu einer Liste zusammen**. In Produktsprache übersetzt heißt das „**parallele Massenverarbeitung + Ergebniskonsolidierung**".

---

### Wie die drei Ebenen zusammenspielen: ein Gesamtbild

```text
┌──────────────────────────────────────────────────────────────────────────────────┐
│  Ebene 3: Graph          分类 → [处理 parallel] → 汇总                           │
│  (Orchestrierung)        bestimmt "wie Schritte verkettet werden, wann parallel" │
└──────────────────────────┬───────────────────────────────────────────────────────┘
                           │ Innerhalb jedes Schritts aufrufbar
┌──────────────────────────┴───────────────────────────────────────────────────────┐
│  Ebene 2: Pydantic AI    Agent + Tools + deps + dynamische Capability-Karten     │
│  (KI-Fähigkeiten)        bestimmt "was die KI hier tun darf und für wen"         │
└──────────────────────────┬───────────────────────────────────────────────────────┘
                           │ Ein- und Ausgabe müssen konform sein
┌──────────────────────────┴───────────────────────────────────────────────────────┐
│  Ebene 1: Pydantic       Ticket-Vertrag: Typen + Constraints + Geschäftsregeln   │
│  (Datenvertrag)          bestimmt "welche Daten als gültig gelten"               │
└──────────────────────────────────────────────────────────────────────────────────┘
```

Die Arbeitsteilung der drei Ebenen in einem Satz:

> **Pydantic regelt „ob die Daten stimmen", Pydantic AI regelt „was die KI tun darf", Pydantic Graph regelt „wie der Ablauf verläuft".**

---

### Fünf Erkenntnisse, die man aus diesem Beispiel mitnehmen kann

Dieses Kapitel demonstriert nicht nur Code; wichtiger sind einige Beurteilungen, die sich in realen Projekten anwenden lassen:

**1. Strukturierte Ausgabe ist die Voraussetzung für die Anbindung an Geschäftssysteme.**
`output_type=Ticket` sorgt dafür, dass das Ergebnis der KI **direkt ins Ticketsystem laufen kann**, statt erst einen Fließtext auszuspucken, aus dem man dann per Regex die Felder herauskratzt. Das ist die Wasserscheide dafür, ob eine KI-Funktion wirklich ins Geschäft „andocken" kann.

**2. Rechtetrennung beruht auf „nicht zeigen", nicht auf „ermahnen".**
Free-Nutzer sehen das Tool `issue_refund` nicht, weil es ihnen schlicht nie zugeteilt wurde – nicht, weil ein Prompt sagt „benutze die Rückerstattungsfunktion nicht". **Fähigkeitsgrenzen müssen auf Framework-Ebene physisch getrennt sein.**

**3. Sensible Werte müssen über deps laufen.**
Rückerstattungslimits, Nutzeridentitäten, Datenbankverbindungen – alles, wo „ein Fehler der KI Schaden anrichtet", wird über `deps` injiziert, und das Modell kommt zu keinem Zeitpunkt daran.

**4. Die Preisliste lässt sich direkt in Zuteilungscode übersetzen.**
Das ist der größte Wert dieses Systems für SaaS-artige KI-Produkte: **kommerzielle Staffelung = Regeln der Capability-Zuteilung**, eins zu eins abgebildet, ohne die Geschäftslogik mit `if user.is_vip` zu übersäen.

**5. Ablaufdiagramme sollten aus dem Code erzeugt und nicht separat gezeichnet werden.**
`graph.render()` garantiert, dass Diagramm und Implementierung immer übereinstimmen, und beseitigt das Auseinanderlaufen von Dokumentation und Code an der Wurzel.

> 👉 **Die abschließende CEO-Perspektive**: Bis hierher sollten Sie in der Lage sein, Urteile dieser Art zu fällen – „Reicht für diese Anforderung eine Agent-Schleife, oder brauchen wir Graph?", „Für welche Tarifstufe gibt es diese Funktion, und wie trennen wir sie technisch?", „Soll die KI dieses Feld ausfüllen, oder muss es vom System geliefert werden?". **Diese Urteile sind mehr wert als die Fähigkeit, Code zu schreiben**, denn sie bestimmen die Zuverlässigkeitsgrenzen und die Kostenstruktur des Produkts.

---
