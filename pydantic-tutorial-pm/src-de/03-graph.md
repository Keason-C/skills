## Teil 3: Pydantic Graph — das Flussdiagramm wird zur lauffähigen Engine

> **Zielpublikum**: Sie haben bereits verstanden, was Pydantics `BaseModel` ist (Datenstrukturen als Klassen schreiben), und ebenso `Agent` / `Tools` / `Capabilities` aus Pydantic AI (einen Agenten, der Tools benutzen kann, sauber verpacken). Dieser Teil behandelt die **dritte Ebene**: Wenn ein Geschäftsprozess so komplex wird, dass die einzelne Schleife des Agenten — „denken → Tool aufrufen → wieder denken" — ihn nicht mehr fassen kann, brauchen Sie ein **explizites Flussdiagramm**.
>
> **Sämtlicher Code in diesem Text wurde real auf `pydantic-graph 2.17.0` + `pydantic-ai 2.17.0` ausgeführt und verifiziert.** Alle abgedruckten Ausgaben sind echte Laufzeitergebnisse, nichts davon ist von Hand geschrieben.

---

### 0. Drei Dinge vorab, damit Sie nicht in die Falle tappen

**Erstens: Diese Version wurde neu geschrieben, die Tutorials im Netz sind praktisch alle veraltet.**

`pydantic-graph` hat mit 2.x eine Architektur-Neufassung erfahren und dabei das **Builder-Muster** eingeführt. Wenn der Code, den Sie im Netz finden, so aussieht:

```python
# ❌ Das ist die alte Schreibweise, unter 2.17.0 läuft sie nicht
graph = Graph(nodes=[NodeA, NodeB])
graph.mermaid_code()
graph.next(node, persistence=...)
```

dann stammt er aus der alten Version. Die folgende Tabelle listet auf, was in dieser Version **entfernt wurde und auf keinen Fall mehr geschrieben werden darf**:

| Entferntes Element | Erläuterung | Ersatz |
|---|---|---|
| Das gesamte Modul `pydantic_graph.persistence` | Keine eingebaute Persistenz / kein Unterbrechen und Fortsetzen | Selbst bauen auf Basis von `iter()` + `override_next()`, oder die offizielle Durable-Execution-Lösung nutzen |
| Das gesamte Modul `pydantic_graph.mermaid` | Das Zeichenmodul ist weg | `Graph.render()` |
| `graph.mermaid_code()` / `mermaid_image()` / `mermaid_save()` | Alle drei Zeichenmethoden sind weg | `Graph.render()` |
| Direkte Konstruktion via `Graph(nodes=[A, B])` | Ein Graph lässt sich nicht mehr direkt instanziieren | `GraphBuilder(...)` → `.build()` |
| `graph.next(node, persistence=...)` | Es gibt keinen Parameter `persistence` mehr | `GraphRun.next()` / `GraphRun.override_next()` |
| `pydantic_graph.beta.*` | Der Namensraum `beta` ist weg | Alles wurde auf die oberste Ebene gezogen: `from pydantic_graph import GraphBuilder` |

Praktisch bestätigt:

```python
import importlib
for m in ['pydantic_graph.persistence', 'pydantic_graph.mermaid', 'pydantic_graph.beta']:
    try:
        importlib.import_module(m)
        print(m, '-> 存在')
    except ImportError as e:
        print(m, '-> 不存在:', e)
```

```text
pydantic_graph.persistence -> 不存在: No module named 'pydantic_graph.persistence'
pydantic_graph.mermaid -> 不存在: No module named 'pydantic_graph.mermaid'
pydantic_graph.beta -> 不存在: No module named 'pydantic_graph.beta'
```

**Zweitens: Die Entwickler selbst raten Ihnen, es zunächst nicht zu benutzen.**

Am Anfang der offiziellen Dokumentation `graph.md` steht eine sehr bekannte Warnung, im Original:

> "Don't use a nail gun unless you need a nail gun.
> If Pydantic AI agents are a hammer, and multi-agent workflows are a sledgehammer, then graphs are a nail gun:
> - sure, nail guns look cooler than hammers
> - but nail guns take a lot more setup than hammers
> - and nail guns don't make you a better builder, they make you a builder with a nail gun"
>
> Übersetzt: **Benutzen Sie keinen Nagler, nur um einen Nagler zu benutzen.** Ein Agent ist ein Hammer, die Zusammenarbeit mehrerer Agenten ist ein Vorschlaghammer, ein Graph ist ein Nagler. Nagler sehen tatsächlich cooler aus, aber sie erfordern erheblich mehr Vorbereitung — und sie machen Sie nicht zum besseren Handwerker, sondern nur zu einem Handwerker mit einem Nagler in der Hand.

Diese Passage ist für sich genommen bereits eine Auswahlempfehlung. In Abschnitt 9 gehe ich ausführlich darauf ein, wann der Einsatz sinnvoll ist.

**Drittens: Diese Bibliothek hängt nicht von pydantic-ai ab.**

Im offiziellen README heißt es wörtlich:

> "This library is developed as part of Pydantic AI, however it has **no dependency on `pydantic-ai`** or related packages and can be considered as a **pure graph-based state machine library**. You may find it useful whether or not you're using Pydantic AI or even building with GenAI."

Übersetzt: Dies ist eine **reine Graph- bzw. Zustandsautomaten-Bibliothek**. Sie ist bei der Arbeit an Pydantic AI gewissermaßen nebenbei entstanden, hat mit LLMs aber nicht das Geringste zu tun — Sie können damit ohne Weiteres einen rein CRUD-basierten Bestellprozess orchestrieren.

> 👉 **CEO-Perspektive**: Stellen Sie es sich als **Open-Source-Workflow-Engine in Codeform** vor (vergleichbar mit Camunda, Airflow oder der Schicht hinter einem Genehmigungsworkflow), nur dass die Prozessdefinition kein zusammengeklicktes XML/JSON ist, sondern Python-Typannotationen. Das Swimlane-Diagramm, das Sie in Ihrem PRD gezeichnet haben, lässt sich fast eins zu eins in Code dieser Bibliothek übersetzen.

**Viertens: Alle Code-Fragmente dieses Kapitels, in denen `await` oder `async for` vorkommt, müssen in einer asynchronen Funktion ausgeführt werden.**

Um das Wesentliche hervorzuheben, zeigen manche Code-Fragmente in diesem Kapitel nur die entscheidenden Zeilen. Überall dort, wo `await xxx` oder `async for ... in ...` auftaucht, führt **ein direktes Kopieren in eine `.py`-Datei zu einem `SyntaxError`** — Python erlaubt `await` nicht auf der äußersten Dateiebene. Richtig ist, eine Hülle darumzulegen:

```python
import asyncio

async def main():
    result = await graph.run(inputs=...)      # ← der await-Code aus dem Fragment kommt hierhin
    print(result)
    # Für async-for-Fragmente gilt dasselbe: ebenfalls in diese Funktion

asyncio.run(main())                            # ← damit wird gestartet
```

> ⚠️ **Fallstrick**: Umgekehrt gilt: **`graph.run_sync()` darf nicht in ein `async def` gepackt werden** — es startet intern selbst eine Event-Loop, und in einer async-Funktion läuft bereits eine, was direkt zu einem Fehler führt. Als Merksatz: **In synchroner Umgebung `run_sync()`, in asynchroner Umgebung `await run()` — beides lässt sich nicht mischen.** Die real gemessene Fehlermeldung finden Sie in Abschnitt 2.4.

---

## 1. Architekturüberblick

### 1.1 Welches Problem es löst: wenn die einzelne Agenten-Schleife nicht mehr ausreicht

Erinnern Sie sich an den Agenten aus Teil 2. Das Ausführungsmodell eines Agenten ist im Kern eine **feste Schleife**:

```text
用户输入 → 请求模型 → 模型说"我要调工具" → 调工具 → 把结果塞回去 → 再请求模型 → ...
                                 ↓
                          模型说"我说完了" → 结束
```

Diese Schleife hat eine Besonderheit: **Was als Nächstes geschieht, entscheidet das Modell selbst.** Das ist außerordentlich flexibel, bedeutet aber auch:

| Was Sie wollen | Kann die Agenten-Schleife das liefern? |
|---|---|
| „Erst Bestand prüfen, dann abbuchen, zuletzt versenden" — streng in dieser Reihenfolge | ❌ Das Modell kann die Reihenfolge vertauschen oder Schritte auslassen |
| „Drei Lieferanten geben gleichzeitig ein Angebot ab, es zählt, wer zuerst antwortet" | ❌ In einer einzelnen Schleife ist echte Parallelität nicht möglich |
| „Beträge über 10.000 müssen zwingend zur Freigabe an die Bereichsleitung" | ❌ Das Modell lässt sich durch geschickte Formulierungen umlenken |
| „Wenn Schritt 3 fehlschlägt, automatisch an einen Menschen übergeben, kein Retry" | ❌ Fehlerbehandlung ist über die einzelnen Tools verstreut |
| „Den gesamten Prozess für die Fachabteilung visualisieren" | ❌ Eine Schleife hat keine Form, sie lässt sich nicht zeichnen |

Genau diese Klasse von Problemen löst `pydantic-graph`: **wenn die Entscheidung über den nächsten Schritt bei Ihnen (Produkt/Engineering) liegen soll und nicht beim Modell.**

> 👉 **CEO-Perspektive**: Hier verläuft die Trennlinie zwischen „die KI darf frei agieren" und „strikte SOP-Bindung".
> - Kundenservice-Dialoge, Textentwürfe, Recherche → dem Agenten freie Hand lassen
> - Erstattungsfreigaben, Kreditvergabe unter Risikokontrolle, Auftragserfüllung → müssen zwingend über einen Graphen laufen; jeder Schritt muss auditierbar, nachvollziehbar und der Compliance vorzeigbar sein
>
> Ein noch praktischeres Kriterium: **Wenn jemand den Kopf hinhalten muss, falls dieser Prozess scheitert, dann nehmen Sie einen Graphen.**

### 1.2 Panorama der Kernkonzepte (erst einmal die Liste, danach einzeln erklärt)

Mehr Konzepte als diese hat die Bibliothek nicht — schauen Sie sie sich zunächst nur oberflächlich an:

| Konzept | Python-Name | In einem Satz | Lebenszyklus |
|---|---|---|---|
| Builder | `GraphBuilder` | Damit „zeichnen" Sie den Graphen | Bauzeit (beim Prozessstart) |
| Kompilierter Graph | `Graph` | Ergebnis von `builder.build()`, unveränderlich, wiederverwendbar | Bauzeit → langlebig |
| Eine Ausführung | `GraphRun` | Der Kontext eines einzelnen Durchlaufs, erzeugt von `graph.iter()` | Laufzeit (einer pro Anfrage) |
| Schritt (funktional) | `Step` / `@g.step` | Eine async-Funktion ist ein Knoten | Definition zur Bauzeit |
| Schritt (deklarativ) | Unterklasse von `BaseNode` | Eine dataclass + `run()` ist ein Knoten | Definition zur Bauzeit |
| Streaming-Schritt | `@g.stream` | Ein async-Generator-Knoten, der während der Erzeugung schon ausliefert | Definition zur Bauzeit |
| Start / Ende | `StartNode` / `EndNode` | Ein- und Ausgang des Graphen, `g.start_node` / `g.end_node` | Eingebaut |
| Abschlusssignal | `End` | `return End(x)` in einem Knoten beendet den gesamten Graphen | Laufzeit |
| Verzweigung | `Decision` / `g.decision()` | Die grafische Fassung von if-elif-else | Definition zur Bauzeit |
| Verzweigungsbedingung | `g.match()` / `g.match_node()` | Ein einzelner `case`-Zweig | Definition zur Bauzeit |
| Fan-out | `Fork` (erzeugt durch `.map()` / `.broadcast()`) | Aus eins wird viel, parallel | Automatisch erzeugt |
| Fan-in | `Join` / `g.join(reducer)` | Aus viel wird eins, Zusammenführung | Definition zur Bauzeit |
| Zusammenführungsfunktion | `ReducerFunction` | Sagt dem Join, wie Ergebnisse zu kombinieren sind | Definition zur Bauzeit |
| Zustand | `StateT` | Die veränderlichen Daten, die der gesamte Prozess teilt (Bestellung, Antragsformular) | Laufzeit, eine Kopie pro Run |
| Abhängigkeiten | `DepsT` | Injizierte externe Ressourcen (Datenbank, API-Client) | Laufzeit, bei jedem Run übergeben |
| Schritt-Kontext | `StepContext` | Das `ctx`, das `@g.step` erhält, mit `.state/.deps/.inputs` | Laufzeit |
| Knoten-Kontext | `GraphRunContext` | Das `ctx`, das `BaseNode.run()` erhält, nur mit `.state/.deps` | Laufzeit |
| Fehlermarkierung | `ErrorMarker` | Der Umschlag bei einer Ausnahme im Knoten, erlaubt Ihnen die Übernahme | Laufzeit |
| Endmarkierung | `EndMarker` | Der Umschlag nach vollständigem Durchlauf, enthält die finale Ausgabe | Laufzeit |

Mit `python -c "import pydantic_graph; print(pydantic_graph.__all__)"` sehen Sie die vollständige Exportliste:

```text
('BaseNode', 'End', 'GraphRunContext', 'Edge', 'GraphBuilder', 'Graph', 'GraphRun',
 'GraphTask', 'GraphTaskRequest', 'EndMarker', 'ErrorMarker', 'JoinItem', 'Step',
 'StepContext', 'StepNode', 'StartNode', 'EndNode', 'Fork', 'Decision', 'Join',
 'JoinNode', 'ReducerContext', 'ReducerFunction', 'ReduceFirstValue',
 'reduce_dict_update', 'reduce_list_append', 'reduce_list_extend', 'reduce_null',
 'reduce_sum', 'TypeExpression', 'GraphSetupError', 'GraphRuntimeError')
```

### 1.3 ASCII-Architekturdiagramm

```text
┌──────────────────────────────────────────────────────────────────────────┐
│  构建期（进程启动时跑一次，之后不再变）                                     │
│                                                                          │
│    GraphBuilder(state_type=…, deps_type=…, input_type=…, output_type=…)  │
│         │                                                                │
│         ├── @g.step      函数式节点      ──┐                              │
│         ├── @g.stream    流式节点        ──┤                              │
│         ├── g.node(X)    声明式 BaseNode ──┼─→ 节点集合                    │
│         ├── g.join(f)    汇总节点        ──┤                              │
│         └── g.decision() 分支节点        ──┘                              │
│                                                                          │
│    g.add(                                                                │
│      g.edge_from(A).to(B),              ← 显式连线                        │
│      g.edge_from(A).map().to(B),        ← 扇出                            │
│      g.edge_from(A).to(B, C, D),        ← 广播                            │
│      g.edge_from(A).to(g.decision()…),  ← 分支                            │
│      g.node(SomeBaseNode),              ← 连线由返回类型注解自动推导 ★     │
│    )                                                                     │
│         │                                                                │
│         ▼                                                                │
│    g.build()   ── 校验结构 / 展平路径 / 归一化 fork / 计算 join 的父 fork   │
│         │                                                                │
│         ▼                                                                │
│  ┌───────────────────────────────────────────────────────────────┐       │
│  │  Graph（不可变，线程安全，可以放在模块级全局变量里复用）          │       │
│  │    .run(state=, deps=, inputs=)      → 跑完拿结果               │       │
│  │    .run_sync(...)                     → 同上，同步版本           │       │
│  │    .iter(...)                         → 逐步执行，能插手         │       │
│  │    .render(title=, direction=)        → 输出 mermaid 源码        │       │
│  └───────────────────────────────────────────────────────────────┘       │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  运行期（每次业务请求一份）                                                │
│                                                                          │
│    GraphRun                                                              │
│      .state    ← 这次跑的可变状态（订单对象）                              │
│      .deps     ← 这次跑注入的资源（DB 连接）                               │
│      .next_task    ← 下一步要跑什么（可以偷看）                            │
│      .output       ← 跑完了没有，输出是啥                                  │
│      .next()       ← 手动推进一步                                          │
│      .override_next()  ← 改写下一步（人工干预 / 错误恢复）★                 │
│                                                                          │
│    执行调度器内部：                                                        │
│      active_tasks      正在跑的任务（并行时有多个）                        │
│      active_reducers   正在累积的 Join 状态                                │
│      fork_stack        每个任务属于哪次 fork（用来判断 join 什么时候满）    │
└──────────────────────────────────────────────────────────────────────────┘
```

> 👉 **CEO-Perspektive**: Diese Trennung von „Bauzeit / Laufzeit" entspricht der Unterscheidung zwischen **Prozessvorlage** und **Prozessinstanz**.
> - `Graph` = die Vorlage „Freigabeprozess für Spesenabrechnungen", die Sie einmal im Backend konfiguriert haben und die das ganze Unternehmen nutzt
> - `GraphRun` = die konkrete Spesenabrechnung, die Herr Wang heute eingereicht hat, mit ihrem eigenen Fortschritt, unabhängig von allen anderen
>
> Das entspricht exakt dem Modell gängiger Freigabe-Workflows.

### 1.4 Das eigenwilligste Designmerkmal: Kanten werden aus den Rückgabetyp-Annotationen abgeleitet

Das ist der Punkt, an dem sich `pydantic-graph` von allen anderen Workflow-Engines am Markt unterscheidet, und er **muss vollständig verstanden sein**.

Im offiziellen README wörtlich:

> "`pydantic-graph` allows you to define graphs using standard Python syntax. In particular, **edges are defined using the return type hint of nodes**."

Das heißt: **Die Verbindungen zwischen den Knoten ziehen Sie nicht von Hand, sie werden aus den Rückgabetyp-Annotationen der Funktionen ausgelesen.**

Sehen Sie sich diesen Code an:

```python
@dataclass
class DivisibleBy5(BaseNode[None, None, int]):
    foo: int

    async def run(self, ctx: GraphRunContext) -> Increment | End[int]:
        #                                        ^^^^^^^^^^^^^^^^^^^^
        #                                        Genau diese Zeile ist die „Verbindung"
        if self.foo % 5 == 0:
            return End(self.foo)
        else:
            return Increment(self.foo)
```

Dieses `-> Increment | End[int]` ist nicht bloß ein Kommentar für den Typprüfer. `pydantic-graph` **liest es beim `build()` mittels `get_type_hints()` aus** und tut dann Folgendes:

- Sieht es `Increment` → zeichnet eine Kante `DivisibleBy5 ──→ Increment`
- Sieht es `End[int]` → zeichnet eine Kante `DivisibleBy5 ──→ [Endpunkt]`
- Da es zwei Ziele gibt → wird automatisch ein rautenförmiger **Decision-Knoten (Entscheidung)** eingefügt

Diese wenigen Codezeilen ergeben also gezeichnet:

```text
  DivisibleBy5 --> decision
  decision --> Increment
  decision --> [*]
```

**Drei Konsequenzen dieses Designs:**

| Konsequenz | Vorteil | Preis |
|---|---|---|
| Flussdiagramm und Code sind immer deckungsgleich | „Das Diagramm wurde geändert, der Code nicht" kann nicht mehr vorkommen | Prozessänderungen erfordern Änderungen an den Typannotationen |
| Der Typprüfer findet Prozessfehler für Sie | Geben Sie einen Knoten zurück, der nicht in der Annotation steht, meldet mypy/pyright das sofort | Annotationen müssen vollständig sein, ein bequemes `-> Any` ist nicht drin |
| Der Graph lässt sich automatisch zeichnen | `render()` liefert direkt Mermaid | Ist die Annotation falsch, ist auch das Diagramm falsch |

> 👉 **CEO-Perspektive**: Damit ist der klassischste Schmerzpunkt aller Workflow-Engines gelöst — **Flussdiagramm und tatsächlicher Code passen nicht zusammen**.
>
> Traditionell läuft es so: Der CEO zeichnet ein Diagramm in Visio, die Entwickler schreiben den Code danach, drei Monate später wurde der Code fünfmal geändert, und das Diagramm liegt unverändert in Confluence — niemand traut ihm noch.
>
> Hier gilt: **Das Diagramm ist der Code selbst.** Ändert ein Entwickler die Zeile `-> Increment | End[int]`, ändert sich das von `render()` erzeugte Diagramm sofort mit. Sie können sich jederzeit von einem Entwickler ein `print(graph.render())` ausführen lassen und das Ergebnis in ein beliebiges Mermaid-fähiges Werkzeug werfen (Dokumentenwerkzeuge, Notion, GitHub) — was Sie sehen, ist der Prozess, der aktuell tatsächlich in Produktion läuft.

**⚠️ Diese Ableitung greift allerdings nur bei `BaseNode` vollständig, bei `@g.step` nur teilweise.** Das ist ein realer Fallstrick, den ich in Abschnitt 3 und 5 gesondert ausführe; halten Sie hier zunächst das Ergebnis fest:

| Schreibweise des Knotens | Rückgabe eines einzelnen Knotentyps | Rückgabe einer Union mehrerer Knotentypen |
|---|---|---|
| `BaseNode` + `g.node(X)` | ✅ Automatische Verbindung | ✅ Erzeugt automatisch eine Decision, die zur Laufzeit anhand der **Klasse des tatsächlich zurückgegebenen Objekts** verzweigt |
| `@g.step` | ✅ Automatische Verbindung | ⚠️ Erzeugt eine Decision, die zur Laufzeit **zwangsläufig einen Fehler wirft** und umgangen werden muss |

### 1.5 Zwei Wege, einen Graphen zu bauen

Die Bibliothek bietet zwei Syntaxvarianten für Knoten, die sich **mischen lassen**:

```text
路线 A：函数式（builder 风格）              路线 B：声明式（面向对象风格）
────────────────────────────              ────────────────────────────
@g.step                                   @dataclass
async def check_stock(ctx) -> int:        class CheckStock(BaseNode[S, D, R]):
    return ctx.inputs                         order_id: int
                                              async def run(self, ctx) -> Charge:
连线：g.edge_from(A).to(B) 手动写               return Charge(self.order_id)

上下文：StepContext                        连线：写在 -> 返回注解里，g.node() 注册
  .state / .deps / .inputs                上下文：GraphRunContext
                                            .state / .deps（没有 .inputs）
数据怎么传：通过边传递                       数据怎么传：塞进下一个节点的构造参数
```

Abschnitt 3 vergleicht beides im Detail.

---

## 2. Das kleinste lauffähige Beispiel: von 4 bis 5 zählen

Dies ist das Beispiel aus dem offiziellen README, ich habe es vollständig durchlaufen lassen. Die Funktion ist ausgesprochen banal (von einer Zahl aus so lange 1 addieren, bis sie durch 5 teilbar ist), aber sie **nutzt sämtliche Kernkonzepte**: Startpunkt, funktionaler Step, deklarative BaseNode, Verzweigung, Schleife, Endpunkt.

### 2.1 Vollständiger Code

```python
from __future__ import annotations

from dataclasses import dataclass

from pydantic_graph import BaseNode, End, GraphBuilder, GraphRunContext, StepContext


@dataclass
class DivisibleBy5(BaseNode[None, None, int]):
    foo: int

    async def run(self, ctx: GraphRunContext) -> Increment | End[int]:
        if self.foo % 5 == 0:
            return End(self.foo)
        else:
            return Increment(self.foo)


@dataclass
class Increment(BaseNode):
    foo: int

    async def run(self, ctx: GraphRunContext) -> DivisibleBy5:
        return DivisibleBy5(self.foo + 1)


g = GraphBuilder(input_type=int, output_type=int)


@g.step
async def start(ctx: StepContext[None, None, int]) -> DivisibleBy5:
    return DivisibleBy5(ctx.inputs)


g.add(
    g.node(DivisibleBy5),
    g.node(Increment),
    g.edge_from(g.start_node).to(start),
)

fives_graph = g.build()


async def main():
    result = await fives_graph.run(inputs=4)
    print(result)
```

Reale Ausgabe:

```text
5
```

Noch einmal ausgeführt mit `fives_graph.run_sync(inputs=12)`:

```text
15
```

(12 → 13 → 14 → 15; 15 ist durch 5 teilbar, also Ende.)

### 2.2 Zeile für Zeile aufgeschlüsselt

| Zeile | Code | Was passiert | Warum so geschrieben |
|---|---|---|---|
| 1 | `from __future__ import annotations` | Macht alle Typannotationen zu „verzögert ausgewerteten" Zeichenketten | **Zwingend erforderlich**. Denn die Rückgabeannotation von `DivisibleBy5` verweist auf `Increment`, das erst darunter definiert wird. Ohne diese Zeile wirft Python bereits bei der Definition von `DivisibleBy5` einen `NameError` |
| 2 | `@dataclass class DivisibleBy5(BaseNode[None, None, int])` | Definiert einen deklarativen Knoten | Die drei Generics sind der Reihe nach: **State-Typ** (hier kein Zustand, `None`), **Deps-Typ** (keine Abhängigkeiten, `None`) und **der Typ von `x`, falls dieser Knoten `return End(x)` ausführt** (`int`) |
| 3 | `foo: int` | Die Eingabedaten des Knotens | Die Felder der dataclass sind die „Parameter" des Knotens. Der vorgelagerte Knoten reicht die Daten über `DivisibleBy5(irgendein Wert)` herein |
| 4 | `async def run(self, ctx: GraphRunContext) -> Increment \| End[int]` | Die Geschäftslogik des Knotens + **Definition der ausgehenden Kanten** | Die Rückgabeannotation liest sich als: „Dieser Knoten geht entweder zu `Increment` oder beendet den gesamten Graphen und liefert ein int" |
| 5 | `class Increment(BaseNode)` | Der zweite Knoten, alle Generics weggelassen | Alle drei Generics von `BaseNode` haben Standardwerte. Dieser Knoten braucht weder Zustand noch Abhängigkeiten und führt auch kein `return End(...)` aus, also lassen sich alle drei weglassen |
| 6 | `g = GraphBuilder(input_type=int, output_type=int)` | Erzeugt den Builder | Erklärt: „Der gesamte Graph nimmt ein int entgegen und liefert am Ende ein int" |
| 7 | `@g.step async def start(ctx: StepContext[None, None, int]) -> DivisibleBy5` | Ein funktionaler Knoten | Die drei Generics von `StepContext` sind **State / Deps / Eingabetyp dieses Steps**. Seine Aufgabe besteht darin, die Rohdaten des Graphen `ctx.inputs` (ein nacktes int) in den ersten `BaseNode` zu verpacken |
| 8 | `g.node(DivisibleBy5)` | Registriert die BaseNode im Graphen | **Gleichzeitig** mit der Registrierung wird die Rückgabeannotation von `run()` gelesen und die ausgehende Kante automatisch angelegt. Dieser Schritt ist „Registrierung + Verbindung" in einem |
| 9 | `g.edge_from(g.start_node).to(start)` | Zieht eine Kante von Hand | Vom Eingang des Graphen zum Step `start`. `g.start_node` ist der eingebaute virtuelle Startpunkt |
| 10 | `g.build()` | Kompilieren | Prüft die Struktur (etwa auf isolierte Knoten), flacht Pfade ab, berechnet Fork-/Join-Beziehungen und liefert einen unveränderlichen `Graph` |
| 11 | `await fives_graph.run(inputs=4)` | Ausführen | Der Rückgabewert ist genau das `x` aus `End(x)` |

**Warum braucht es den Step `start`?**

Weil die Eingabe des Graphen ein nacktes `int` (4) ist, im Graphen aber `BaseNode`-Objekte zirkulieren. `start` ist ein Adapter und dafür zuständig, die `4` in ein `DivisibleBy5(4)` zu verpacken.

**Warum muss für `Increment` keine ausgehende Kante registriert werden?**

Sie wurde registriert — `g.node(Increment)` liest die Rückgabeannotation `-> DivisibleBy5` (ein einzelner Typ) und zeichnet daraufhin automatisch eine Kante `Increment ──→ DivisibleBy5`. Diese Kante bildet die **Schleife**.

### 2.3 Wie das gezeichnet aussieht

Die echte Ausgabe von `print(fives_graph.render())`:

```text
stateDiagram-v2
  start
  DivisibleBy5
  state decision <<choice>>
  Increment

  [*] --> start
  start --> DivisibleBy5
  DivisibleBy5 --> decision
  decision --> Increment
  decision --> [*]
  Increment --> DivisibleBy5
```

So liest man es:

- `[*]` ist Start- bzw. Endpunkt
- `state decision <<choice>>` ist der rautenförmige Entscheidungsknoten (**Sie haben ihn nicht geschrieben, er wurde automatisch aus `-> Increment | End[int]` erzeugt**)
- Die Kante `Increment --> DivisibleBy5` bildet den Rückweg der Schleife

Fügen Sie diesen Text in einen beliebigen Mermaid-fähigen Editor ein, und Sie sehen das Diagramm.

> 👉 **CEO-Perspektive**: Achten Sie auf die Kausalität. Der Entwickler hat kein Diagramm gezeichnet, er hat lediglich Geschäftslogik und Typannotationen geschrieben — das Diagramm ist ein **Nebenprodukt**. Das bedeutet, die Pflegekosten des Flussdiagramms liegen bei **null**: Es kann gar nicht veralten, weil es aus dem laufenden Code erzeugt wird.
>
> Sie können vom Team verlangen, das Ergebnis von `print(graph.render())` in die CI einzubauen, sodass bei jedem PR das Flussdiagramm in der Dokumentation automatisch aktualisiert wird. Die Prüfung von Prozessänderungen hat damit von nun an eine belastbare Grundlage.

### 2.4 Drei Einstiegspunkte für die Ausführung

Auf `Graph` gibt es nur diese wenigen öffentlichen Methoden:

```python
from pydantic_graph import Graph
print([a for a in dir(Graph) if not a.startswith('_')])
```

```text
['get_parent_fork', 'is_final_join', 'iter', 'render', 'run', 'run_sync']
```

| Methode | Verwendung | Zu beachten |
|---|---|---|
| `await graph.run(state=, deps=, inputs=)` | Durchlaufen und Ergebnis abholen, **am häufigsten genutzt** | Asynchron |
| `graph.run_sync(state=, deps=, inputs=)` | Dasselbe, synchrone Variante | ⚠️ **Darf nicht in einer async-Umgebung aufgerufen werden** |
| `async with graph.iter(...) as run:` | Schrittweise Ausführung, beobachtbar und beeinflussbar | Ausführlich in Abschnitt 6 |
| `graph.render(title=, direction=)` | Liefert Mermaid-Quelltext | Ausführlich in Abschnitt 7 |

> ⚠️ **Fallstrick**: `run_sync` ist intern ein `loop.run_until_complete(...)`; wird es an einer Stelle aufgerufen, an der bereits eine Event-Loop läuft, fliegt es sofort auseinander. Praktisch gemessen:
>
> ```python
> async def main():
>     graph.run_sync()   # run_sync innerhalb einer async-Funktion aufgerufen
> asyncio.run(main())
> ```
> ```text
> RuntimeError : This event loop is already running
> ```
>
> Die Regel ist einfach: **Innerhalb von `async def` immer `await graph.run(...)`; `run_sync` nur auf oberster Skriptebene bzw. in synchronem Code.**


---

## 3. Zwei Arten, Knoten zu schreiben

Dieser Abschnitt erklärt `@g.step` (funktional) und `BaseNode` (deklarativ) getrennt voneinander, denn **die falsche Wahl tut weh**.

Zunächst die Punkte, die dieser Abschnitt abdeckt:

1. Die Schreibweise von `@g.step` und `StepContext`
2. Die Schreibweise von `BaseNode` und `GraphRunContext`
3. Die vollständige Vergleichstabelle
4. Wie sich beides mischen lässt (`as_node()` + `Annotated`)
5. Streaming-Knoten mit `@g.stream`
6. `node_id` und `label` eines Knotens
7. ⚠️ Ein realer Fallstrick: Ein Step, der eine Union von BaseNodes zurückgibt, fliegt auseinander

### 3.1 `@g.step`: funktional

Die einfachste Form — eine async-Funktion ist ein Knoten:

```python
import asyncio
from dataclasses import dataclass
from pydantic_graph import GraphBuilder, StepContext


@dataclass
class OrderState:
    log: list[str]


g = GraphBuilder(state_type=OrderState, input_type=int, output_type=str)


@g.step
async def check_stock(ctx: StepContext[OrderState, None, int]) -> int:
    ctx.state.log.append(f'查库存: 订单 {ctx.inputs}')
    return ctx.inputs


@g.step
async def charge(ctx: StepContext[OrderState, None, int]) -> str:
    ctx.state.log.append(f'扣款: 订单 {ctx.inputs}')
    return f'订单 {ctx.inputs} 已完成'


g.add(
    g.edge_from(g.start_node).to(check_stock),
    g.edge_from(check_stock).to(charge),
    g.edge_from(charge).to(g.end_node),
)

order_graph = g.build()


async def main():
    state = OrderState(log=[])
    result = await order_graph.run(state=state, inputs=1001)
    print(result)
    print(state.log)
```

Reale Ausgabe:

```text
订单 1001 已完成
['查库存: 订单 1001', '扣款: 订单 1001']
```

Ausgabe von `render()`:

```text
stateDiagram-v2
  check_stock
  charge

  [*] --> check_stock
  check_stock --> charge
  charge --> [*]
```

**Die entscheidenden Punkte:**

| Punkt | Erläuterung |
|---|---|
| `ctx` ist ein `StepContext[State, Deps, Input]` | Die drei Generics sind der Reihe nach: Zustandstyp des Graphen, Abhängigkeitstyp des Graphen, **Eingabetyp dieses konkreten Steps** |
| `ctx.inputs` | Die vom vorgelagerten Knoten übergebenen Daten. Das gibt es nur bei `@g.step` |
| Rückgabewert | Gibt direkt die Geschäftsdaten zurück (`int`, `str`, `dict` …), die entlang der von Ihnen manuell gezogenen Kante zum nächsten Knoten fließen |
| Kanten müssen von Hand gezogen werden | `g.edge_from(A).to(B)` |
| Knoten-ID | Standardmäßig der Funktionsname (`check_stock`, `charge`) |

> 👉 **CEO-Perspektive**: Die funktionale Schreibweise eignet sich für **Fließband-Prozesse** — jeder Schritt nimmt die Ausgabe des vorherigen auf und reicht sie weiter. Wie ein Fertigungsband: Das Halbfertigprodukt des vorherigen Arbeitsgangs wandert direkt zur nächsten Station. Die Daten fließen **auf den Kanten**.

### 3.2 `BaseNode`: deklarativ

```python
from __future__ import annotations
from dataclasses import dataclass
from pydantic_graph import BaseNode, End, GraphRunContext


@dataclass
class Triage(BaseNode[TicketState, None, str]):
    ticket: str          # ← die Daten, die der Knoten selbst mitbringt

    async def run(self, ctx: GraphRunContext[TicketState, None]) -> Escalate | End[str]:
        ctx.state.trail.append('分诊')
        if '崩溃' in self.ticket:
            return Escalate(self.ticket)      # ← Daten in die Konstruktorparameter des nächsten Knotens stecken
        return End('工单已关闭')
```

**Die entscheidenden Punkte:**

| Punkt | Erläuterung |
|---|---|
| Die drei Generics `BaseNode[StateT, DepsT, RunEndT]` | Zustandstyp, Abhängigkeitstyp, **und — falls dieser Knoten `return End(x)` ausführt — der Typ von `x`**. Alle haben Standardwerte und können weggelassen werden, wenn sie nicht gebraucht werden |
| `ctx` ist ein `GraphRunContext[State, Deps]` | **Nur zwei Generics, kein inputs!** |
| Wie Daten übergeben werden | Über dataclass-Felder. Der vorgelagerte Knoten macht `return Escalate(self.ticket)`, die Daten stecken **in den Konstruktorparametern** |
| Wie Kanten definiert werden | In der Rückgabeannotation von `run()`; bei der Registrierung mit `g.node(Triage)` werden sie automatisch ausgelesen |
| Knoten-ID | Standardmäßig der Klassenname (`Triage`), geliefert von `BaseNode.get_node_id()` als `cls.__name__` |

> 👉 **CEO-Perspektive**: Die deklarative Schreibweise eignet sich für **Zustandsautomaten-Prozesse** — „aktuell im Zustand ‚wartet auf Freigabe', als Nächstes möglicherweise ‚genehmigt' oder ‚abgelehnt'". Die Daten stecken **in den Knoten**, die Kanten sind lediglich Zustandsübergänge. So, als wandere der Antrag selbst durch die Instanzen und bekomme an jeder Station einen Stempel.

### 3.3 Vollständige Vergleichstabelle

| Dimension | `@g.step` funktional | `BaseNode` deklarativ |
|---|---|---|
| Definitionsweise | `@g.step` dekoriert eine async-Funktion | `@dataclass` + Ableitung von `BaseNode` + Implementierung von `run()` |
| Kontexttyp | `StepContext[StateT, DepsT, InputT]` | `GraphRunContext[StateT, DepsT]` |
| Zugriff auf `ctx.state` | ✅ | ✅ |
| Zugriff auf `ctx.deps` | ✅ | ✅ |
| Zugriff auf `ctx.inputs` | ✅ | ❌ **Nicht vorhanden**, die Daten liegen in den Feldern `self.xxx` |
| Art der Datenübergabe | Über die Kante (Rückgabewert → `ctx.inputs` des nächsten Knotens) | Über die Konstruktorparameter des Knotens (`return NextNode(data)`) |
| Wie ausgehende Kanten festgelegt werden | Manuell mit `g.edge_from(A).to(B)` | Automatisch aus der Rückgabeannotation von `run()` abgeleitet |
| Registrierungsweise | Wird automatisch registriert, sobald `g.add(g.edge_from(...))` darauf verweist | Explizit über `g.node(X)` |
| Mehrere mögliche Nachfolger | ⚠️ Erfordert ein explizites `g.decision()` (siehe Fallstrick in 3.7) | ✅ Es genügt, eine Union in die Rückgabeannotation zu schreiben |
| Beenden des gesamten Graphen | Verbindung zu `g.end_node` | `return End(x)` |
| Unterstützung für `.map()` / `.broadcast()` / `.transform()` | ✅ Alle Kantenoperationen werden unterstützt | Kanten entstehen aus der Ableitung, Kantenoperationen sind unbequem |
| Streaming-Unterstützung (`@g.stream`) | ✅ | ❌ |
| Standard-Knoten-ID | Funktionsname | Klassenname |
| Passende Einsatzszenarien | Datenverarbeitungs-Pipelines, paralleles map/reduce, ETL | Zustandsautomaten, Freigabeprozesse, Abläufe mit klarem „Zustands"-Begriff |
| Mentales Modell | „Funktionskomposition" | „Zustandsübergang" |

**Wie wählt man? In einem Satz:**

- Wenn jeder Schritt des Prozesses **dieselben Daten weiterverarbeitet** → `@g.step`
- Wenn der Prozess einen klaren **Zustands**begriff hat (wartet auf Freigabe / genehmigt / abgelehnt) → `BaseNode`
- **Im Zweifelsfall `@g.step`**: einfacher, und alle fortgeschrittenen Kantenoperationen wie Parallelität, Verzweigung und Transformation liegen auf dieser Seite

### 3.4 Mischen: `as_node()` + `Annotated`

Beides lässt sich im selben Graphen kombinieren. Eine Richtung haben wir bereits gesehen: Ein `@g.step` gibt einen `BaseNode` zurück (genau das tut `start` im README).

Die Gegenrichtung — ein `BaseNode` soll zu einem `@g.step` springen — erfordert `step.as_node(daten)`, und die Rückgabeannotation muss als `Annotated[StepNode[StateT, DepsT], derBetreffendeStep]` geschrieben werden:

```python
from __future__ import annotations
import asyncio
from dataclasses import dataclass
from typing import Annotated
from pydantic_graph import (
    BaseNode, End, GraphBuilder, GraphRunContext, StepContext, StepNode,
)


@dataclass
class TicketState:
    trail: list[str]


g = GraphBuilder(state_type=TicketState, input_type=str, output_type=str)


# funktionaler Step
@g.step
async def close_ticket(ctx: StepContext[TicketState, None, str]) -> str:
    ctx.state.trail.append('关单')
    return f'工单 {ctx.inputs} 已关闭'


# deklarativer BaseNode; kann zu Escalate (einem weiteren BaseNode) oder zu close_ticket (einem Step) springen
@dataclass
class Triage(BaseNode[TicketState, None, str]):
    ticket: str

    async def run(
        self, ctx: GraphRunContext[TicketState, None]
    ) -> Escalate | Annotated[StepNode[TicketState, None], close_ticket]:
        ctx.state.trail.append('分诊')
        if '崩溃' in self.ticket:
            return Escalate(self.ticket)
        return close_ticket.as_node(self.ticket)      # ← Sprung zu einem Step


@dataclass
class Escalate(BaseNode[TicketState, None, str]):
    ticket: str

    async def run(self, ctx: GraphRunContext[TicketState, None]) -> End[str]:
        ctx.state.trail.append('升级')
        return End(f'工单 {self.ticket} 已升级给二线')


@g.step
async def entry(ctx: StepContext[TicketState, None, str]) -> Triage:
    return Triage(ctx.inputs)


g.add(
    g.edge_from(g.start_node).to(entry),
    g.node(Triage),
    g.node(Escalate),
    g.edge_from(close_ticket).to(g.end_node),
)

graph = g.build()


async def main():
    for t in ('登录页崩溃', '文案错别字'):
        st = TicketState(trail=[])
        print(await graph.run(state=st, inputs=t), '|', st.trail)
```

Reale Ausgabe:

```text
工单 登录页崩溃 已升级给二线 | ['分诊', '升级']
工单 文案错别字 已关闭 | ['分诊', '关单']
```

Ausgabe von `render()`:

```text
stateDiagram-v2
  entry
  Triage
  state decision <<choice>>
  Escalate
  close_ticket

  [*] --> entry
  entry --> Triage
  Triage --> decision
  decision --> Escalate
  decision --> close_ticket
  Escalate --> [*]
  close_ticket --> [*]
```

Die Schreibweise `Annotated[StepNode[...], close_ticket]` ist etwas unschön. Der Grund: Pythons Typsystem kann im Typ selbst nicht ausdrücken, „dies ist genau der Step `close_ticket`". Deshalb wird das Step-Objekt als Metadatum an `Annotated` gehängt. Beim Auslesen der Annotation greift die Bibliothek es dort heraus.

> ⚠️ **Fallstrick**: Schreiben Sie `-> StepNode[S, D]` und vergessen dabei die Hülle `Annotated[..., derBetreffendeStep]`, wird **bereits bei der Registrierung durch `g.add()` / `g.node()`** ein `GraphSetupError` geworfen (nicht erst bei `build()`), mit dem Hinweis „return type hint includes a `StepNode` without a `Step` annotation".

> 👉 **CEO-Perspektive**: Das Mischen ist eigentlich ganz natürlich — **den Hauptstrang als Zustandsautomat (BaseNode) modellieren, damit klar ist, an welcher Station der Vorgang gerade steht, und die eigentliche Arbeit jeder Station als Step schreiben**. Genau wie beim Freigabeprozess, dessen Hauptstrang „einzureichen → wartet auf Freigabe → wartet auf Auszahlung → abgeschlossen" lautet; innerhalb der Station „wartet auf Auszahlung" müssen aber drei Zahlungsschnittstellen angesprochen, Buchungen geschrieben und Benachrichtigungen verschickt werden — das geht mit Steps deutlich bequemer.

### 3.5 `@g.stream`: Streaming-Knoten

Ein gewöhnlicher Step „rechnet fertig und liefert alles auf einmal zurück", ein Streaming-Step „liefert schon während des Rechnens nach unten weiter". Er nimmt einen **async-Generator** entgegen:

```python
import asyncio
from pydantic_graph import GraphBuilder, StepContext, reduce_list_append

g = GraphBuilder(output_type=list[str])


@g.stream
async def pull_leads(ctx: StepContext[None, None, None]):
    for i in range(1, 4):
        await asyncio.sleep(0.05)      # Simulation: Leads schubweise aus dem CRM ziehen
        yield f'线索{i}'                # ← eines nach dem anderen per yield hinausgeben


@g.step
async def score(ctx: StepContext[None, None, str]) -> str:
    return f'{ctx.inputs} -> 评分完成'


collect = g.join(reduce_list_append, initial_factory=list[str])

g.add(
    g.edge_from(g.start_node).to(pull_leads),
    g.edge_from(pull_leads).map().to(score),   # ← jedes herausströmende Element wird parallel verarbeitet
    g.edge_from(score).to(collect),
    g.edge_from(collect).to(g.end_node),
)

graph = g.build()


async def main():
    print(sorted(await graph.run()))
```

Reale Ausgabe:

```text
['线索1 -> 评分完成', '线索2 -> 评分完成', '线索3 -> 评分完成']
```

Ausgabe von `render()` (beachten Sie, dass `pull_leads` im Diagramm genauso aussieht wie ein gewöhnlicher Step):

```text
stateDiagram-v2
  pull_leads
  state map <<fork>>
  score
  state reduce_list_append <<join>>

  [*] --> pull_leads
  pull_leads --> map
  map --> score
  score --> reduce_list_append
  reduce_list_append --> [*]
```

**Das Wesen eines Streaming-Knotens**: `@g.stream` legt intern eine Hülle um Ihren Generator, sodass der „Rückgabewert" dieses Steps zu einem `AsyncIterable` wird. In Kombination mit `.map()` wird **bei jedem yield sofort eine nachgelagerte parallele Aufgabe gestartet**, ohne dass der Generator erst vollständig durchlaufen muss.

> 👉 **CEO-Perspektive**: Das entspricht der Produkterfahrung „**Verarbeitung im Durchlauf**". Beispiel: 10.000 Kundendatensätze im Batch importieren und per KI verschlagworten:
> - Gewöhnlicher Step: Erst werden alle 10.000 Datensätze abgefragt (30 Sekunden), dann beginnt die Verschlagwortung → der Nutzer starrt 30 Sekunden auf einen unbewegten Fortschrittsbalken
> - Streaming-Step: Sobald eine Charge abgefragt ist, wird sie verschlagwortet → der Fortschrittsbalken bewegt sich ab der ersten Sekunde
>
> Die vom Nutzer erlebte Gesamtdauer mag identisch sein, aber die **wahrgenommene Reaktionsgeschwindigkeit** liegt Welten auseinander.

### 3.6 Knoten-IDs und Beschriftungen

Zwei optionale Parameter, beide wirken sich auf die Visualisierung aus:

```python
@g.step(label='拉取用户画像', node_id='profile')
async def fetch_profile(ctx: StepContext[None, None, None]) -> str:
    return 'CEO小李'


@g.step(label='生成推荐语')
async def make_copy(ctx: StepContext[None, None, str]) -> str:
    return f'你好 {ctx.inputs}'


g.add(g.edge_from(g.start_node).to(fetch_profile))
g.add_edge(fetch_profile, make_copy, label='带上画像')
g.add(g.edge_from(make_copy).to(g.end_node))
```

Reale Ausgabe von `render(title='推荐语生成', direction='TB')`:

```text
---
title: 推荐语生成
---
stateDiagram-v2
  direction TB
  profile: 拉取用户画像
  make_copy: 生成推荐语

  [*] --> profile
  profile --> make_copy: 带上画像
  make_copy --> [*]
```

| Parameter | Wirkung | Standardwert |
|---|---|---|
| `node_id=` | Die eindeutige ID des Knotens im Graphen, **muss im gesamten Graphen eindeutig sein** | Bei Steps der Funktionsname, bei BaseNode der Klassenname |
| `label=` | Der für Menschen lesbare Klartextname, gerendert als `Knoten-ID: Beschriftung` | Keiner |
| `g.add_edge(A, B, label=)` | Beschriftet eine **Kante**, gerendert als `A --> B: Beschriftung` | Keine |

Sie können sich auch direkt ansehen, welche Knoten der Graph enthält:

```python
for nid, node in graph.nodes.items():
    print(f'{nid:20} {type(node).__name__}')
```

```text
__start__            StartNode
profile              Step
make_copy            Step
__end__              EndNode
```

Beachten Sie, dass die IDs von Start- und Endpunkt fest auf `__start__` / `__end__` lauten.

> ⚠️ **Fallstrick**: Ein Konflikt bei `node_id` wird **bereits bei der Registrierung durch `g.add()`** als `GraphBuildingError: All nodes must have unique node IDs.` geworfen (nicht erst bei `build()`). Wenn Sie zwei gleichnamige Funktionen haben (etwa jeweils `process` in unterschiedlichen Modulen), müssen Sie `node_id` von Hand vergeben.

> 👉 **CEO-Perspektive**: `label` ist der Punkt, an dem Sie unmittelbar Einfluss nehmen können. Lassen Sie die Entwickler für jeden Knoten eine sprechende Beschriftung in Klartext vergeben, dann versteht die Fachabteilung das von `render()` erzeugte Diagramm sofort, ohne dass es noch einmal übersetzt werden muss. Das ist **Prozessdokumentation zu den geringstmöglichen Kosten**.

### 3.7 ⚠️ Ein realer Fallstrick: Ein Step, der eine Union von BaseNodes zurückgibt, fliegt zur Laufzeit auseinander

Dies ist ein Verhaltensunterschied dieser Version, den Sie unbedingt kennen müssen. Oben hieß es, Kanten würden aus den Rückgabetyp-Annotationen abgeleitet — aber **die daraus abgeleitete Verzweigungslogik unterscheidet sich zwischen `@g.step` und `BaseNode`**.

Zunächst die Schreibweise, die auseinanderfliegt:

```python
@dataclass
class Approve(BaseNode[None, None, str]):
    who: str
    async def run(self, ctx: GraphRunContext) -> End[str]:
        return End(f'{self.who} 已通过')


@dataclass
class Reject(BaseNode[None, None, str]):
    who: str
    async def run(self, ctx: GraphRunContext) -> End[str]:
        return End(f'{self.who} 被驳回')


g = GraphBuilder(input_type=int, output_type=str)

@g.step
async def judge(ctx: StepContext[None, None, int]) -> Approve | Reject:   # ⚠️ Union
    return Approve('小张') if ctx.inputs >= 60 else Reject('小张')

g.add(
    g.edge_from(g.start_node).to(judge),
    g.node(Approve),
    g.node(Reject),
)
graph = g.build()          # build() meldet keinen Fehler

import asyncio
asyncio.run(graph.run(inputs=90))   # ← erst hier fliegt es auseinander
```

Real gemessene Fehlermeldung:

```text
RuntimeError: No branch matched inputs Approve(who='小张') for decision node
Decision(id='decision', branches=[
  DecisionBranch(source=<class 'NoneType'>, matches=None, ...destinations=[NodeStep(id='Approve'...)]),
  DecisionBranch(source=<class 'NoneType'>, matches=None, ...destinations=[NodeStep(id='Reject'...)]),
])
```

**Die Ursache** (ich habe die Funktion `_edge_from_return_hint` im Quelltext von `graph_builder.py` gelesen): Ist die Rückgabeannotation eine Union mehrerer Knotentypen, legt die Bibliothek automatisch einen Decision-Knoten an, dessen Verzweigungsbedingung jedoch nur der Platzhalter `NoneType` ist. Der Kommentar im Quelltext lautet wörtlich:

> `# We don't actually use this decision mechanism, but we need to build the edges for parent-fork finding`

Mit anderen Worten: Diese Decision existiert **nur, um die Kanten in der Graphstruktur überhaupt zu zeichnen** (für die Fork-/Join-Analyse und das Rendering), sie ist **nicht dafür gedacht, zur Laufzeit tatsächlich benutzt zu werden**.

- Auf dem `BaseNode`-Weg (`g.node(X)`): Nach Abschluss des Knotens nimmt der Scheduler den Zweig `_handle_node()` — er **schaut direkt nach, welcher Klasse das zurückgegebene Objekt angehört, und routet zum entsprechenden Knoten**, ganz ohne jene Decision. ✅ Deshalb funktioniert es einwandfrei.
- Auf dem `@g.step`-Weg: Nach Abschluss des Knotens nimmt der Scheduler `_handle_edges()` → trifft auf jene Platzhalter-Decision → vergleicht per `isinstance()` gegen `NoneType` → **nichts passt → RuntimeError**. ❌

**Zwei korrekte Schreibweisen:**

**Variante A (empfohlen): Die Verzweigungslogik in einen `BaseNode` verlagern**

```python
@dataclass
class Judge(BaseNode[None, None, str]):
    score: int
    async def run(self, ctx: GraphRunContext) -> Approve | Reject:
        return Approve('小张') if self.score >= 60 else Reject('小张')


@g.step
async def entry(ctx: StepContext[None, None, int]) -> Judge:
    return Judge(ctx.inputs)


g.add(
    g.edge_from(g.start_node).to(entry),
    g.node(Judge), g.node(Approve), g.node(Reject),
)
```

**Variante B: Der Step gibt einen gewöhnlichen Wert zurück, verzweigt wird über ein explizites `g.decision()`**

```python
@g2.step
async def score_it(ctx: StepContext[None, None, int]) -> int:      # ← gibt ein gewöhnliches int zurück
    return ctx.inputs

@g2.step
async def approve(ctx: StepContext[None, None, int]) -> str:
    return '已通过'

@g2.step
async def reject(ctx: StepContext[None, None, int]) -> str:
    return '被驳回'

g2.add(
    g2.edge_from(g2.start_node).to(score_it),
    g2.edge_from(score_it).to(
        g2.decision()
        .branch(g2.match(int, matches=lambda s: s >= 60).to(approve))
        .branch(g2.match(int).to(reject))
    ),
    g2.edge_from(approve, reject).to(g2.end_node),
)
```

Reale Ausgabe beider Varianten:

```text
A: 小张 已通过 / 小张 被驳回
B: 已通过 / 被驳回
```

Das `render()` von Variante A:

```text
stateDiagram-v2
  entry
  Judge
  state decision <<choice>>
  Approve
  Reject

  [*] --> entry
  entry --> Judge
  Judge --> decision
  decision --> Approve
  decision --> Reject
  Approve --> [*]
  Reject --> [*]
```

**Als Merkhilfe:**

| Was Sie tun wollen | Was Sie verwenden |
|---|---|
| Ein Step gibt **einen** bestimmten nachgelagerten Knoten zurück | ✅ Einfach `-> NextNode` schreiben, die Kante entsteht automatisch |
| Ein Step soll zwischen **mehreren BaseNodes** verzweigen | ❌ Keine Union schreiben → auf Variante A oder B umstellen |
| Ein BaseNode soll zwischen mehreren Nachfolgern verzweigen | ✅ Einfach `-> A \| B \| End[X]` schreiben |
| Ein Step soll zwischen **mehreren Steps** verzweigen | ✅ Ein explizites `g.decision()` verwenden |

> ⚠️ **Fallstrick**: Das Unangenehmste an dieser Falle ist, dass **`build()` keinen Fehler meldet**; der Graph lässt sich auch zeichnen, alles wirkt normal — erst wenn die Ausführung diesen Schritt erreicht, fliegt es auseinander. Denken Sie deshalb daran, nach dem Schreiben **jeden einzelnen Zweig per Unit-Test einmal durchlaufen zu lassen**.

---

## 4. Zustand und Abhängigkeiten: die vier Generics

`GraphBuilder` hat vier Typparameter, die den gesamten Graphen durchziehen. Dieser Abschnitt klärt, was jeder einzelne ist, wann man ihn einsetzt und wie man sie auseinanderhält.

Zunächst die Themen:

1. Übersichtstabelle der vier Parameter
2. `state_type`: die veränderlichen Daten, die der gesamte Prozess teilt
3. `deps_type`: injizierte externe Ressourcen
4. `input_type` / `output_type`: Ein- und Ausgang des Graphen
5. Der Unterschied zwischen `StepContext` und `GraphRunContext`
6. Wie man zwischen `state` und `deps` wirklich wählt

### 4.1 Übersicht der vier Parameter

```python
g = GraphBuilder(
    name='报销审批流',          # optional, der Name in Logs / Traces
    state_type=AuditState,      # Zustand
    deps_type=Deps,             # Abhängigkeiten
    input_type=Expense,         # Eingabe
    output_type=str,            # Ausgabe
    auto_instrument=True,       # ob automatisch OpenTelemetry-Spans erzeugt werden, Standard True
)
```

| Parameter | Standardwert | Lebenszyklus | Veränderlich? | Wer liefert es | Analogie |
|---|---|---|---|---|---|
| `state_type` | `NoneType` | Innerhalb eines Runs | ✅ Knoten dürfen es beliebig ändern | Aufrufer via `run(state=...)` | **Der Vorgang selbst** (Spesenabrechnung, Bestellung) |
| `deps_type` | `NoneType` | Innerhalb eines Runs | ⚠️ Technisch änderbar, sollte aber nicht geändert werden | Aufrufer via `run(deps=...)` | **Die Büroausstattung** (Datenbankverbindung, Client des Zahlungsgateways) |
| `input_type` | `NoneType` | Im Moment des Eintritts in den Graphen | — | Aufrufer via `run(inputs=...)` | **Das Formular, das beim Anstoßen des Prozesses ausgefüllt wird** |
| `output_type` | `NoneType` | Im Moment des Verlassens des Graphen | — | Der Graph erzeugt es selbst | **Das Endergebnis des Prozesses** |

> 👉 **CEO-Perspektive**: Diese vier Dinge entsprechen vier Konfigurationspunkten im Backend eines Freigabe-Workflows:
> - `input_type` = „Welche Felder muss der Antragsteller ausfüllen"
> - `state_type` = „Welche Felder dieses Vorgangs werden von den einzelnen Stationen beschrieben" (Freigabekommentare, Zeitstempel, Anlagen)
> - `deps_type` = „An welche externen Systeme dieser Prozess andockt" (HR-System, Finanzsystem)
> - `output_type` = „Was nach Abschluss des Prozesses zurückgegeben wird"

### 4.2 `state_type`: die veränderlichen Daten, die der gesamte Prozess teilt

**Merkmale: pro Run eine neue Instanz, alle Knoten dürfen lesen und schreiben, und nach dem Durchlauf können Sie sie sich noch ansehen.**

```python
import asyncio
from dataclasses import dataclass
from pydantic_graph import GraphBuilder, StepContext


@dataclass
class OrderState:
    log: list[str]


g = GraphBuilder(state_type=OrderState, input_type=int, output_type=str)


@g.step
async def check_stock(ctx: StepContext[OrderState, None, int]) -> int:
    ctx.state.log.append(f'查库存: 订单 {ctx.inputs}')     # ← Zustand schreiben
    return ctx.inputs


@g.step
async def charge(ctx: StepContext[OrderState, None, int]) -> str:
    ctx.state.log.append(f'扣款: 订单 {ctx.inputs}')
    return f'订单 {ctx.inputs} 已完成'
```

Nach dem Durchlauf ist das **außen liegende `state`-Objekt tatsächlich verändert worden**:

```python
state = OrderState(log=[])
result = await order_graph.run(state=state, inputs=1001)
print(result)       #> 订单 1001 已完成
print(state.log)    #> ['查库存: 订单 1001', '扣款: 订单 1001']
```

Das ist der wertvollste Einsatz von state: **Der Graph hat nur einen Rückgabewert, aber sämtliche Nebenprodukte, die unterwegs entstehen, lassen sich im state sammeln und mit hinausnehmen.**

> 👉 **CEO-Perspektive**: `state` ist der **Bearbeitungsverlauf auf dem Antragsformular**. Der `output` des Graphen ist „genehmigt oder nicht", im state steht dagegen, „wer wann in welchem Schritt was getan hat" — und dieser Verlauf ist für Beschwerdebearbeitung, Abstimmung und Compliance-Audits oft wertvoller als das Ergebnis selbst.
>
> Beim Entwurf eines neuen Prozesses lohnt es sich, den Entwicklern gezielt die Frage zu stellen: **„Welche Audit-Informationen kann ich nach dem Durchlauf dieses Prozesses aus dem state entnehmen?"**

⚠️ **Bei Parallelität ist der state geteilt.** Alle parallelen Aufgaben verändern **dasselbe state-Objekt**, ohne jede Sperre. Das Beispiel aus der offiziellen Dokumentation:

```python
@g.step
async def track_and_square(ctx: StepContext[CounterState, None, int]) -> int:
    ctx.state.values.append(ctx.inputs)      # ← drei parallele Aufgaben führen gleichzeitig append aus
    return ctx.inputs * ctx.inputs
```

Pythons `list.append` ist selbst atomar, deshalb ist das unproblematisch. Schreiben Sie jedoch etwas wie `ctx.state.counter = ctx.state.counter + 1`, also ein „Lesen-Ändern-Schreiben", können unter Parallelität Aktualisierungen verloren gehen.

> ⚠️ **Fallstrick**: Führen Sie in parallelen Zweigen am state ausschließlich **anfügende** Operationen aus (`append` / `dict[k]=v`), niemals „auslesen, rechnen, zurückschreiben". Zum Aufsummieren nehmen Sie den Reducer eines Join (Abschnitt 5).

### 4.3 `deps_type`: injizierte externe Ressourcen

**Merkmale: bei jedem Run hereingereicht, von den Knoten nur gelesen, dient der Umgebungsisolation.**

```python
import asyncio
from dataclasses import dataclass
from pydantic_graph import GraphBuilder, StepContext


@dataclass
class Deps:
    db_url: str
    notify_channel: str


g = GraphBuilder(deps_type=Deps, input_type=int, output_type=str)


@g.step
async def load(ctx: StepContext[None, Deps, int]) -> str:
    return f'从 {ctx.deps.db_url} 读取用户 {ctx.inputs}'


@g.step
async def notify(ctx: StepContext[None, Deps, str]) -> str:
    return f'{ctx.inputs}, 并推送到 {ctx.deps.notify_channel}'


g.add(
    g.edge_from(g.start_node).to(load),
    g.edge_from(load).to(notify),
    g.edge_from(notify).to(g.end_node),
)
graph = g.build()


async def main():
    prod = Deps(db_url='prod-db', notify_channel='#alerts')
    test = Deps(db_url='sqlite://memory', notify_channel='#dev-null')
    print(await graph.run(deps=prod, inputs=42))
    print(await graph.run(deps=test, inputs=42))
```

Reale Ausgabe:

```text
从 prod-db 读取用户 42, 并推送到 #alerts
从 sqlite://memory 读取用户 42, 并推送到 #dev-null
```

**Derselbe Graph — ein anderes `deps` genügt, um von Produktion auf Test umzuschalten.** Das ist der gesamte Sinn von Dependency Injection.

In der offiziellen Dokumentation gibt es noch ein praxisnäheres Beispiel: CPU-intensive Berechnungen an einen Prozesspool auslagern:

```python
@dataclass
class GraphDeps:
    executor: ProcessPoolExecutor


@dataclass
class Increment(BaseNode[None, GraphDeps]):
    foo: int

    async def run(self, ctx: GraphRunContext[None, GraphDeps]) -> DivisibleBy5:
        loop = asyncio.get_running_loop()
        compute_result = await loop.run_in_executor(ctx.deps.executor, self.compute)
        return DivisibleBy5(compute_result)

    def compute(self) -> int:
        return self.foo + 1
```

> 👉 **CEO-Perspektive**: `deps` ist der Schalter für **„derselbe Prozess, unterschiedliche Umgebungen"**. Der unmittelbare Produktnutzen:
> - **Testbarkeit**: In der Testumgebung ein simuliertes Zahlungsgateway verwenden, 100 Durchläufe kosten keinen Cent
> - **Schrittweiser Rollout**: Alte und neue Risiko-Engine als zwei Deps führen, 5 % des Traffics über die neue leiten
> - **Mandantenfähigkeit**: Kunde A gegen A's Datenbank, Kunde B gegen B's — die Prozessdefinition existiert nur einmal

### 4.4 Wie wählt man nun zwischen `state` und `deps`?

Der Punkt, den Einsteiger am ehesten verwechseln. Die Entscheidungskriterien:

| Frage | Ja → state | Ja → deps |
|---|---|---|
| Ist es eine **Tatsache dieses konkreten Geschäftsvorfalls**? (der Betrag dieser Bestellung) | ✅ | |
| Ist es **Infrastruktur**? (eine Datenbankverbindung) | | ✅ |
| Will ich es nach dem Durchlauf **herausnehmen und ansehen**? | ✅ | |
| **Ändert** es sich bei einem Umgebungswechsel (Test/Produktion)? | | ✅ |
| Wird es im Verlauf des Prozesses **überschrieben**? | ✅ | |
| Kann es **von mehreren Runs geteilt** werden? | ❌ Pro Run eine neue Instanz | ✅ Dasselbe Objekt ist wiederverwendbar |

In einem Satz: **`state` ist „der Inhalt des Vorgangs", `deps` sind „die Werkzeuge, mit denen der Vorgang bearbeitet wird".**

### 4.5 `input_type` / `output_type`: Ein- und Ausgang des Graphen

```python
g = GraphBuilder(input_type=Expense, output_type=str)
result: str = await graph.run(inputs=Expense('小王', 300.0))
```

| Parameter | Fließrichtung | Wer konsumiert es |
|---|---|---|
| `input_type` | `run(inputs=X)` → `g.start_node` → `ctx.inputs` des ersten Knotens | Der Knoten, zu dem die Kante vom start_node führt |
| `output_type` | Rückgabewert des letzten Knotens → `g.end_node` → Rückgabewert von `run()` | Der Aufrufer |

Auf dem `BaseNode`-Weg ist die Ausgabe des Graphen genau das `x` aus `End(x)`.

**Zu `g.start_node` und `g.end_node`:**

- Es sind eingebaute virtuelle Knoten mit den festen IDs `__start__` / `__end__`
- In Mermaid werden sie als `[*]` gerendert
- Jeder Graph **muss** mindestens eine vom Start ausgehende und eine ins Ende führende Kante haben (sonst meldet `build()` einen Fehler)

### 4.6 `StepContext` vs. `GraphRunContext`

Das ist der unmittelbarste Unterschied zwischen den beiden Schreibweisen für Knoten:

| | `StepContext[StateT, DepsT, InputT]` | `GraphRunContext[StateT, DepsT]` |
|---|---|---|
| Wer bekommt ihn | Der erste Parameter einer `@g.step`- / `@g.stream`-Funktion | Der `ctx`-Parameter von `BaseNode.run()` |
| `.state` | ✅ | ✅ |
| `.deps` | ✅ | ✅ |
| `.inputs` | ✅ **vorhanden** | ❌ **nicht vorhanden** |
| Anzahl der Generics | 3 | 2 |
| Warum dieses Design | Ein Step ist eine zustandslose Funktion, seine Eingabe muss von außen kommen | Ein BaseNode ist ein zustandsbehaftetes Objekt, seine Eingabe sind die Felder von `self` |

Ergänzend: Auch das `ctx` in `.transform(lambda ctx: ...)` ist ein `StepContext`, folglich können Transformationsfunktionen auf Kanten ebenfalls `state` / `deps` / `inputs` lesen.

`ReducerContext[StateT, DepsT]` (der Kontext, den eine Reducer-Funktion erhält) ist die dritte Variante; sie besitzt nur `.state` / `.deps` sowie eine Methode `.cancel_sibling_tasks()`, dazu mehr in Abschnitt 5.

### 4.7 Vollständiges Beispiel mit allen vier Parametern

Alle vier Parameter gemeinsam im Einsatz:

```python
import asyncio
from dataclasses import dataclass
from pydantic_graph import GraphBuilder, StepContext, TypeExpression


@dataclass
class Expense:              # ← input_type
    who: str
    amount: float


@dataclass
class AuditState:           # ← state_type
    trail: list[str]


g = GraphBuilder(
    state_type=AuditState,
    input_type=Expense,
    output_type=str,        # ← output_type
)


@g.step
async def submit(ctx: StepContext[AuditState, None, Expense]) -> Expense:
    ctx.state.trail.append(f'{ctx.inputs.who} 提交 {ctx.inputs.amount} 元')
    return ctx.inputs


@g.step
async def lead_approve(ctx: StepContext[AuditState, None, Expense]) -> str:
    ctx.state.trail.append('组长审批')
    return f'{ctx.inputs.who} 的 {ctx.inputs.amount} 元由组长批准'


@g.step
async def director_approve(ctx: StepContext[AuditState, None, Expense]) -> str:
    ctx.state.trail.append('总监审批')
    return f'{ctx.inputs.who} 的 {ctx.inputs.amount} 元由总监批准'


g.add(
    g.edge_from(g.start_node).to(submit),
    g.edge_from(submit).to(
        g.decision(note='金额 <= 1000 走组长')
        .branch(
            g.match(TypeExpression[Expense], matches=lambda e: e.amount <= 1000)
            .label('小额').to(lead_approve)
        )
        .branch(
            g.match(TypeExpression[Expense], matches=lambda e: e.amount > 1000)
            .label('大额').to(director_approve)
        )
    ),
    g.edge_from(lead_approve, director_approve).to(g.end_node),
)

approval_graph = g.build()


async def main():
    for amount in (300.0, 5000.0):
        state = AuditState(trail=[])
        result = await approval_graph.run(state=state, inputs=Expense('小王', amount))
        print(result)
        print(state.trail)
```

Reale Ausgabe:

```text
小王 的 300.0 元由组长批准
['小王 提交 300.0 元', '组长审批']
小王 的 5000.0 元由总监批准
['小王 提交 5000.0 元', '总监审批']
```

Ausgabe von `render()` (beachten Sie, dass `note` als Anmerkung im Diagramm gerendert wird):

```text
stateDiagram-v2
  submit
  state decision <<choice>>
  note right of decision
    金额 <= 1000 走组长
  end note
  director_approve
  lead_approve

  [*] --> submit
  submit --> decision
  decision --> director_approve: 大额
  decision --> lead_approve: 小额
  director_approve --> [*]
  lead_approve --> [*]
```

> 👉 **CEO-Perspektive**: Dieses Diagramm können Sie praktisch unverändert in ein PRD übernehmen. In der `note` steht die Geschäftsregel, die Beschriftungen an den Kanten sind die Zweignamen — auf einen Blick ist erkennbar, dass 1000 die Schwelle ist. Ändert sich die Regel (etwa auf 2000), ändert sich die Anmerkung im Diagramm mit — denn sie steht im Code.

---

## 5. Kontrollfluss: die fünf Formen eines Graphen

Dies ist der wichtigste Abschnitt. Jedes Flussdiagramm besteht aus nicht mehr als fünf Formen: **Sequenz, Verzweigung, Schleife, paralleles Fan-out, paralleles Fan-in**. Dieser Abschnitt arbeitet jede davon vollständig durch, jeweils mit dem echten, von `render()` erzeugten Mermaid-Diagramm.

Zunächst die Liste der Themen dieses Abschnitts:

| # | Form | API | Unterabschnitt |
|---|---|---|---|
| 1 | Sequenz | `g.edge_from(A).to(B)` / `g.add_edge(A, B)` | 5.1 |
| 2 | Verzweigung | `g.decision()` + `.branch(g.match(...))` | 5.2 |
| 3 | Verzweigung: nach Typ | `g.match(int)` | 5.2.1 |
| 4 | Verzweigung: nach Union / Literal | `g.match(TypeExpression[...])` | 5.2.2 |
| 5 | Verzweigung: eigenes Prädikat | `g.match(T, matches=lambda x: ...)` | 5.2.3 |
| 6 | Verzweigung: Priorität und Auffangzweig | Zweigreihenfolge + `g.match(TypeExpression[object])` | 5.2.4 |
| 7 | Verzweigung: nach Knotentyp | `g.match_node(SomeNode)` | 5.2.5 |
| 8 | Verzweigung: verschachtelt | Mehrere `g.decision()` hintereinander | 5.2.6 |
| 9 | Verzweigung: Anmerkungen und Beschriftungen | `g.decision(note=)` / `.label()` | 5.2.7 |
| 10 | Schleife | Eine Kante zurück zu einem vorgelagerten Knoten | 5.3 |
| 11 | Paralleles Fan-out: Broadcast | `.to(A, B, C)` / `.broadcast()` | 5.4 |
| 12 | Paralleles Fan-out: Mapping | `.map()` / `g.add_mapping_edge()` | 5.5 |
| 13 | Paralleles Fan-in | `g.join(reducer, initial=/initial_factory=)` | 5.6 |
| 14 | Eingebaute Reducer (sechs) | `reduce_*` / `ReduceFirstValue` | 5.6.2 |
| 15 | Eigener Reducer + vorzeitiger Abbruch | `ReducerContext.cancel_sibling_tasks()` | 5.6.3 |
| 16 | Transformation auf der Kante | `.transform(lambda ctx: ...)` | 5.7 |
| 17 | Der Fallstrick leerer Collections | `downstream_join_id=` | 5.8 |
| 18 | Verschachtelte Parallelität | map um broadcast, aufeinanderfolgende map | 5.9 |
| 19 | Mehrere unabhängige Joins | Unterscheidung über `node_id=` | 5.10 |

### 5.1 Sequenz

Die einfachste Form, zwei gleichwertige Schreibweisen:

```python
# Schreibweise 1: edge_from().to()
g.add(
    g.edge_from(g.start_node).to(step_a),
    g.edge_from(step_a).to(step_b),
    g.edge_from(step_b).to(g.end_node),
)

# Schreibweise 2: add_edge() (kürzer, taugt aber nur für einfache Kanten)
g.add_edge(g.start_node, step_a)
g.add_edge(step_a, step_b, label='从 a 到 b')
g.add_edge(step_b, g.end_node)
```

`g.edge_from()` nimmt außerdem **mehrere Quellen** entgegen, was bedeutet: „diese Knoten führen alle zum selben Ziel":

```python
g.edge_from(lead_approve, director_approve).to(g.end_node)
# entspricht zwei Kanten: lead_approve → end, director_approve → end
```

Das braucht man besonders häufig beim Zusammenführen von Zweigen.

> 👉 **CEO-Perspektive**: `g.edge_from(A, B, C).to(D)` ist im Swimlane-Diagramm der Fall „drei Nebenstränge münden in denselben Endpunkt". Beachten Sie: Das ist **kein** Join — es muss nicht gewartet werden, bis alle drei fertig sind; wer zuerst kommt, geht zuerst weiter. Das echte „warten, bis alle da sind" ist `g.join()` (5.6).

### 5.2 Verzweigung: `decision` + `match`

Die Grundform einer Verzweigung:

```python
g.edge_from(Quellknoten).to(
    g.decision(note='Regelbeschreibung')
    .branch(g.match(Bedingung1).to(Ziel1))
    .branch(g.match(Bedingung2).to(Ziel2))
    .branch(g.match(Bedingung3).to(Ziel3))
)
```

**Ausführungslogik** (Quelltext `_handle_decision`): Die Zweige werden von oben nach unten durchprobiert, **der erste Treffer gewinnt** und sein Pfad wird genommen. **Passt kein einziger, wird ein `RuntimeError` geworfen.**

Das entspricht genau Pythons `if / elif / elif`, nur ohne implizites `else` — **wer keinen Auffangzweig schreibt, fliegt auseinander**.

#### 5.2.1 Matching nach Typ

Die einfachste Form: einfach eine Klasse übergeben:

```python
g.edge_from(return_int).to(
    g.decision()
    .branch(g.match(int).to(handle_int))
    .branch(g.match(str).to(handle_str))
)
```

Intern wird mit `isinstance(Eingabewert, int)` geprüft.

#### 5.2.2 Matching nach Union / Literal: `TypeExpression` erforderlich

Python erlaubt es nicht, `int | str` oder `Literal['a']` als Laufzeit-`type`-Wert zu übergeben, deshalb braucht es den Wrapper `TypeExpression`:

```python
from pydantic_graph import TypeExpression

g.match(TypeExpression[int | float]).to(handle_number)      # union
g.match(TypeExpression[Literal['退款']]).to(refund)          # Literal
g.match(TypeExpression[object]).to(catch_all)               # Auffangzweig
```

| Matching-Ziel | Schreibweise | Interne Prüflogik |
|---|---|---|
| Gewöhnliche Klasse | `g.match(int)` | `isinstance(v, int)` |
| Union | `g.match(TypeExpression[int \| float])` | `isinstance(v, (int, float))` |
| Literal | `g.match(TypeExpression[Literal['a', 'b']])` | `v in ('a', 'b')` |
| Auffangzweig | `g.match(TypeExpression[object])` oder `TypeExpression[Any]` | Immer True |

Ein vollständiges Beispiel — Support-Tickets nach Absicht verteilen:

```python
import asyncio
from dataclasses import dataclass
from typing import Literal
from pydantic_graph import GraphBuilder, StepContext, TypeExpression


@dataclass
class S:
    pass


g = GraphBuilder(state_type=S, input_type=str, output_type=str)


@g.step
async def classify(ctx: StepContext[S, None, str]) -> Literal['退款', '换货', '咨询']:
    if '坏' in ctx.inputs:
        return '换货'
    if '钱' in ctx.inputs:
        return '退款'
    return '咨询'


@g.step
async def refund(ctx: StepContext[S, None, object]) -> str:
    return '走退款流程'


@g.step
async def exchange(ctx: StepContext[S, None, object]) -> str:
    return '走换货流程'


@g.step
async def faq(ctx: StepContext[S, None, object]) -> str:
    return '转 FAQ 机器人'


g.add(
    g.edge_from(g.start_node).to(classify),
    g.edge_from(classify).to(
        g.decision()
        .branch(g.match(TypeExpression[Literal['退款']]).to(refund))
        .branch(g.match(TypeExpression[Literal['换货']]).to(exchange))
        .branch(g.match(TypeExpression[object]).to(faq))       # ← Auffangzweig
    ),
    g.edge_from(refund, exchange, faq).to(g.end_node),
)
graph = g.build()


async def main():
    for msg in ('杯子坏了', '想退钱', '怎么用'):
        print(msg, '->', await graph.run(state=S(), inputs=msg))
```

Reale Ausgabe:

```text
杯子坏了 -> 走换货流程
想退钱 -> 走退款流程
怎么用 -> 转 FAQ 机器人
```

Ausgabe von `render()`:

```text
stateDiagram-v2
  classify
  state decision <<choice>>
  exchange
  faq
  refund

  [*] --> classify
  classify --> decision
  decision --> exchange
  decision --> faq
  decision --> refund
  exchange --> [*]
  faq --> [*]
  refund --> [*]
```

> 👉 **CEO-Perspektive**: Das ist das Standardvorgehen für „Absichtserkennung → Verteilung". Der Schritt `classify` ließe sich ohne Weiteres durch einen Agenten ersetzen (das Modell übernimmt die Klassifikation), aber **die Verteilungsregeln bleiben hart codiert** — das Modell beantwortet lediglich die Frage „welche Kategorie ist das", es entscheidet nicht, „welcher Prozess durchlaufen wird". Diese Trennung der Verantwortlichkeiten ist außerordentlich wichtig: Die Ausgabe des Modells ist auf eines von drei Literalen eingeschränkt, es kann keinen Unsinn anstellen.

#### 5.2.3 Eigene Prädikate: `matches=`

Wenn eine Typprüfung nicht ausreicht (Fälle wie „Betrag > 1000"), übergeben Sie eine `matches`-Funktion:

```python
g.decision(note='金额 <= 1000 走组长')
 .branch(
     g.match(TypeExpression[Expense], matches=lambda e: e.amount <= 1000)
     .label('小额').to(lead_approve)
 )
 .branch(
     g.match(TypeExpression[Expense], matches=lambda e: e.amount > 1000)
     .label('大额').to(director_approve)
 )
```

`matches` ist ein `Callable[[Any], bool]`, dessen Parameter genau **der Wert selbst** ist, der zu dieser Decision fließt.

> ⚠️ **Fallstrick**: `matches` **erhält nur den Wert, nicht `ctx.state` und nicht `ctx.deps`**. Wenn Ihre Verzweigungsbedingung den Zustand berücksichtigen muss (etwa „der wievielte Wiederholungsversuch ist das"), müssen Sie diese Information in den durchfließenden Wert packen (als Feld einer dataclass) oder sie in einem vorgelagerten Step vorab berechnen.

#### 5.2.4 Priorität und Auffangzweig

**Die Zweige werden von oben nach unten durchprobiert, der erste Treffer gewinnt.** Das offizielle Beispiel:

```python
g.decision()
 .branch(g.match(TypeExpression[int], matches=lambda x: x >= 5).to(branch_a))
 .branch(g.match(TypeExpression[int], matches=lambda x: x >= 0).to(branch_b))
```

Bei der Eingabe `10` treffen beide Zweige zu, genommen wird aber `branch_a` (der zuerst geschriebene).

**Der Auffangzweig wird zuletzt geschrieben:**

```python
.branch(g.match(TypeExpression[object]).to(catch_all))
```

Oder ein Zweig desselben Typs ohne `matches` (das `isinstance` trifft immer zu):

```python
.branch(g.match(TypeExpression[int], matches=lambda x: x >= 5).to(branch_a))
.branch(g.match(TypeExpression[int]).to(branch_b))   # ← alle übrigen int landen hier
```

> ⚠️ **Fallstrick**: **Kein Auffangzweig + eine Eingabe, die auf keinen Zweig passt = zur Laufzeit ein `RuntimeError: No branch matched inputs ...`**. Und dieser Fehler lässt sich beim `build()` nicht entdecken.
>
> Sicheres Vorgehen: **Schreiben Sie bei jeder Decision als letzte Zeile einen Auffangzweig**, selbst wenn dessen Ziel nur ein Step ist, der „die Anomalie protokolliert und an einen Menschen übergibt".

> 👉 **CEO-Perspektive**: Das ist der **else-Zweig**, der bei Anforderungsprüfungen am häufigsten übersehen wird. Im PRD steht häufig „Betrag <1000 → A, >5000 → B", und der Bereich zwischen 1000 und 5000 wurde vergessen. In dieser Bibliothek wird aus so einer Lücke ein **Absturz zur Laufzeit in Produktion**, kein stilles Abbiegen in den falschen Zweig. In einem gewissen Sinne ist das gut — das Problem tritt sofort zutage.
>
> Empfehlung für die Checkliste der Prozessprüfung: **Sind bei jedem Entscheidungsknoten alle Fälle abgedeckt? Wohin führt der Auffangzweig?**

#### 5.2.5 Matching nach Knotentyp: `g.match_node()`

Wenn der durchfließende Wert eine `BaseNode`-Instanz ist, verwenden Sie `g.match_node(SomeNode)` — die Kurzform von `g.match(SomeNode).to(SomeNode)`:

```python
g.decision()
 .branch(g.match_node(Approve))
 .branch(g.match_node(Reject))
```

⚠️ Beachten Sie aber den in 3.7 beschriebenen Fallstrick: Lautet die Rückgabeannotation des vorgelagerten Steps bereits `Approve | Reject`, greift die automatisch erzeugte Platzhalter-Decision zuerst und wirft einen Fehler. `match_node` ist deshalb vor allem für Fälle gedacht, in denen **die Rückgabeannotation des vorgelagerten Knotens keine Knoten-Union ist**.

#### 5.2.6 Verschachtelte Verzweigungen

Decisions lassen sich hintereinanderschalten und bilden so mehrstufige Entscheidungen:

```python
import asyncio
from pydantic_graph import GraphBuilder, StepContext, TypeExpression

g = GraphBuilder(input_type=int, output_type=str)


@g.step
async def get_amount(ctx: StepContext[None, None, int]) -> int:
    return ctx.inputs


@g.step
async def need_approval(ctx: StepContext[None, None, int]) -> int:
    return ctx.inputs


@g.step
async def auto_pass(ctx: StepContext[None, None, int]) -> str:
    return f'{ctx.inputs} 元自动通过'


@g.step
async def lead(ctx: StepContext[None, None, int]) -> str:
    return f'{ctx.inputs} 元组长审批'


@g.step
async def director(ctx: StepContext[None, None, int]) -> str:
    return f'{ctx.inputs} 元总监审批'


g.add(
    g.edge_from(g.start_node).to(get_amount),
    # Erste Ebene: Freigabe erforderlich oder nicht
    g.edge_from(get_amount).to(
        g.decision(note='500 以下免审')
        .branch(g.match(TypeExpression[int], matches=lambda x: x < 500).label('免审').to(auto_pass))
        .branch(g.match(TypeExpression[int]).label('需审批').to(need_approval))
    ),
    # Zweite Ebene: wer die Freigabe erteilt
    g.edge_from(need_approval).to(
        g.decision(note='5000 以上升总监')
        .branch(g.match(TypeExpression[int], matches=lambda x: x < 5000).label('组长').to(lead))
        .branch(g.match(TypeExpression[int]).label('总监').to(director))
    ),
    g.edge_from(auto_pass, lead, director).to(g.end_node),
)
graph = g.build()


async def main():
    for a in (100, 2000, 90000):
        print(a, '->', await graph.run(inputs=a))
```

Reale Ausgabe:

```text
100 -> 100 元自动通过
2000 -> 2000 元组长审批
90000 -> 90000 元总监审批
```

Ausgabe von `render()` (zwei Rauten, `decision` und `decision_2`, jeweils mit eigener Anmerkung):

```text
stateDiagram-v2
  get_amount
  state decision <<choice>>
  note right of decision
    500 以下免审
  end note
  auto_pass
  need_approval
  state decision_2 <<choice>>
  note right of decision_2
    5000 以上升总监
  end note
  director
  lead

  [*] --> get_amount
  get_amount --> decision
  decision --> auto_pass: 免审
  decision --> need_approval: 需审批
  auto_pass --> [*]
  need_approval --> decision_2
  decision_2 --> director: 总监
  decision_2 --> lead: 组长
  director --> [*]
  lead --> [*]
```

> 👉 **CEO-Perspektive**: Dieses Diagramm ist unmittelbar eine klassische Freigabematrix. Beachten Sie den Zwischenschritt `need_approval` — er tut selbst überhaupt nichts (er gibt den Wert lediglich unverändert zurück), aber seine bloße Existenz gibt der zweiten Entscheidungsebene einen „Aufhängepunkt". Das entspricht genau dem Vorgehen, im Backend eines Freigabe-Workflows einen „leeren Knoten" einzufügen, um eine Verzweigung aufzunehmen.

#### 5.2.7 Anmerkungen und Beschriftungen

Zwei Parameter, die ausschließlich der Visualisierung dienen:

| Parameter | Position | Wird gerendert als |
|---|---|---|
| `g.decision(note='...')` | An der Decision | `note right of decision \n ... \n end note` |
| `.label('...')` | Am Verzweigungspfad | `decision --> Ziel: Label` |
| `g.decision(node_id='...')` | An der Decision | Überschreibt die Standard-IDs `decision` / `decision_2` |

> 👉 **CEO-Perspektive**: `note` ist der Ort, an dem Sie das „Warum" einer Geschäftsregel festhalten, `label` der Ort, an dem ein Zweig einen „fachlichen Namen" bekommt. Beides kostet praktisch nichts, verwandelt das von `render()` erzeugte Diagramm aber von „für Entwickler verständlich" in „für die Fachabteilung verständlich". **Das ist die einzige Anforderung, die ein CEO im Zusammenhang mit dieser Bibliothek direkt an die Entwickler stellen muss.**

### 5.3 Schleifen

Für Schleifen braucht es keine besondere API — **eine Kante, die auf einen vorgelagerten Knoten zurückzeigt, ist bereits eine Schleife**.

```python
import asyncio
from dataclasses import dataclass, field
from pydantic_graph import GraphBuilder, StepContext, TypeExpression


@dataclass
class Draft:
    topic: str
    round: int
    score: int


@dataclass
class DraftState:
    history: list[str] = field(default_factory=list)


g = GraphBuilder(state_type=DraftState, input_type=str, output_type=str)


@g.step
async def start(ctx: StepContext[DraftState, None, str]) -> Draft:
    return Draft(topic=ctx.inputs, round=0, score=0)


@g.step
async def write(ctx: StepContext[DraftState, None, Draft]) -> Draft:
    d = ctx.inputs
    new = Draft(topic=d.topic, round=d.round + 1, score=d.score + 40)
    ctx.state.history.append(f'写第{new.round}稿, 评分{new.score}')
    return new


@g.step
async def publish(ctx: StepContext[DraftState, None, Draft]) -> str:
    return f'《{ctx.inputs.topic}》第{ctx.inputs.round}稿发布, 评分{ctx.inputs.score}'


g.add(
    g.edge_from(g.start_node).to(start),
    g.edge_from(start).to(write),
    g.edge_from(write).to(
        g.decision(note='评分 >= 80 才发布')
        .branch(g.match(TypeExpression[Draft], matches=lambda d: d.score >= 80)
                .label('达标').to(publish))
        .branch(g.match(TypeExpression[Draft]).label('回炉重写').to(write))   # ← zeigt zurück auf write
    ),
    g.edge_from(publish).to(g.end_node),
)

graph = g.build()


async def main():
    st = DraftState()
    print(await graph.run(state=st, inputs='2026 年产品路线图'))
    print(st.history)
```

Reale Ausgabe:

```text
《2026 年产品路线图》第2稿发布, 评分80
['写第1稿, 评分40', '写第2稿, 评分80']
```

Ausgabe von `render()`:

```text
stateDiagram-v2
  start
  write
  state decision <<choice>>
  note right of decision
    评分 >= 80 才发布
  end note
  publish

  [*] --> start
  start --> write
  write --> decision
  decision --> write: 回炉重写
  decision --> publish: 达标
  publish --> [*]
```

**Drei Dinge, auf die man bei Schleifen achten muss:**

| Punkt | Erläuterung |
|---|---|
| Es gibt keine eingebaute Obergrenze für Durchläufe | Eine nie erfüllte Bedingung = **Endlosschleife**. Sie müssen selbst einen Zähler in den Daten oder im state mitführen |
| Wo die Schleifenvariable liegt | **Im durchfließenden Wert** (im Beispiel `Draft.round`), denn `matches` hat keinen Zugriff auf den state |
| Jede Runde führt den Knoten vollständig neu aus | Es wird nicht „zum letzten Stand zurückgekehrt", der Knoten läuft tatsächlich noch einmal komplett durch |

> ⚠️ **Fallstrick**: Setzen Sie unbedingt eine Rundenobergrenze. Das obige Beispiel lässt sich so erweitern:
> ```python
> .branch(g.match(TypeExpression[Draft], matches=lambda d: d.round >= 5)
>         .label('超过5轮强制发布').to(publish))
> ```
> Vor den „Neuschreiben"-Zweig gesetzt, wirkt das als Sicherung.

> 👉 **CEO-Perspektive**: Das ist die **Überarbeitungsschleife** — Text schreiben → prüfen → durchgefallen → neu schreiben → erneut prüfen. Im Produktdesign müssen zwei Fragen beantwortet werden: **Wie viele Runden maximal? Und was geschieht, wenn es auch in der letzten Runde nicht durchgeht?** Werden diese Fragen nicht beantwortet, läuft in Produktion eine Endlosschleife, die Geld verbrennt (jede Runde bedeutet einen weiteren LLM-Aufruf).

### 5.4 Paralleles Fan-out: Broadcast

**Dieselben Daten gleichzeitig an mehrere nachgelagerte Knoten senden.**

Die Schreibweise besteht schlicht darin, `.to()` mehrere Ziele zu übergeben:

```python
g.edge_from(intake).to(risk_check, credit_check, blacklist_check)
```

Ein vollständiges Beispiel — die drei parallelen Prüfungen bei einer Kontoeröffnung:

```python
import asyncio
from dataclasses import dataclass
from pydantic_graph import GraphBuilder, StepContext, reduce_dict_update


@dataclass
class S:
    pass


g = GraphBuilder(state_type=S, input_type=str, output_type=dict[str, str])


@g.step
async def intake(ctx: StepContext[S, None, str]) -> str:
    return ctx.inputs


@g.step
async def risk_check(ctx: StepContext[S, None, str]) -> dict[str, str]:
    await asyncio.sleep(0.02)
    return {'风控': f'{ctx.inputs} 无异常'}


@g.step
async def credit_check(ctx: StepContext[S, None, str]) -> dict[str, str]:
    await asyncio.sleep(0.01)
    return {'征信': f'{ctx.inputs} 分数 720'}


@g.step
async def blacklist_check(ctx: StepContext[S, None, str]) -> dict[str, str]:
    return {'黑名单': f'{ctx.inputs} 不在名单内'}


merge = g.join(reduce_dict_update, initial_factory=dict[str, str])

g.add(
    g.edge_from(g.start_node).to(intake),
    g.edge_from(intake).to(risk_check, credit_check, blacklist_check),   # ← Broadcast
    g.edge_from(risk_check, credit_check, blacklist_check).to(merge),    # ← Zusammenführung
    g.edge_from(merge).to(g.end_node),
)

kyc_graph = g.build()


async def main():
    result = await kyc_graph.run(state=S(), inputs='用户9527')
    print({k: result[k] for k in sorted(result)})
```

Reale Ausgabe:

```text
{'征信': '用户9527 分数 720', '风控': '用户9527 无异常', '黑名单': '用户9527 不在名单内'}
```

Ausgabe von `render()` (beachten Sie den automatisch erzeugten `broadcast`-Fork-Knoten):

```text
stateDiagram-v2
  intake
  state broadcast <<fork>>
  blacklist_check
  credit_check
  risk_check
  state reduce_dict_update <<join>>

  [*] --> intake
  intake --> broadcast
  broadcast --> blacklist_check
  broadcast --> credit_check
  broadcast --> risk_check
  blacklist_check --> reduce_dict_update
  credit_check --> reduce_dict_update
  risk_check --> reduce_dict_update
  reduce_dict_update --> [*]
```

**Beachten Sie: Den Knoten `broadcast` haben Sie nicht geschrieben, er wurde beim `build()` automatisch eingefügt.** In Mermaid wird er als `<<fork>>` gerendert (ein dicker Querbalken).

Es gibt außerdem die explizitere Schreibweise `.broadcast()` für den Fall, dass jeder Nebenstrang eine eigene Behandlung braucht (etwa jeweils eigene Beschriftungen oder Transformationen):

```python
g.edge_from(source).broadcast(lambda b: [
    b.label('走风控').to(risk_check),
    b.label('走征信').to(credit_check),
])
```

> 👉 **CEO-Perspektive**: Broadcast = **parallele Freigabe**. Drei Abteilungen prüfen dieselben Unterlagen gleichzeitig, ohne Warteschlange. Der Produktnutzen ist unmittelbar: dreimal seriell zu je 2 Sekunden = 6 Sekunden, parallel = 2 Sekunden.
>
> Umgekehrt sollten Sie an jeder seriellen Stelle die Frage stellen: **„Ginge das auch parallel?"** Die Wartezeit der Nutzer ist eine Produktkennzahl, und diese Bibliothek macht Parallelität nahezu kostenlos (eine Zeile ändern: `.to(A, B, C)`).

### 5.5 Paralleles Fan-out: Mapping

**Eine Liste, und für jedes Element wird eine parallele Aufgabe gestartet.**

Geschrieben wird das, indem man ein `.map()` in die Kante einfügt:

```python
g.edge_from(split_items).map().to(review_one)
```

Ein vollständiges Beispiel — Texte im Batch prüfen:

```python
import asyncio
from dataclasses import dataclass, field
from pydantic_graph import GraphBuilder, StepContext, reduce_list_append


@dataclass
class ReviewState:
    reviewed: list[str] = field(default_factory=list)


g = GraphBuilder(state_type=ReviewState, input_type=list[str], output_type=list[str])


@g.step
async def split_items(ctx: StepContext[ReviewState, None, list[str]]) -> list[str]:
    return ctx.inputs


@g.step
async def review_one(ctx: StepContext[ReviewState, None, str]) -> str:
    await asyncio.sleep(0.01)
    ctx.state.reviewed.append(ctx.inputs)
    return f'{ctx.inputs}: 通过'


collect = g.join(reduce_list_append, initial_factory=list[str])

g.add(
    g.edge_from(g.start_node).to(split_items),
    g.edge_from(split_items).map().to(review_one),   # ← Fan-out
    g.edge_from(review_one).to(collect),
    g.edge_from(collect).to(g.end_node),
)

review_graph = g.build()


async def main():
    state = ReviewState()
    result = await review_graph.run(state=state, inputs=['文案A', '文案B', '文案C'])
    print(sorted(result))
    print(sorted(state.reviewed))
```

Reale Ausgabe:

```text
['文案A: 通过', '文案B: 通过', '文案C: 通过']
['文案A', '文案B', '文案C']
```

Ausgabe von `render()`:

```text
stateDiagram-v2
  split_items
  state map <<fork>>
  review_one
  state reduce_list_append <<join>>

  [*] --> split_items
  split_items --> map
  map --> review_one
  review_one --> reduce_list_append
  reduce_list_append --> [*]
```

**Der Unterschied zwischen `map` und `broadcast`:**

| | `.map()` | `.to(A, B, C)` / `.broadcast()` |
|---|---|---|
| Die Eingabe muss sein | Ein iterierbares Objekt (list / AsyncIterable) | Ein beliebiger Wert |
| Anzahl paralleler Aufgaben | = Länge der Liste (**erst zur Laufzeit bekannt**) | = Anzahl der Zielknoten (**bereits zur Bauzeit festgelegt**) |
| Jede Aufgabe erhält | Ein Element der Liste | Den vollständigen Originalwert |
| Nachgelagerte Knoten | Derselbe (es können auch mehrere sein, siehe 5.9) | Verschiedene |
| In Mermaid | `state map <<fork>>` | `state broadcast <<fork>>` |
| Analogie | Ein Stapel Bestellungen, pro Bestellung ein Bearbeitungsstrang | Ein Dokument, das drei Abteilungen gleichzeitig ansehen |

**`.map()` verarbeitet auch `AsyncIterable`**; in Kombination mit `@g.stream` ergibt das „erzeugen und gleichzeitig konsumieren" (siehe 3.5).

**Die Kurzform `g.add_mapping_edge()`:**

```python
g.add_mapping_edge(
    generate,
    process,
    pre_map_label='拆分前',      # Kantenbeschriftung vor dem map
    post_map_label='拆分后',     # Kantenbeschriftung nach dem map
    fork_id='my_fork',           # eigene ID für den Fork-Knoten
    downstream_join_id=collect.id,   # zu welchem Join bei leerer Liste gesprungen wird (siehe 5.8)
)
```

> 👉 **CEO-Perspektive**: map = **Nebenläufigkeit bei Massenaufgaben**. „Erzeuge für diese 500 Kunden je eine personalisierte E-Mail" — seriell braucht das 500 × 2 Sekunden = 16 Minuten, mit map sind es wenige Sekunden.
>
> Beachten Sie aber: **Der Nebenläufigkeitsgrad ist ungeregelt.** Es werden so viele Aufgaben gestartet, wie die Liste lang ist. 500 gleichzeitige Aufrufe gegen eine LLM-API laufen unmittelbar in eine Ratenbegrenzung. Die Bibliothek selbst kennt keinen Parameter für eine Obergrenze; wer drosseln will, muss innerhalb des Steps selbst ein Semaphor einbauen. **Das müssen Sie vor dem Produktivgang mit den Entwicklern klären.**

### 5.6 Paralleles Fan-in: `join` und Reducer

Auf ein Fan-out muss zwingend ein Fan-in folgen, sonst lassen sich die parallelen Ergebnisse nicht zusammenführen. Genau dafür gibt es `Join`.

#### 5.6.1 Die Grundform eines Join

```python
collect = g.join(reduce_list_append, initial_factory=list[str])

g.add(
    g.edge_from(review_one).to(collect),      # alle parallelen Aufgaben führen zum Join
    g.edge_from(collect).to(g.end_node),      # der Join gibt einen Wert aus, es geht weiter nach unten
)
```

Die Parameter von `g.join()`:

| Parameter | Pflicht | Erläuterung |
|---|---|---|
| `reducer` | ✅ | Die Zusammenführungsfunktion, Signatur `(current, inputs) -> current` oder `(ctx, current, inputs) -> current` |
| `initial=` oder `initial_factory=` | ✅ eines von beiden | Der Anfangswert des Akkumulators. **Für veränderliche Typen (list/dict) ist zwingend `initial_factory` zu verwenden**, sonst vermischen sich Daten zwischen mehreren Runs |
| `node_id=` | ❌ | Eigene ID, standardmäßig aus dem Namen der Reducer-Funktion abgeleitet |
| `parent_fork_id=` | ❌ | Legt von Hand fest, zu welchem Fork dieser Join gehört |
| `preferred_parent_fork=` | ❌ | `'farthest'` (Standard) oder `'closest'`, dient bei verschachtelten Forks der Auflösung von Mehrdeutigkeiten |

**Die Arbeitsweise eines Join** (Übersetzung aus der offiziellen Dokumentation):

1. Den eigenen „Eltern-Fork" ermitteln (welches Fan-out diese parallelen Aufgaben erzeugt hat)
2. Warten, bis alle von diesem Fork erzeugten Aufgaben eingetroffen sind
3. Bei jedem eintreffenden Wert einmal `reducer(current, neuer Wert)` aufrufen
4. Sind alle da, wird das akkumulierte Ergebnis nach unten weitergegeben

> ⚠️ **Fallstrick**: `initial=[]` und `initial_factory=list` sind **grundverschieden**. Bei Ersterem teilen sich alle Runs **dasselbe** list-Objekt (der zweite Durchlauf schleppt die Daten des ersten mit), bei Letzterem wird pro Run ein neues erzeugt. **Für veränderliche Typen immer `initial_factory`.**

#### 5.6.2 Die sechs eingebauten Reducer

| Reducer | Signatur | Anfangswert | Wirkung | Analogie |
|---|---|---|---|---|
| `reduce_list_append` | `(list[T], T) -> list[T]` | `initial_factory=list` | Hängt jedes Ergebnis an die Liste an | Die Antworten aller Beteiligten einsammeln |
| `reduce_list_extend` | `(list[T], Iterable[T]) -> list[T]` | `initial_factory=list` | Jedes Ergebnis ist selbst eine Liste, wird flach zusammengeführt | Mehrere Namenslisten zusammenführen |
| `reduce_dict_update` | `(dict, Mapping) -> dict` | `initial_factory=dict` | Wörterbücher zusammenführen | Jede Abteilung füllt eine andere Spalte desselben Formulars |
| `reduce_sum` | `(N, N) -> N` | `initial=0` | Summenbildung (für jeden Typ, der `+` unterstützt) | Beträge aufsummieren |
| `reduce_null` | `(None, Any) -> None` | `initial=None` | Verwirft alles, es zählen nur die Seiteneffekte | Es interessiert nur, dass „alle fertig sind" |
| `ReduceFirstValue[T]()` | `(ctx, T, T) -> T` | `initial=None` | Nimmt das zuerst eintreffende Ergebnis und **bricht alle übrigen Aufgaben ab** | Wer zuerst drückt / Wettlauf |

Praktisch verifiziert (vier auf einmal):

```python
print('reduce_sum       ->', await gg1.run(inputs=[10, 20, 30, 40]))
print('reduce_list_extend ->', sorted(await gg2.run(inputs=[1, 2, 3])))
print('ReduceFirstValue ->', await gg3.run(inputs=[1, 5, 9]))
```

```text
reduce_sum       -> 100
reduce_list_extend -> [0, 0, 0, 1, 1, 2]
ReduceFirstValue -> 供应商1先报价
```

(Im Beispiel zu `reduce_list_extend` gibt jede Aufgabe `list(range(n))` zurück: 1→`[0]`, 2→`[0,1]`, 3→`[0,1,2]`; flach zusammengeführt und sortiert ergibt das `[0,0,0,1,1,2]`.)

**`ReduceFirstValue` hat den größten Produktnutzen** — „mehrere treten gegeneinander an, der Schnellste gewinnt". Im obigen Beispiel simulieren drei Lieferanten unterschiedliche Latenzen (0,1 s / 0,5 s / 0,9 s), der schnellste gewinnt, und **die beiden anderen Aufgaben werden unmittelbar abgebrochen** (es wird kein Geld verbrannt).

**Die typische Verwendung von `reduce_null`** — die parallelen Aufgaben schreiben lediglich in den state, ihr Rückgabewert interessiert nicht:

```python
@dataclass
class CounterState:
    total: int = 0


@g.step
async def accumulate(ctx: StepContext[CounterState, None, int]) -> int:
    ctx.state.total += ctx.inputs      # ← Seiteneffekt (Achtung: hier sicher, Begründung siehe unten)
    return ctx.inputs


ignore = g.join(reduce_null, initial=None)    # ← verwirft alle Rückgabewerte
# Erläuterung: In Abschnitt 4.2 wurde vor „Lesen-Ändern-Schreiben in parallelen Zweigen" gewarnt — warum ist das += hier sicher?
# Weil asyncio einen einzigen Thread nutzt und die Zeile `ctx.state.total += ctx.inputs` keinen await-Punkt enthält,
# kann sich keine andere Aufgabe dazwischenschieben. Sobald jedoch mittendrin ein await auftaucht (DB-Abfrage, API-Aufruf),
# gehen wirklich Updates verloren — dann muss der Reducer eines Join summieren, der state darf nicht direkt geändert werden.


@g.step
async def get_total(ctx: StepContext[CounterState, None, None]) -> int:
    return ctx.state.total             # ← aus dem state entnehmen


g.add(
    g.edge_from(g.start_node).to(generate),
    g.edge_from(generate).map().to(accumulate),
    g.edge_from(accumulate).to(ignore),
    g.edge_from(ignore).to(get_total),
    g.edge_from(get_total).to(g.end_node),
)
```

Reale Ausgabe (Eingabe `[1,2,3,4,5]`):

```text
reduce_null -> 15
```

`reduce_null` wirkt hier als **Synchronisationsbarriere**: „warten, bis alle parallelen Aufgaben durchgelaufen sind, und erst dann weitergehen".

> 👉 **CEO-Perspektive**: Der Reducer ist die **Zusammenführungsregel**. Bei ein und derselben „parallelen Freigabe durch drei Abteilungen" bestimmt die Zusammenführungsregel die fachliche Bedeutung:
> - `reduce_list_append` → drei Stellungnahmen einsammeln und alle behalten
> - `reduce_dict_update` → drei Abteilungen füllen unterschiedliche Spalten desselben Formulars
> - `ReduceFirstValue` → eine Zustimmung genügt (wer zuerst freigibt, entscheidet; der Rest wird zurückgezogen)
> - Eigener Reducer → Vetorecht (siehe unten)
>
> **Wenn im PRD eine parallele Freigabe steht, muss die Zusammenführungsregel ausdrücklich festgehalten werden**, sonst wählen die Entwickler einfach irgendeine.

#### 5.6.3 Eigener Reducer + `cancel_sibling_tasks()`

Ein Reducer hat zwei mögliche Signaturen, die Bibliothek erkennt sie automatisch an der Parameteranzahl:

```python
# Einfache Variante: 2 Parameter
def reduce_sum(current: int, inputs: int) -> int:
    return current + inputs

# Variante mit Kontext: 3 Parameter, kann state/deps lesen und Geschwisteraufgaben abbrechen
def reduce_find(ctx: ReducerContext[SearchState, None], current: str | None, inputs: str) -> str | None:
    ...
```

**Vollständiges Beispiel für „Vetorecht / Abbruch beim ersten Treffer":**

```python
import asyncio
from dataclasses import dataclass
from pydantic_graph import GraphBuilder, StepContext, ReducerContext


@dataclass
class SearchState:
    done: int = 0


def reduce_find(ctx: ReducerContext[SearchState, None], current: str | None, inputs: str) -> str | None:
    if current is not None:
        return current                  # bereits gefunden, spätere Ergebnisse ignorieren
    if '命中' in inputs:
        ctx.cancel_sibling_tasks()      # ← Treffer! Alle noch laufenden Geschwisteraufgaben abbrechen
        return inputs
    return None


g = GraphBuilder(state_type=SearchState, output_type=str | None)


@g.step
async def candidates(ctx: StepContext[SearchState, None, None]) -> list[str]:
    return ['渠道A', '渠道B', '渠道C命中', '渠道D', '渠道E']


@g.step
async def query(ctx: StepContext[SearchState, None, str]) -> str:
    await asyncio.sleep(0.1 if ctx.inputs not in {'渠道D', '渠道E'} else 1.0)
    ctx.state.done += 1
    return ctx.inputs


find = g.join(reduce_find, initial=None)

g.add(
    g.edge_from(g.start_node).to(candidates),
    g.edge_from(candidates).map().to(query),
    g.edge_from(query).to(find),
    g.edge_from(find).to(g.end_node),
)

graph = g.build()


async def main():
    st = SearchState()
    print('结果:', await graph.run(state=st))
    print('实际执行的查询数:', st.done)
```

Reale Ausgabe:

```text
结果: 渠道C命中
实际执行的查询数: 3
```

**Fünf Kandidatenkanäle, tatsächlich ausgeführt wurden nur drei** — nachdem das Ziel gefunden war, wurden die beiden verbliebenen langsamen Aufgaben abgebrochen.

Was `ReducerContext` bietet:

| Element | Erläuterung |
|---|---|
| `.state` | Der Zustand des Graphen (les- und schreibbar) |
| `.deps` | Die Abhängigkeiten des Graphen |
| `.cancel_sibling_tasks()` | Bricht alle übrigen parallelen Aufgaben desselben Forks ab |

**Ein Reducer darf auch in den state schreiben**, das offizielle Beispiel (praktisch verifiziert):

```python
def reduce_metrics_sum(ctx: ReducerContext[MetricsState, None],
                       current: ReducedMetrics, inputs: int) -> ReducedMetrics:
    ctx.state.total_count += 1        # ← globaler Zähler
    ctx.state.total_sum += inputs
    return ReducedMetrics(count=current.count + 1, sum=current.sum + inputs)
```

In Kombination mit dem dreistufigen Join „nach gerade/ungerade verzweigen → jeweils reduzieren → erneut reduzieren und das Maximum nehmen" lautet die reale Ausgabe:

```text
Result: ReducedMetrics(count=5, sum=200)
state.total_count: 9
state.total_sum: 275
```

Ausgabe von `render()` (drei `<<join>>`):

```text
stateDiagram-v2
  generate
  state map <<fork>>
  state decision <<choice>>
  process_even
  process_odd
  state metrics_even <<join>>
  state metrics_odd <<join>>
  state metrics_max <<join>>

  [*] --> generate
  generate --> map
  map --> decision
  decision --> process_even: 偶数
  decision --> process_odd: 奇数
  process_even --> metrics_even
  process_odd --> metrics_odd
  metrics_even --> metrics_max
  metrics_odd --> metrics_max
  metrics_max --> [*]
```

> 👉 **CEO-Perspektive**: `cancel_sibling_tasks()` ist der **Sparschalter**. Das Szenario: Drei verschiedene Modelle beantworten dieselbe Frage gleichzeitig, wer zuerst eine brauchbare Antwort liefert, gewinnt, der Rest wird sofort abgewürgt. Ohne Abbruch zahlen Sie alle drei Aufrufe voll; mit Abbruch zahlen Sie ungefähr etwas mehr als einen.
>
> Bei Entwürfen wie „Absicherung über mehrere Modelle" oder „Preisvergleich über mehrere Anbieter" gilt: **Fragen Sie die Entwickler unbedingt, ob die langsamen Anfragen abgebrochen werden.**

### 5.7 Transformation auf der Kante: `.transform()`

Manchmal passt das Ausgabeformat des vorgelagerten Knotens nicht zu dem, was der nachgelagerte erwartet, und einen eigenen Step dafür zu schreiben wäre zu schwerfällig. `.transform()` erlaubt Ihnen eine Umwandlung **direkt auf der Kante**:

```python
g.edge_from(fetch_orders)
 .transform(lambda ctx: [o['id'] for o in ctx.inputs])    # die IDs herausziehen
 .label('取出订单号')
 .map()                                                    # dann Fan-out
 .to(notify)
```

Real ausgeführt (Eingabe `[{'id': 101, 'amount': 30}, {'id': 102, 'amount': 80}]`):

```text
['已通知订单 101', '已通知订单 102']
```

Ausgabe von `render(title='订单通知流程', direction='LR')`:

```text
---
title: 订单通知流程
---
stateDiagram-v2
  direction LR
  fetch_orders
  state map <<fork>>
  notify
  state reduce_list_append <<join>>

  [*] --> fetch_orders
  fetch_orders --> map: 取出订单号
  map --> notify
  notify --> reduce_list_append
  reduce_list_append --> [*]
```

Die Signatur der Funktion von `.transform()` lautet `(StepContext) -> neuer Wert`. Zu beachten:

| Eigenschaft | Erläuterung |
|---|---|
| Der Parameter ist ein `StepContext` | Deshalb sind `ctx.state` / `ctx.deps` / `ctx.inputs` lesbar |
| **Es ist eine synchrone Funktion** | Kein async, darin ist kein `await` möglich |
| Erzeugt keinen Graphknoten | In Mermaid nicht sichtbar, die Transformation ist „unsichtbar" |
| Lässt sich verketten | `.transform().label().map().to()` |

Übersicht der auf Kanten verfügbaren Kettenmethoden:

| Methode | Wirkung | Erzeugt einen Knoten? |
|---|---|---|
| `.to(A)` / `.to(A, B, C)` | Legt das Ziel fest (mehrere = Broadcast) | Bei mehreren Zielen entsteht ein `<<fork>>` |
| `.map(fork_id=, downstream_join_id=)` | Fan-out | Erzeugt ein `<<fork>>` |
| `.broadcast(lambda b: [...], fork_id=)` | Explizites Broadcast, jeder Nebenstrang separat konfigurierbar | Erzeugt ein `<<fork>>` |
| `.transform(func)` | Daten umwandeln | ❌ Erzeugt keinen |
| `.label('...')` | Beschriftet die Kante | ❌ Erzeugt keinen |

> ⚠️ **Fallstrick**: `.transform()` ist synchron. Wenn Sie ein `await` brauchen (Datenbankabfrage, API-Aufruf), müssen Sie ordentlich einen `@g.step` schreiben.

> 👉 **CEO-Perspektive**: transform ist **Formatanpassung**, keine Geschäftslogik. Das Kriterium: Wenn diese Umwandlung ins PRD gehört, von der Fachabteilung bestätigt werden muss oder sich ändern kann, dann sollte sie ein benannter Step sein (nur dann taucht sie im Flussdiagramm auf). Handelt es sich nur um technischen Klebstoff wie „die IDs aus dem dict herausziehen", nehmen Sie transform und verschmutzen das Flussdiagramm nicht.

### 5.8 Der Fallstrick leerer Collections: `downstream_join_id`

Was passiert bei `.map()` auf eine **leere Liste**? Es wird keine einzige parallele Aufgabe erzeugt, der nachgelagerte Join **wartet folglich ewig, und dieser gesamte Nebenstrang wird übersprungen**.

Die Lösung besteht darin, dem map mitzuteilen: „Wenn ich leer bin, springe direkt zu diesem Join":

```python
collect2 = g2.join(reduce_list_append, initial_factory=list[str])

g2.add(g2.edge_from(g2.start_node).to(fetch_nothing))
g2.add_mapping_edge(fetch_nothing, handle, downstream_join_id=collect2.id)   # ← entscheidend
g2.add(
    g2.edge_from(handle).to(collect2),
    g2.edge_from(collect2).to(g2.end_node),
)
```

Reale Ausgabe:

```text
[]
```

Es wird korrekt eine leere Liste geliefert, statt einen `RuntimeError` zu werfen.

Bei der Kettenschreibweise mit `.map()` lässt sich derselbe Parameter übergeben:

```python
g.edge_from(source).map(downstream_join_id=collect.id).to(handle)
```

> ⚠️ **Fallstrick**: Das ist ein Problem, das **extrem leicht übersehen wird und sich in der Testumgebung nur schwer reproduzieren lässt**. Während der Entwicklung enthält die Liste immer Daten, und nach dem Produktivgang bricht es beim ersten Nutzer, der „nicht eine einzige Bestellung hat", zusammen.
>
> **Regel: Sobald eine Kante ein `.map()` enthält, tragen Sie `downstream_join_id` ein.** Das kostet nichts und erspart einen Produktionsvorfall.

> 👉 **CEO-Perspektive**: Das ist der klassische Fall „**der Leerzustand wurde nicht bedacht**". Ein CEO kann in der Prüfung einfach fragen: „Was passiert bei dieser Massenverarbeitung, wenn kein einziger Datensatz vorliegt?" In dieser Bibliothek lautet die Antwort entweder „`downstream_join_id` ist gesetzt, es kommt regulär eine leere Menge zurück" oder „nicht gesetzt — **bei einfachen Graphen fliegt direkt ein `RuntimeError: Graph run completed, but no result was produced`; bei mehrzweigigen Graphen ist es schlimmer: Die Daten dieses Nebenstrangs werden stillschweigend verworfen, das Ergebnis stimmt nicht, aber es gibt keine Fehlermeldung**". Letzteres ist der wirklich gefährliche Fall.

### 5.9 Verschachtelte Parallelität

Forks lassen sich verschachteln; die Bibliothek verfolgt automatisch, zu welcher Fork-Ebene eine Aufgabe gehört (intern `fork_stack` genannt).

**Nach einem map ein broadcast** — jedes Element geht an zwei nachgelagerte Knoten:

```python
g.edge_from(gen2).map().to(add_one, add_two)
```

Eingabe `[10, 20]`, reale Ausgabe:

```text
[11, 12, 21, 22]
```

(10→11, 10→12, 20→21, 20→22, insgesamt vier parallele Aufgaben.)

Ausgabe von `render()` (zwei hintereinandergeschaltete Forks):

```text
stateDiagram-v2
  gen2
  state map <<fork>>
  state broadcast <<fork>>
  add_one
  add_two
  state reduce_list_append <<join>>

  [*] --> gen2
  gen2 --> map
  map --> broadcast
  broadcast --> add_one
  broadcast --> add_two
  add_one --> reduce_list_append
  add_two --> reduce_list_append
  reduce_list_append --> [*]
```

**Zwei map hintereinander** — eine Liste von Listen:

```python
g3.edge_from(pairs).map().to(unpack)        # [(1,2),(3,4)] → 2 Aufgaben
g3.edge_from(unpack).map().to(stringify)    # jedes Tupel zerfällt in 2 → insgesamt 4 Aufgaben
```

Reale Ausgabe:

```text
['num:1', 'num:2', 'num:3', 'num:4']
```

Ausgabe von `render()` (`map` und `map_2`):

```text
stateDiagram-v2
  pairs
  state map <<fork>>
  unpack
  state map_2 <<fork>>
  stringify
  state reduce_list_append <<join>>

  [*] --> pairs
  pairs --> map
  map --> unpack
  unpack --> map_2
  map_2 --> stringify
  stringify --> reduce_list_append
  reduce_list_append --> [*]
```

> 👉 **CEO-Perspektive**: Verschachtelte Parallelität = „**für jede Filiale jede Artikelnummer einmal durchrechnen**". Die Aufgabenzahl wächst multiplikativ (10 Filialen × 200 Artikelnummern = 2000 parallele Aufgaben) und **gerät sehr leicht außer Kontrolle**. Verlangen Sie bei solchen Anforderungen unbedingt von den Entwicklern eine Obergrenze für die Nebenläufigkeit sowie eine Schätzung von Laufzeit und Kosten.

### 5.10 Mehrere unabhängige Joins

Ein Graph kann mehrere voneinander unabhängige Joins enthalten, unterschieden über `node_id=`:

```python
join_t = g.join(reduce_list_append, initial_factory=list[int], node_id='join_tmall')
join_j = g.join(reduce_list_append, initial_factory=list[int], node_id='join_jd')
```

Ein vollständiges Beispiel — Preisvergleich über zwei E-Commerce-Plattformen parallel:

```python
g.add(
    g.edge_from(g.start_node).to(crawl_tmall, crawl_jd),   # Broadcast: zwei Fließbänder
    g.edge_from(crawl_tmall).map().to(price_tmall),        # jeweils ein map
    g.edge_from(crawl_jd).map().to(price_jd),
    g.edge_from(price_tmall).to(join_t),                   # jeweils ein Join
    g.edge_from(price_jd).to(join_j),
    g.edge_from(join_t).to(store_t),
    g.edge_from(join_j).to(store_j),
    g.edge_from(store_t, store_j).to(report),              # Zusammenführung
    g.edge_from(report).to(g.end_node),
)
```

Reale Ausgabe:

```text
{'京东': [30, 60], '天猫': [2, 4, 6]}
```

Ausgabe von `render()`:

```text
stateDiagram-v2
  state broadcast <<fork>>
  crawl_jd
  crawl_tmall
  state map <<fork>>
  state map_2 <<fork>>
  price_jd
  price_tmall
  state join_jd <<join>>
  state join_tmall <<join>>
  store_j
  store_t
  report

  [*] --> broadcast
  broadcast --> crawl_jd
  broadcast --> crawl_tmall
  crawl_jd --> map_2
  crawl_tmall --> map
  map --> price_tmall
  map_2 --> price_jd
  price_jd --> join_jd
  price_tmall --> join_tmall
  join_jd --> store_j
  join_tmall --> store_t
  store_j --> report
  store_t --> report
  report --> [*]
```

> 💡 **Hinweis**: Wenn mehrere Joins denselben Reducer verwenden, hängt die Standard-ID automatisch ein Suffix an (`reduce_list_append`, `reduce_list_append_2`), **ein Fehler entsteht dabei nicht**. Im Diagramm ist dann aber nicht mehr erkennbar, welcher welcher ist — vergeben Sie deshalb besser von Hand fachlich sprechende `node_id`.

> 👉 **CEO-Perspektive**: Dieses Diagramm zeigt die Standardstruktur der **kanalübergreifenden Datenaggregation** — jeder Kanal erhebt und aggregiert eigenständig, am Ende wird alles zu einem Report zusammengeführt. Im Diagramm ist auf einen Blick erkennbar, dass die beiden Stränge vollständig voneinander isoliert sind; tritt ein Problem auf, lässt sich schnell eingrenzen, welcher Strang ausgefallen ist.

---

## 6. Ausführung beobachten und steuern

`graph.run()` ist eine Blackbox — hineinwerfen, auf das Ergebnis warten. Im realen Geschäftsbetrieb brauchen Sie jedoch häufig:

- Sichtbarkeit, an welchem Schritt der Prozess steht (Fortschrittsbalken, Audit-Log)
- Die Möglichkeit, vor einem bestimmten Schritt einzugreifen (manuelle Intervention, Rollout-Experiment)
- Einen alternativen Weg, wenn ein Schritt fehlschlägt (Degradierung, Übergabe an einen Menschen)
- Vorzeitiges Beenden (Sicherung, Timeout)

All das leisten `graph.iter()` und `GraphRun`. Dieser Abschnitt behandelt:

1. Die grundlegende Verwendung von `iter()`
2. Was `GraphRun` bietet
3. Mit `next_task` den nächsten Schritt vorab einsehen
4. Mit `override_next()` den nächsten Schritt umschreiben (manuelle Intervention)
5. Fehlerbehebung über `ErrorMarker`
6. Vorzeitige Sicherung über `EndMarker`

### 6.1 `iter()`: schrittweise Ausführung

```python
import asyncio
from dataclasses import dataclass
from pydantic_graph import GraphBuilder, StepContext


@dataclass
class CounterState:
    value: int = 0


g = GraphBuilder(state_type=CounterState, output_type=int)


@g.step
async def increment(ctx: StepContext[CounterState, None, None]) -> int:
    ctx.state.value += 1
    return ctx.state.value


@g.step
async def double_it(ctx: StepContext[CounterState, None, int]) -> int:
    return ctx.inputs * 2


g.add(
    g.edge_from(g.start_node).to(increment),
    g.edge_from(increment).to(double_it),
    g.edge_from(double_it).to(g.end_node),
)

graph = g.build()


async def main():
    state = CounterState()
    async with graph.iter(state=state) as run:
        print(f'开始前 state.value={state.value}')
        print(f'即将执行: {run.next_task}')
        async for event in run:
            print(f'state.value={state.value} | event={event}')
        print(f'最终输出: {run.output}')
```

Reale Ausgabe:

```text
开始前 state.value=0
即将执行: [GraphTask(node_id='__start__', inputs=None)]
state.value=0 | event=[GraphTask(node_id='increment', inputs=None)]
state.value=1 | event=[GraphTask(node_id='double_it', inputs=1)]
state.value=1 | event=[GraphTask(node_id='__end__', inputs=2)]
state.value=1 | event=EndMarker(_value=2)
最终输出: 2
```

**So liest man es**: Das `event`, das jedes `async for` liefert, ist die „**Menge der als Nächstes auszuführenden Aufgaben**", nicht „das Ergebnis des gerade abgeschlossenen Schritts".

- Erster Durchlauf: `[GraphTask(node_id='increment', ...)]` → der Startpunkt ist abgearbeitet, als Nächstes läuft `increment`
- Zweiter Durchlauf: `[GraphTask(node_id='double_it', inputs=1)]` → `increment` ist fertig und lieferte 1, als Nächstes läuft `double_it`
- Dritter Durchlauf: `[GraphTask(node_id='__end__', inputs=2)]` → als Nächstes der Endpunkt
- Vierter Durchlauf: `EndMarker(_value=2)` → Ende, die Ausgabe ist 2

Beachten Sie, dass `event` eine **Liste** ist — bei Parallelität stehen mehrere Aufgaben gleichzeitig zur Ausführung an.

> ⚠️ **Achtung**: `iter()` muss mit `async with` verwendet werden. Es ist ein asynchroner Kontextmanager, der beim Verlassen die interne Aufgabengruppe aufräumt.

> 👉 **CEO-Perspektive**: Das ist der **Echtzeitstatus einer Prozessinstanz**. Damit können Sie umsetzen:
> - Fortschrittsbalken im Frontend: „Identität wird geprüft (2/5)"
> - Audit-Logs: Zeitstempel, Eingaben und Ausgaben jedes Schritts landen in der Datenbank
> - Timeout-Alarme: Hängt ein Schritt 30 Sekunden, wird Alarm ausgelöst
>
> Im Blackbox-Modus von `graph.run()` sind diese Fähigkeiten nicht verfügbar.

### 6.2 Das `GraphRun`-Panel

| Element | Typ | Erläuterung |
|---|---|---|
| `.state` | `StateT` | Das Zustandsobjekt dieses Durchlaufs |
| `.deps` | `DepsT` | Die Abhängigkeiten dieses Durchlaufs |
| `.inputs` | `InputT` | Die ursprüngliche Eingabe |
| `.next_task` | `EndMarker \| ErrorMarker \| Sequence[GraphTask]` | **Was als Nächstes ausgeführt wird** (vor der Ausführung einsehbar) |
| `.output` | `OutputT \| None` | Nach dem Durchlauf das Ergebnis, davor `None` |
| `await .next(value=None)` | | Einen Schritt manuell weiterschalten, optional mit einem eingespeisten Wert |
| `.override_next(value)` | | **Den nächsten Schritt umschreiben** (die entscheidende Fähigkeit) |
| `async for x in run` | | Automatisch weiterschalten bis zum Ende |

Die Felder von `GraphTask`:

| Feld | Erläuterung |
|---|---|
| `.node_id` | Welcher Knoten laufen soll (String-ID) |
| `.inputs` | Die an ihn übergebenen Daten |
| `.fork_stack` | Intern genutzt, markiert die Zugehörigkeit zu einem Fork (im `repr` ausgeblendet) |
| `.task_id` | Die intern genutzte eindeutige Aufgaben-ID |

**Zwei Arten, die Ausführung anzutreiben:**

```python
# Variante 1: async for, automatisches Weiterschalten
async for event in run:
    ...

# Variante 2: await run.next(), manuelles Weiterschalten (Eingriff dazwischen möglich)
while True:
    try:
        event = await run.next()
    except StopAsyncIteration:
        break
    ...
```

Variante 2 ist umständlicher, aber nur sie lässt sich mit `override_next()` kombinieren.

### 6.3 `override_next()`: manuelle Intervention

**Szenario: Der Prozess würde eigentlich A nehmen, aber aufgrund bestimmter Laufzeitinformationen (Risikokontrolle, Rollout, menschlicher Eingriff) soll er stattdessen B nehmen.**

```python
import asyncio
from dataclasses import dataclass
from pydantic_graph import EndMarker, GraphBuilder, GraphTaskRequest, StepContext


@dataclass
class S:
    trail: list[str]


g = GraphBuilder(state_type=S, input_type=float, output_type=str)


@g.step
async def submit(ctx: StepContext[S, None, float]) -> float:
    ctx.state.trail.append('提交')
    return ctx.inputs


@g.step
async def auto_approve(ctx: StepContext[S, None, float]) -> str:
    ctx.state.trail.append('自动通过')
    return f'{ctx.inputs} 元自动通过'


@g.step
async def human_approve(ctx: StepContext[S, None, float]) -> str:
    ctx.state.trail.append('人工审批')
    return f'{ctx.inputs} 元人工批准'


g.add(
    g.edge_from(g.start_node).to(submit),
    g.edge_from(submit).to(auto_approve),
    g.edge_from(auto_approve).to(g.end_node),
    g.edge_from(human_approve).to(g.end_node),      # human_approve liegt nicht auf dem Hauptstrang
)

# ⚠️ human_approve ist vom Startpunkt aus nicht erreichbar, die Strukturprüfung muss abgeschaltet werden
graph = g.build(validate_graph_structure=False)


async def main():
    state = S(trail=[])
    async with graph.iter(state=state, inputs=8888.0) as run:
        while True:
            try:
                event = await run.next()
            except StopAsyncIteration:
                break
            print(f'event={event}')
            tasks = run.next_task
            if isinstance(tasks, list) and tasks and tasks[0].node_id == 'auto_approve':
                print('>>> 拦截: 金额太大，改走人工')
                run.override_next([
                    GraphTaskRequest(node_id='human_approve', inputs=tasks[0].inputs, fork_stack=())
                ])
            if run.output is not None:
                break
    print('输出:', run.output)
    print('轨迹:', state.trail)
```

Reale Ausgabe:

```text
event=[GraphTask(node_id='auto_approve', inputs=8888.0)]
>>> 拦截: 金额太大，改走人工
event=[GraphTask(node_id='__end__', inputs='8888.0 元人工批准')]
event=EndMarker(_value='8888.0 元人工批准')
输出: 8888.0 元人工批准
轨迹: ['提交', '人工审批']
```

**`auto_approve` wurde überhaupt nicht ausgeführt** — es wurde abgefangen und durch `human_approve` ersetzt.

Die drei Felder von `GraphTaskRequest`:

| Feld | Was einzutragen ist |
|---|---|
| `node_id` | Die ID des Zielknotens (Funktionsname eines Steps / Klassenname einer BaseNode / eigene `node_id`) |
| `inputs` | Die an ihn übergebenen Daten |
| `fork_stack` | Bei nicht parallelen Szenarien `()`; bei parallelen Szenarien muss der `fork_stack` der ursprünglichen Aufgabe übernommen werden, sonst wartet der Join vergeblich |

> ⚠️ **Fallstrick 1**: Ist der Zielknoten des Sprungs vom Startpunkt aus **nicht erreichbar** (wie oben `human_approve`), meldet `build()` unmittelbar einen Fehler:
>
> ```text
> GraphValidationError: The following nodes are not reachable from the start node:
> ['human_approve']. If this is intentional, you can suppress this error by passing
> `validate_graph_structure=False` to the call to `GraphBuilder.build`.
> ```
>
> Die Fehlermeldung selbst nennt die Lösung: `g.build(validate_graph_structure=False)`.

> ⚠️ **Fallstrick 2**: `override_next()` **darf nur zwischen zwei Iterationen aufgerufen werden**, nicht mitten in der Ausführung eines Schritts.

> 👉 **CEO-Perspektive**: Das ist die technische Grundlage für **Human-in-the-Loop**. Mögliche Produktausprägungen:
> - Großaufträge werden automatisch angehalten, bis jemand im Backend „genehmigen" klickt
> - KI-generierte Inhalte gehen zunächst in eine manuelle Prüfschlange und werden erst nach Freigabe veröffentlicht
> - A/B-Experiment: 5 % des Traffics werden an einem bestimmten Knoten in einen neuen Prozess umgeleitet
>
> Beachten Sie: Diese Bibliothek besitzt **keine eingebaute Fähigkeit für „anhalten, auf einen Menschen warten und Tage später fortsetzen"** (es gibt keine Persistenz, siehe Abschnitt 10). Möglich ist nur „abfangen und umleiten innerhalb desselben Prozesses und desselben Durchlaufs". Für ein echtes langes Aussetzen braucht es eine zusätzliche Lösung.

### 6.4 `ErrorMarker`: Fehlerbehebung

**Szenario: Ein Knoten wirft eine Ausnahme, aber der gesamte Prozess soll nicht zusammenbrechen, sondern einen Degradierungspfad nehmen.**

Der Ansatz dieser Bibliothek ist bemerkenswert: Wirft ein Knoten eine Ausnahme, wird sie nicht sofort nach oben weitergereicht, sondern **zunächst als `ErrorMarker` geyieldet**, was Ihnen eine Gelegenheit zur Übernahme gibt. Der Kommentar im Quelltext lautet wörtlich:

> "Yielded by the graph iterator instead of raising immediately, allowing the caller to recover by sending new tasks via `GraphRun.next()` or `GraphRun.override_next()`. **If the caller does not override, the error is re-raised on the next iteration.**"

Übersetzt: Der Fehler wird zunächst in einen `ErrorMarker` verpackt und Ihnen übergeben. Behandeln Sie ihn nicht, wird er bei der nächsten Iteration tatsächlich geworfen.

```python
import asyncio
from dataclasses import dataclass
from pydantic_graph import GraphBuilder, GraphTaskRequest, StepContext


@dataclass
class PayState:
    attempts: int = 0


g = GraphBuilder(state_type=PayState, input_type=str, output_type=str)


@g.step
async def call_gateway(ctx: StepContext[PayState, None, str]) -> str:
    ctx.state.attempts += 1
    raise RuntimeError(f'支付网关超时 (第 {ctx.state.attempts} 次)')


@g.step
async def manual_review(ctx: StepContext[PayState, None, str]) -> str:
    return f'{ctx.inputs} 转人工处理'


g.add(
    g.edge_from(g.start_node).to(call_gateway),
    g.edge_from(call_gateway).to(g.end_node),
    g.edge_from(manual_review).to(g.end_node),
)

graph = g.build(validate_graph_structure=False)


async def main():
    state = PayState()
    async with graph.iter(state=state, inputs='订单8888') as run:
        while True:
            try:
                event = await run.next()
            except StopAsyncIteration:
                break
            except RuntimeError as exc:                    # ← die vom Knoten geworfene Ausnahme wird hier gefangen
                print(f'捕获异常: {exc}')
                print(f'出错时的 next_task: {run.next_task}')
                run.override_next([                        # ← Umleitung auf den Degradierungspfad
                    GraphTaskRequest(node_id='manual_review', inputs='订单8888', fork_stack=())
                ])
                continue
            print(f'event={event}')
            if run.output is not None:
                print(f'最终输出: {run.output}')
                break
```

Reale Ausgabe:

```text
捕获异常: 支付网关超时 (第 1 次)
出错时的 next_task: ErrorMarker(error=RuntimeError('支付网关超时 (第 1 次)'))
event=[GraphTask(node_id='__end__', inputs='订单8888 转人工处理')]
event=EndMarker(_value='订单8888 转人工处理')
最终输出: 订单8888 转人工处理
```

**Die entscheidenden Punkte:**

| Punkt | Erläuterung |
|---|---|
| Die Ausnahme wird von `await run.next()` geworfen | Wird mit einem gewöhnlichen `try/except` gefangen |
| `run.next_task` wird zu `ErrorMarker(error=...)` | Daraus lässt sich das ursprüngliche Ausnahmeobjekt entnehmen |
| Art der Wiederherstellung | Im `except`-Block `override_next([...])` aufrufen, anschließend `continue` |
| Was geschieht ohne Wiederherstellung | Beim nächsten `next()` wird der Fehler erneut geworfen und der gesamte Run endet |
| Wie man einen **Retry** umsetzt | `override_next` auf **dieselbe** `node_id` ist bereits ein Retry. Die Zählung übernehmen Sie selbst |

> 👉 **CEO-Perspektive**: Das ist die technische Grundlage der **Degradierung im Fehlerfall**. Wenn im PRD steht „bei fehlgeschlagener Zahlung an einen Menschen übergeben", „bei fehlgeschlagener KI-Generierung auf eine Vorlage zurückfallen" oder „bei Timeout einer Drittanbieter-Schnittstelle zwischengespeicherte Daten verwenden", steckt jedes Mal dieser Mechanismus dahinter.
>
> In der Prüfung lohnt es sich, jeden Knoten einzeln zu hinterfragen: **„Was passiert, wenn dieser Schritt fehlschlägt? Wie viele Wiederholungen? Und wohin, wenn auch die nicht helfen?"** In dieser Bibliothek sind die Antworten auf diese drei Fragen genau die wenigen Zeilen im `except`-Block.

### 6.5 `EndMarker`: vorzeitige Sicherung

`override_next()` nimmt außer einer Aufgabenliste auch einen `EndMarker` entgegen, was bedeutet: „**nicht weiterlaufen, sondern unmittelbar mit diesem Wert enden**":

```python
import asyncio
from pydantic_graph import EndMarker, GraphBuilder, StepContext

g = GraphBuilder(input_type=int, output_type=str)


@g.step
async def s1(ctx: StepContext[None, None, int]) -> int:
    return ctx.inputs + 1


@g.step
async def s2(ctx: StepContext[None, None, int]) -> str:
    return f'走完了全流程, 值={ctx.inputs}'


g.add(
    g.edge_from(g.start_node).to(s1),
    g.edge_from(s1).to(s2),
    g.edge_from(s2).to(g.end_node),
)
graph = g.build()


async def main():
    async with graph.iter(inputs=1) as run:
        while True:
            try:
                event = await run.next()
            except StopAsyncIteration:
                break
            print('event =', event)
            tasks = run.next_task
            if isinstance(tasks, list) and tasks and tasks[0].node_id == 's2':
                print('>>> 提前熔断，不跑 s2 了')
                run.override_next(EndMarker('人工提前终止'))     # ← unmittelbar beenden
            if run.output is not None:
                break
        print('输出:', run.output)
```

Reale Ausgabe:

```text
event = [GraphTask(node_id='s2', inputs=2)]
>>> 提前熔断，不跑 s2 了
输出: 人工提前终止
```

`s2` ist kein einziges Mal gelaufen. Und falls zu diesem Zeitpunkt parallele Aufgaben liefen, **werden sie allesamt mit abgebrochen** (im Quelltext ruft der `EndMarker`-Zweig `task_group.cancel_scope.cancel()` auf).

> 👉 **CEO-Perspektive**: Die drei typischen Auslöser für eine Sicherung sind **Zeitüberschreitung, Budgetüberschreitung und manueller Stopp**.
> - Zeitüberschreitung: 30 Sekunden ohne Abschluss → Rückmeldung „in Bearbeitung, Sie werden benachrichtigt"
> - Budgetüberschreitung: Dieser Durchlauf hat bereits Token im Wert von 5 Einheiten verbrannt → Stopp
> - Manueller Stopp: Jemand hat im Backend auf „Abbrechen" geklickt
>
> Alle drei sind Produktanforderungen, und technisch sind sie ein und dasselbe `override_next(EndMarker(...))`.

### 6.6 Gegenüberstellung der drei Arten von Ausführungssteuerung

| Was ich will | Was ich verwende | Ergebnis |
|---|---|---|
| Nur den Fortschritt sehen, nicht eingreifen | `async for event in run` | Man erhält für jeden Schritt die Liste der `GraphTask` |
| Vor einem bestimmten Schritt umleiten | `run.next()`-Schleife + `override_next([GraphTaskRequest(...)])` | Der ursprünglich vorgesehene Knoten wird nicht ausgeführt, stattdessen der neue |
| Nach einem fehlgeschlagenen Schritt degradieren | `try/except` fangen + `override_next([...])` | Der Fehler wird geschluckt, der Degradierungspfad genommen |
| Sofort beenden | `override_next(EndMarker(Wert))` | Alle verbleibenden Aufgaben werden abgebrochen, `output` ist genau dieser Wert |
| Denselben Schritt wiederholen | `override_next([GraphTaskRequest(dieselbe node_id, ...)])` | Der Knoten läuft ein weiteres Mal |

---

## 7. Visualisierung: `render()`

In jedem der vorherigen Abschnitte war sie bereits im Einsatz, hier folgt die systematische Darstellung.

### 7.1 Grundlegende Verwendung

```python
mermaid_source: str = graph.render()
print(mermaid_source)

# oder noch kürzer
print(graph)      # Graph.__str__ ist genau render()
```

`render()` liefert einen **String** zurück (Mermaid-Quelltext im Format `stateDiagram-v2`). Es erzeugt kein Bild, schreibt keine Datei und geht nicht ins Netz — es ist schlicht ein Stück Text. Sie müssen diesen Text an eine beliebige Mermaid-fähige Stelle einfügen:

| Werkzeug | Unterstützung |
|---|---|
| Markdown auf GitHub / GitLab | ✅ Native Unterstützung für Mermaid-Codeblöcke (Sprachkennzeichnung `mermaid`) |
| Notion | ✅ Im Codeblock Mermaid auswählen |
| Kollaborative Dokumentenwerkzeuge | ✅ Unterstützt |
| VS Code | ✅ Erweiterung „Markdown Preview Mermaid Support" installieren |
| mermaid.live | ✅ Online einfügen und sofort rendern |

### 7.2 Die beiden Parameter

```python
graph.render(title='订单通知流程', direction='LR')
```

| Parameter | Werte | Wirkung |
|---|---|---|
| `title=` | Beliebiger String | Fügt am Anfang einen Titelblock als YAML-Front-Matter ein |
| `direction=` | `'TB'` / `'LR'` / `'RL'` / `'BT'` | Ausrichtung des Diagramms: oben-unten / links-rechts / rechts-links / unten-oben |

Reale Ausgabe:

```text
---
title: 订单通知流程
---
stateDiagram-v2
  direction LR
  fetch_orders
  state map <<fork>>
  notify
  state reduce_list_append <<join>>

  [*] --> fetch_orders
  fetch_orders --> map: 取出订单号
  map --> notify
  notify --> reduce_list_append
  reduce_list_append --> [*]
```

> 💡 Erfahrungswert: **Bei wenigen Knoten `TB` (Standard, oben-unten), bei vielen Knoten `LR` (links-rechts).** Eine vertikale Anordnung wird ab etwa zehn Knoten sehr lang; die horizontale passt besser zu Breitbildschirmen und Präsentationen.

### 7.3 Wie die verschiedenen Knotentypen in Mermaid aussehen

Diese Tabelle ist der Schlüssel zum Lesen der Diagramme:

| Diagrammelement | Mermaid-Syntax | Optik | Wofür es steht |
|---|---|---|---|
| Start / Ende | `[*]` | Ausgefüllter Kreis / konzentrische Kreise | `g.start_node` / `g.end_node` |
| Gewöhnlicher Schritt | `Knoten-ID` | Abgerundetes Rechteck | `@g.step` / `@g.stream` |
| Beschrifteter Schritt | `Knoten-ID: Label` | Abgerundetes Rechteck mit Beschriftung | `@g.step(label='...')` |
| BaseNode-Knoten | `Klassenname` | Abgerundetes Rechteck | Eine mit `g.node(X)` registrierte `BaseNode` |
| Entscheidung | `state Knoten-ID <<choice>>` | **Raute** | `g.decision()` oder automatisch aus einer Rückgabetyp-Union erzeugt |
| Erläuterung zur Entscheidung | `note right of Knoten-ID ... end note` | Notizzettel | `g.decision(note='...')` |
| Fan-out | `state Knoten-ID <<fork>>` | **Dicker Querbalken** | `.map()` / `.broadcast()` / `.to(A,B,C)` |
| Fan-in | `state Knoten-ID <<join>>` | **Dicker Querbalken** | `g.join(...)` |
| Kante | `A --> B` | Pfeil | Jede Verbindung |
| Beschriftete Kante | `A --> B: Label` | Pfeil + Text | `.label('...')` / `g.add_edge(..., label=)` |

**Benennungsschema der automatisch erzeugten Knoten-IDs:**

| Typ | Erster | Zweiter | Dritter |
|---|---|---|---|
| Entscheidung | `decision` | `decision_2` | `decision_3` |
| map-Fan-out | `map` | `map_2` | `map_3` |
| broadcast-Fan-out | `broadcast` | `broadcast_2` | ... |
| join | Name der Reducer-Funktion (etwa `reduce_list_append`) | Bei Konflikt manuell `node_id=` setzen | |

### 7.4 Ein „Familienfoto"-Diagramm

Alle bisherigen Elemente in einem Diagramm (dies ist die echte Ausgabe des Beispiels aus 5.6.3):

```text
stateDiagram-v2
  generate
  state map <<fork>>
  state decision <<choice>>
  process_even
  process_odd
  state metrics_even <<join>>
  state metrics_odd <<join>>
  state metrics_max <<join>>

  [*] --> generate
  generate --> map
  map --> decision
  decision --> process_even: 偶数
  decision --> process_odd: 奇数
  process_even --> metrics_even
  process_odd --> metrics_odd
  metrics_even --> metrics_max
  metrics_odd --> metrics_max
  metrics_max --> [*]
```

So liest man es: Startpunkt → `generate` erzeugt eine Liste → `map` fächert auf (eine Aufgabe pro Zahl) → `decision` prüft auf gerade/ungerade → jeweils eigene Verarbeitung → jeweils ein Join → noch einmal ein Join für das Maximum → Endpunkt.

### 7.5 Nebenbei: nachsehen, welche Knoten der Graph enthält

```python
for nid, node in graph.nodes.items():
    print(f'{nid:20} {type(node).__name__}')
```

```text
__start__            StartNode
profile              Step
make_copy            Step
__end__              EndNode
```

`graph.nodes` ist ein `dict[Knoten-ID, Knotenobjekt]` und eignet sich für automatisierte Prüfungen (etwa eine CI-Zusicherung, dass bestimmte Schlüsselknoten vorhanden sein müssen).

> 👉 **CEO-Perspektive**: Der größte Wert von `render()` liegt darin, **die Prozessdokumentation zu automatisieren**. Drei Dinge, die Sie vorantreiben sollten:
>
> 1. **Das Flussdiagramm in der CI automatisch aktualisieren**: Bei jedem Merge wird das Ergebnis von `render()` automatisch in das Dokumentations-Repository geschrieben. Das Flussdiagramm veraltet nie.
> 2. **Für jeden Knoten ein sprechendes `label` verlangen**: Das sind die einzigen Kosten, um aus einem Entwicklerdiagramm ein Geschäftsdiagramm zu machen.
> 3. **An entscheidenden Verzweigungspunkten ein `note` schreiben**: Die Geschäftsregel („1000 ist die Schwelle") steht damit im Diagramm und ist in der Prüfung sofort ersichtlich.
>
> Wenn Sie diese drei Punkte umsetzen, sind Ihr Prozess-PRD und die produktive Implementierung dauerhaft deckungsgleich — etwas, das in klassischen Entwicklungsprozessen nahezu unmöglich ist.

---

## 8. Die entscheidende Einsicht: Die Agenten-Schleife ist selbst ein Graph

Die vorherigen sieben Abschnitte handelten davon, „wie Sie mit dieser Bibliothek Graphen zeichnen". Dieser Abschnitt behandelt etwas Wichtigeres: **Der `pydantic_ai.Agent`, den Sie in Teil 2 verwendet haben, ist intern selbst mit `pydantic_graph` gebaut.**

Das ist keine Analogie, sondern wörtlich gemeint — in `pydantic_ai/_agent_graph.py` gibt es eine Funktion namens `build_agent_graph()`, und darin steht genau `GraphBuilder(...)` + `g.add(...)` + `g.build()`.

Wer das verstanden hat, betrachtet den Agenten nicht mehr als „Blackbox", sondern als „ein Diagramm, das ich lesen, beobachten und beeinflussen kann".

### 8.1 Den Graphen des Agenten ausgeben

Drei Zeilen Code:

```python
from pydantic_ai._agent_graph import build_agent_graph

print(build_agent_graph(name='MyAgent', deps_type=type(None), output_type=str).render())
```

Reale Ausgabe:

```text
stateDiagram-v2
  UserPromptNode
  state decision <<choice>>
  CallToolsNode
  ModelRequestNode
  state decision_2 <<choice>>
  state decision_3 <<choice>>
  SetFinalResult

  [*] --> UserPromptNode
  UserPromptNode --> decision
  decision --> CallToolsNode
  decision --> ModelRequestNode
  CallToolsNode --> decision_3
  ModelRequestNode --> decision_2
  decision_2 --> CallToolsNode
  decision_2 --> ModelRequestNode
  decision_3 --> ModelRequestNode
  decision_3 --> [*]
  SetFinalResult --> [*]
```

**Das ist das Flussdiagramm, das in jedem pydantic-ai-Agenten tatsächlich abläuft.**

In Klartext gebracht:

```text
      [用户发起]
          │
          ▼
  ┌─────────────────┐
  │ UserPromptNode  │  处理用户输入、系统提示词、instructions
  └────────┬────────┘
           │  ◇ 判断：有历史待处理的响应吗？
     ┌─────┴─────┐
     ▼           ▼
┌──────────────┐ ┌──────────────────┐
│CallToolsNode │ │ ModelRequestNode │  ←──────┐
└──────┬───────┘ └────────┬─────────┘         │
       │                  │                    │
       │                  │ ◇ 流式出结果了？    │
       │            ┌─────┴─────┐              │
       │            ▼           ▼              │
       │      CallToolsNode  ModelRequestNode ─┘
       │            │
       │◇ 模型说完了 vs 还要调工具
   ┌───┴────┐
   ▼        ▼
[结束]  ModelRequestNode ──┐
                            └──→ 回到上面，循环
```

**Beachten Sie das `SetFinalResult --> [*]`**: Das ist eine „Insel-Kante", vom Startpunkt aus nicht erreichbar. Genau deshalb lautet die letzte Zeile von `build_agent_graph` im Quelltext `return g.build(validate_graph_structure=False)` — sie schaltet die Prüfung „alle Knoten müssen vom Startpunkt aus erreichbar sein" ausdrücklich ab. `SetFinalResult` wird nur im Streaming-Szenario ausgeführt, wenn es über `agent_run.next(SetFinalResult(...))` von Hand eingespeist wird — also genau über den `override_next`-Mechanismus aus Abschnitt 6.

### 8.2 Was die vier Knoten jeweils tun

Ich habe die Docstrings der einzelnen Knotenklassen im Original aus `pydantic_ai/_agent_graph.py` entnommen:

| Knoten | Docstring im Quelltext (Original) | In Klartext | Analogie |
|---|---|---|---|
| `UserPromptNode` | "The node that handles the user prompt and instructions." | Baut die erste Anfrage zusammen: Nutzereingabe, System-Prompt, Instructions (inklusive dynamisch erzeugter) und Nachrichtenverlauf werden zu einem `ModelRequest` zusammengefügt | **Der Empfang**: Vorgang annehmen, kennzeichnen, Unterlagen vervollständigen |
| `ModelRequestNode` | "The node that makes a request to the model using the last message in `state.message_history`." | Schickt die eigentliche HTTP-Anfrage an das LLM und holt die `ModelResponse` zurück | **Der Postausgang**: Die Unterlagen an den Experten schicken und auf Antwort warten |
| `CallToolsNode` | "The node that processes a model response, and decides whether to end the run or make a new request." | Wertet die Modellantwort aus: Bei Tool-Aufrufen werden die Tools ausgeführt und die Ergebnisse zu einer neuen Anfrage zusammengesetzt; andernfalls entsteht die endgültige Ausgabe | **Die Sortierstelle**: Die Antwort öffnen und prüfen, ob „Unterlagen nachzureichen sind" oder „das Ergebnis vorliegt" |
| `SetFinalResult` | "A node that immediately ends the graph run after a streaming response produced a final result." | Nur für Streaming-Szenarien: Im Datenstrom wurde bereits das Endergebnis erkannt, es wird unmittelbar beendet | **Die Schnellspur**: Das Ergebnis lag schon während der Übertragung vor, auf den Posteingang muss niemand warten |

**Einige entscheidende Details:**

`UserPromptNode` hat zwei ausgehende Kanten (`decision` → `CallToolsNode` oder `ModelRequestNode`). Warum sollte es direkt zu `CallToolsNode` gehen? Wegen des Szenarios **Wiederaufnahme eines früheren Dialogs** — ist die letzte Nachricht in `message_history` bereits eine Modellantwort (etwa weil der letzte Durchlauf vor dem Tool-Aufruf abgebrochen wurde), muss das Modell nicht erneut befragt werden, es geht direkt an die Tool-Verarbeitung.

Auch `ModelRequestNode` hat zwei ausgehende Kanten (`decision_2`): Der reguläre Pfad führt zu `CallToolsNode`; handelt es sich jedoch um Streaming und tritt unterwegs eine Situation auf, die eine Fortsetzung erfordert (etwa `pause_turn` bei Anthropic oder der Background-Modus bei OpenAI), geht es zurück zu `ModelRequestNode` selbst.

Die beiden ausgehenden Kanten von `CallToolsNode` (`decision_3`) sind das Herz der gesamten Schleife:

- `→ ModelRequestNode`: Das Modell will ein Tool aufrufen → das Tool läuft durch → das Ergebnis wird zurückgereicht und erneut gefragt → **das ist die Agenten-Schleife**
- `→ [*]`: Das Modell hat die endgültige Ausgabe geliefert → Ende

> 👉 **CEO-Perspektive**: Diese vier Knoten entsprechen exakt den vier Kennzahlen, die Sie an einem Agenten-Produkt interessieren:
>
> | Knoten | Die Kennzahl, die Sie interessieren sollte |
> |---|---|
> | `UserPromptNode` | Wie lang ist der Prompt? (kostenrelevant) Wurden die dynamischen Instructions korrekt zusammengesetzt? |
> | `ModelRequestNode` | Wie oft wurde das Modell aufgerufen? (jedes Auftreten von `ModelRequestNode` = ein weiterer Kostenposten) Wie hoch ist die Latenz? |
> | `CallToolsNode` | Welche Tools wurden aufgerufen? Wie hoch ist die Fehlerquote der Tools? |
> | Anzahl der Runden | Wie oft wurde `ModelRequestNode ↔ CallToolsNode` durchlaufen? Zu viele Runden bedeuten, dass sich das Modell im Kreis dreht — dann sind Prompt oder Tool-Beschreibungen zu optimieren |
>
> **„Wie viele Runden der Agent gedreht hat" ist eine außerordentlich praktische Produktkennzahl**, denn sie spiegelt Kosten, Latenz und Entwurfsqualität gleichzeitig wider. Und sie ist nichts anderes als die Anzahl der Schleifendurchläufe in diesem Diagramm.

### 8.3 Einmal real ausführen und sehen, welche Knoten durchlaufen werden

Mit `TestModel` (einem offline arbeitenden Scheinmodell, ohne Netzzugriff und ohne Kosten) einen Agenten mit Tool einmal durchlaufen lassen:

```python
import asyncio
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic_graph import End

agent = Agent(TestModel(custom_output_text='上海今天多云，26 度。'))


@agent.tool_plain
def get_weather(city: str) -> str:
    return f'{city}: 多云 26C'


async def main():
    async with agent.iter('上海天气怎么样？') as run:
        node = run.next_node                  # der erste Knoten
        trace = []
        while not isinstance(node, End):
            trace.append(type(node).__name__)
            node = await run.next(node)       # ← manuelles Weiterschalten (beachten Sie: kein async for)
        trace.append(f'End({node.data.output!r})')
        for i, t in enumerate(trace, 1):
            print(f'{i}. {t}')
        print('最终输出:', run.result.output)
```

Reale Ausgabe:

```text
1. UserPromptNode
2. ModelRequestNode
3. CallToolsNode
4. ModelRequestNode
5. CallToolsNode
6. End('上海今天多云，26 度。')
最终输出: 上海今天多云，26 度。
```

**Das entspricht exakt dem obigen Diagramm:**

- 1 → 2: Empfang → erste Anfrage abschicken
- 2 → 3: Das Modell sagt „ich will get_weather aufrufen"
- 3 → 4: Das Tool ist durchgelaufen, mit dem Ergebnis wird erneut gefragt (**das ist der zweite Modellaufruf, also der zweite Kostenposten**)
- 4 → 5: Diesmal liefert das Modell den endgültigen Text
- 5 → End: Ende

Der `AgentRun`, den `agent.iter()` liefert, ist eine Hülle um dasselbe Konstrukt wie der `GraphRun` von `pydantic_graph`:

| Element von `AgentRun` | Erläuterung |
|---|---|
| `.next_node` | Der als Nächstes auszuführende Agenten-Knoten |
| `await .next(node)` | Einen Schritt manuell weiterschalten |
| `.result` | Nach dem Durchlauf ein `AgentRunResult`, davor `None` |
| `.usage` | Token-Verbrauch, Anzahl der Anfragen |
| `.all_messages()` | Der vollständige Nachrichtenverlauf bis zu diesem Zeitpunkt |
| `.ctx.state` / `.ctx.deps` | State / Deps des zugrunde liegenden Graphen |
| `async for node in run` | Automatisches Weiterschalten (⚠️ siehe den Fallstrick im nächsten Unterabschnitt) |

> 👉 **CEO-Perspektive**: Diesen Code können Sie den Entwicklern unmittelbar mit der Ansage übergeben: „Ich möchte im Backend sehen, welche Knoten jede Agenten-Anfrage durchlaufen hat, wie viele Runden gedreht wurden und wie lange jeder Schritt gedauert hat." Das ist die minimale Umsetzung von **Agenten-Beobachtbarkeit** und zugleich das einzige Mittel, um der Frage nachzugehen, „warum die Antwort für diesen Nutzer besonders langsam bzw. besonders teuer war".

### 8.4 ⚠️ Ein Fallstrick, den man kennen muss: Ein nacktes `async for` löst die Node-Hooks von Capabilities nicht aus

`AgentRun` unterstützt zwei Arten des Weiterschaltens, und **sie verhalten sich unterschiedlich**:

```python
# Variante A: nacktes async for
async for node in agent_run:
    ...

# Variante B: manuelles next()
node = agent_run.next_node
while not isinstance(node, End):
    node = await agent_run.next(node)
```

**Variante A löst die von Capabilities registrierten Hooks auf Knotenebene nicht aus** (`before_node_run` / `wrap_node_run` / `after_node_run` / `on_node_run_error`).

Im Quelltext von `pydantic_ai/run.py` steht es bei `AgentRun.__anext__` unmissverständlich:

> "Note: this uses the graph run's internal iteration which **does NOT call node hooks** (`before_node_run`, `wrap_node_run`, `after_node_run`, `on_node_run_error`). Use `next()` for capability-hooked iteration, or use `agent.run()` which drives via `next()` automatically."

Praktisch verifiziert:

```python
import asyncio, warnings
from pydantic_ai import Agent
from pydantic_ai.capabilities import Hooks
from pydantic_ai.models.test import TestModel
from pydantic_graph import End

hooks = Hooks()
seen = []


@hooks.on.node_run
async def trace_node(ctx, *, node, handler):
    seen.append(type(node).__name__)
    return await handler(node)


agent = Agent(TestModel(custom_output_text='好的'), capabilities=[hooks])


async def main():
    # 1) nacktes async for
    seen.clear()
    async with agent.iter('你好') as run:
        async for node in run:
            pass
    print('裸 async for 触发的 hook:', seen)

    # 2) run.next(node)
    seen.clear()
    async with agent.iter('你好') as run:
        node = run.next_node
        while not isinstance(node, End):
            node = await run.next(node)
    print('用 run.next() 触发的 hook:', seen)

    # 3) agent.run()
    seen.clear()
    await agent.run('你好')
    print('agent.run() 触发的 hook:', seen)
```

Reale Ausgabe:

```text
裸 async for 触发的 hook: []
用 run.next() 触发的 hook: ['UserPromptNode', 'ModelRequestNode', 'CallToolsNode']
agent.run() 触发的 hook: ['UserPromptNode', 'ModelRequestNode', 'CallToolsNode']
```

**Das nackte `async for` hat nicht einen einzigen Hook ausgelöst.**

Die gute Nachricht: Die Bibliothek warnt Sie. Der vollständige, real abgefangene Warntext:

```text
UserWarning: A capability has `wrap_node_run` hooks, but bare `async for node in agent_run`
does not fire them. Use `agent_run.next(node)` to advance the run, or use `agent.run()`
which drives via `next()` automatically.
```

Es gibt noch ein gravierenderes verwandtes Verhalten: Wenn Sie eine Fähigkeit wie `enqueue` einsetzen, die auf `after_node_run` angewiesen ist, wirft die nackte Iteration beim Erreichen von `End` unmittelbar einen `UndrainedPendingMessagesError`, statt Nachrichten stillschweigend zu verwerfen.

**Ergebnistabelle:**

| Art des Antriebs | Löst Node-Hooks aus | Wann zu verwenden |
|---|---|---|
| `await agent.run(...)` | ✅ | **Standardmäßig diese Variante**, in 99 % der Fälle |
| `agent_run.next(node)` | ✅ | Wenn zwischen den Knoten eingegriffen werden muss |
| `async for node in agent_run` | ❌ | Nur zur **rein lesenden Beobachtung** und nur, wenn sicher keine Capability installiert ist |

> ⚠️ **Zusammenfassung des Fallstricks**: Wenn Ihr Team Capabilities einsetzt (etwa für Audit-Logs, Drosselung, Kostenerfassung oder Inhaltsfilterung) und irgendjemand an anderer Stelle `async for node in agent_run` benutzt, um „mal den Ablauf anzusehen", **werden diese Capabilities stillschweigend wirkungslos**. Audit-Einträge fehlen, die Drosselung greift nicht, die Kostenerfassung ist lückenhaft.
>
> Solche Fehler sind extrem schwer aufzuspüren — alles funktioniert scheinbar, nur werden „manche Anfragen nicht protokolliert".

> 👉 **CEO-Perspektive**: Dieser Fallstrick gehört unmittelbar in die technischen Richtlinien des Teams. In Produktsprache übersetzt: **„Einen Prozess beobachten" und „einen Prozess antreiben" sind zwei verschiedene Dinge; wird die falsche API verwendet, fallen auf diesem Pfad sämtliche Querschnittsfunktionen (Audit, Risikokontrolle, Abrechnung) aus.**
>
> Wenn Sie regulatorische Auflagen haben (jeder KI-Aufruf muss nachweisbar protokolliert werden), ist das ein realer Compliance-Risikopunkt.

### 8.5 Was das für einen CEO bedeutet

Die Erkenntnisse dieses Abschnitts in drei Punkten:

**1. Ein Agent ist keine Blackbox, sondern ein Diagramm mit gerade einmal vier Knoten.**

Sie können es ohne Weiteres in ein Anforderungsdokument zeichnen und der Fachabteilung erklären, „wie die KI arbeitet". Vier Knoten, zwei Schleifeneinstiege — mehr ist es nicht.

**2. „Wie viele Runden der Agent gedreht hat" = Kosten = Latenz = Entwurfsqualität.**

Die Zahl der Durchläufe der Schleife `ModelRequestNode ↔ CallToolsNode` im Diagramm entspricht unmittelbar der Zahl der Modellaufrufe. Eine einfache Frage-Antwort-Runde ist ein Durchlauf, mit einem Tool-Aufruf sind es zwei. Stellen Sie in Produktion einen Durchschnitt von fünf Runden fest, probiert das Modell wiederholt herum — meist sind die Tool-Beschreibungen unklar formuliert oder der Prompt liefert zu wenig Kontext. **Das ist eine Produktkennzahl, die sich unmittelbar optimieren lässt und deren Optimierungseffekt messbar ist.**

**3. Agent und expliziter Graph lassen sich verschachteln.**

Da ein Agent intern selbst ein Graph ist, liegt es nahe, „einen Agenten als Knoten in den eigenen Graphen zu setzen" — es genügt, in einem `@g.step` ein `await some_agent.run(...)` auszuführen.

```python
@g.step
async def draft_reply(ctx: StepContext[TicketState, Deps, str]) -> str:
    result = await ctx.deps.reply_agent.run(ctx.inputs)
    return result.output
```

**Außen die hart codierte SOP (unter Ihrer Kontrolle), innen die freie Entfaltung des Agenten (unter Kontrolle des Modells).** Das ist derzeit die verbreitetste und zugleich robusteste Architektur für KI-Produkte:

```text
┌────────────────────────────────────────────────────┐
│  你的显式 Graph（SOP，可审计，规则硬编码）           │
│                                                    │
│   收单 → 校验 → ┌──────────────────┐ → 人工复核 → 发出 │
│                │ Agent（自由发挥） │                  │
│                │  写回复文案       │                  │
│                └──────────────────┘                  │
└────────────────────────────────────────────────────┘
```

---

## 9. Die Auswahl: wann ein Graph angebracht ist

Der offizielle Satz „Benutzen Sie keinen Nagler, nur um einen Nagler zu benutzen" ist keine Höflichkeitsfloskel. Dieser Abschnitt liefert einen praktikablen Entscheidungsrahmen.

### 9.1 Vergleich der drei Ebenen

| | Einzelner Agent | Zusammenarbeit mehrerer Agenten | Expliziter Graph |
|---|---|---|---|
| Offizielle Metapher | Hammer | Vorschlaghammer | Nagler |
| Wer den nächsten Schritt entscheidet | Das Modell | Das Modell | **Sie** |
| Aufbaukosten | Gering | Mittel | **Hoch** |
| Visualisierbarkeit des Prozesses | ❌ | ❌ | ✅ `render()` |
| Garantie strikter Reihenfolge | ❌ | ❌ | ✅ |
| Echte Parallelität | ❌ | Teilweise | ✅ `.map()` / `.broadcast()` |
| Eingriff bei jedem Schritt | Über Capability-Hooks | Schwierig | ✅ `iter()` + `override_next()` |
| Auditierbarkeit der Verzweigungsregeln | ❌ Im Prompt versteckt | ❌ | ✅ Im Code und im Diagramm |
| Degradierung nach Fehlern | Über Capabilities | Schwierig | ✅ `ErrorMarker` |
| Kosten einer Anforderungsänderung | Prompt ändern (Minuten) | Prompt ändern | Code + Typannotationen ändern (Stunden) |
| Geeignet für | Frage-Antwort, Texterstellung, Recherche | Zusammenarbeit mit klarer Aufgabenteilung | SOPs, Freigaben, Auftragserfüllung, Stapelverarbeitung |

### 9.2 Entscheidungsliste: Ab wie vielen erfüllten Punkten sich ein Graph lohnt

Punkt für Punkt abhaken, ab **≥ 3 Punkten** lohnt sich ein Graph:

- [ ] Der Prozess hat eine **klar festgelegte, unveränderliche Schrittreihenfolge** (regulatorische Vorgaben, Geschäftsregeln)
- [ ] Es wird **echte Parallelität** benötigt (mehrere zeitaufwendige Operationen gleichzeitig, ohne serielles Warten)
- [ ] Die Verzweigungsregeln sind **harte Geschäftsregeln** (Betragsschwellen, Region, Kundenstufe) und dürfen nicht dem Ermessen des Modells überlassen bleiben
- [ ] Jeder Schritt muss **auditierbar protokolliert** werden, im Nachhinein muss beantwortbar sein, „warum damals dieser Weg genommen wurde"
- [ ] Es wird **menschliches Eingreifen** benötigt (Pausieren, Freigeben, Umleiten)
- [ ] Fehlschläge brauchen einen **klar definierten Degradierungspfad**, keinen simplen Retry
- [ ] Der Prozess muss **Nichttechnikern visuell erklärbar** sein (Fachabteilung, Compliance, Kunden)
- [ ] Der Prozess enthält **mehrere unterschiedliche KI-Aufrufe** mit jeweils eigener Aufgabe, die orchestriert werden müssen
- [ ] Es müssen **Massendaten** per Fan-out verarbeitet werden (Hunderte bis Tausende parallel)

Umgekehrt gilt: Trifft einer der folgenden Punkte zu, **verzichten Sie zunächst auf einen Graphen**:

- [ ] Der Prozess hat nur ein bis drei Schritte und ist rein linear → schreiben Sie einfach Funktionen
- [ ] „Was als Nächstes geschieht" sollte ohnehin das Modell entscheiden → Agent + Tools
- [ ] Die Anforderungen ändern sich rasch, der Prozess dreimal pro Woche → die Typannotationen eines Graphen bremsen Sie aus
- [ ] Niemand im Team ist mit Python-Generics und Typannotationen vertraut → die Einarbeitungskosten fressen den Nutzen auf

### 9.3 Bewertung dreier realer Szenarien

**Szenario A: Intelligenter Kundenservice-Dialog**

> Der Nutzer stellt eine Frage, die KI durchsucht die Wissensdatenbank und Bestelldaten und antwortet dann.

**Bewertung: kein Graph.** Nehmen Sie einen Agenten mit zwei Tools. Was und wie oft abgefragt wird, sollte das Modell selbst entscheiden — das ist flexibler. Ein hart codiertes „erst die Wissensdatenbank, dann die Bestelldaten" führt eher zu schlechteren Antworten.

**Szenario B: KI-gestützte Erstattungsfreigabe**

> Der Nutzer beantragt eine Erstattung → die KI beurteilt die Vereinbarkeit mit der Erstattungsrichtlinie → Beträge unter 100 werden automatisch freigegeben → 100 bis 1000 gehen an die Serviceleitung → über 1000 an die Finanzabteilung → auf jedem Weg muss ein Auditeintrag entstehen → bei Fehlschlag Übergabe an einen Menschen.

**Bewertung: unbedingt ein Graph.** Erfüllte Kriterien: klare Reihenfolge ✅, harte Regelverzweigung ✅, Audit-Protokollierung ✅, menschliches Eingreifen ✅, Degradierungspfad ✅ = 5 Punkte.

Die Struktur sieht in etwa so aus:

```text
[*] --> 收单
收单 --> AI政策判断（这一步内部是个 Agent）
AI政策判断 --> decision
decision --> 自动通过: <100
decision --> 主管审批: 100~1000
decision --> 财务审批: >1000
自动通过 --> 写审计
主管审批 --> 写审计
财务审批 --> 写审计
写审计 --> [*]
```

Beachten Sie: Der Schritt „KI-Richtlinienbeurteilung" darf intern durchaus ein Agent sein — **das Modell liefert nur die Begründung, es entscheidet nicht, welcher Zweig genommen wird**. Die Schwellenwerte der Verzweigung sind hart codiert, eine Änderung erfordert einen Release-Prozess — und genau das will die Compliance.

**Szenario C: Marketingtexte für 500 Produkte im Batch erzeugen**

> Produktliste abrufen → für jedes Produkt parallel die KI zur Texterzeugung aufrufen → Filterung sensibler Begriffe → Zusammenführung und Speicherung → Report erzeugen.

**Bewertung: Graph verwenden.** Erfüllte Kriterien: echte Parallelität ✅, Massen-Fan-out ✅, mehrere KI-Aufrufe ✅ = 3 Punkte.

Die Struktur:

```text
拉取商品 --> map(500 个并行) --> 生成文案（Agent）--> 敏感词过滤 --> join(汇总) --> 入库 --> 报告
```

Der Kernwert des Graphen liegt hier in `.map()` + `join` — 500 Aufgaben laufen parallel und werden automatisch zusammengeführt. Mit einer Agenten-Schleife liefe dasselbe 500-mal seriell, also hundertmal langsamer.

> ⚠️ Denken Sie aber an die Frage: **Werden 500 gleichzeitige Aufrufe von der Modell-API gedrosselt?** Um Drosselung kümmert sich diese Bibliothek nicht, Sie müssen im Step selbst ein Semaphor einbauen.

### 9.4 Ein schrittweiser Einführungspfad

Bilden Sie nicht sofort das gesamte System als Graph ab. Empfohlene Reihenfolge:

```text
第 1 步：先用 Agent 把功能跑通
   ↓  发现"某几步必须固定顺序"
第 2 步：把那几步抽成一张小 Graph，Agent 作为其中一个 step
   ↓  发现"要并行 / 要审计 / 要人工介入"
第 3 步：扩展这张 Graph，加 map/join、加 iter() 观察
   ↓  发现"要暂停几天等审批"
第 4 步：需要持久化 → 见第十节
```

> 👉 **CEO-Perspektive**: Die praktischste Faustregel — **fragen Sie zuerst, wer für ein Scheitern dieses Prozesses geradestehen muss**.
> - Antwort: „Wenn die KI falsch antwortet, fragt der Nutzer eben noch einmal" → Agent
> - Antwort: „Ein Fehler in diesem Schritt kostet Geld / erfordert einen Compliance-Bericht / muss von jemandem unterschrieben werden" → Graph
>
> Dieses Kriterium ist zuverlässiger als jede technische Kennzahl.

---

## 10. Grenzen dieser Version (offen benannt)

Beim Schreiben eines Tutorials ist nichts schlimmer, als nur die guten Seiten zu zeigen. Dieser Abschnitt legt dar, **was diese Version nicht leisten kann**.

### 10.1 Die größte Einschränkung: keine Persistenz, kein Unterbrechen und Fortsetzen

Das Modul `pydantic_graph.persistence` wurde in 2.x **vollständig entfernt**, ohne Ersatz.

Im Original aus der offiziellen Dokumentation `graph/builder/index.md`:

> **"No Native Persistence"**
> Unlike the original Graph API, the graph builder API does not include built-in state persistence. This is due to the **complexity of achieving consistent snapshotting with parallel execution**.
> For workflows that need to preserve progress across failures, restarts, or long-running operations, use one of the supported **durable execution** solutions.

Übersetzt: Die Builder-API hat **keine eingebaute Zustandspersistenz**, weil „konsistente Snapshots unter paralleler Ausführung zu komplex sind". Wer den Fortschritt über Ausfälle, Neustarts oder langlaufende Vorgänge hinweg sichern muss, soll eine der offiziell unterstützten Durable-Execution-Lösungen verwenden.

**Was das konkret bedeutet:**

| Was Sie tun wollen | Geht das? |
|---|---|
| Den Fortschritt mitten im Prozess in einer Datenbank ablegen | ❌ Keine eingebaute API |
| Nach einem Neustart des Dienstes an der letzten Stelle weiterlaufen | ❌ |
| „Freigabe beantragen → drei Tage später klickt die Führungskraft auf genehmigen → weiterlaufen" | ❌ Kein prozess- oder zeitübergreifendes Aussetzen möglich |
| Innerhalb desselben Prozesses pausieren, umleiten, fortsetzen | ✅ `iter()` + `override_next()` |
| Nach einem Absturz von vorn beginnen | ✅ (sofern Ihre Steps idempotent sind) |

> 👉 **CEO-Perspektive**: Das ist eine **harte Einschränkung auf Produktebene**, die bereits in der Anforderungsphase geklärt werden muss.
>
> Wenn in Ihrem PRD steht „nach der Einreichung wird auf die Bearbeitung durch den Freigebenden gewartet, der möglicherweise erst nach drei Tagen reagiert", dann kann diese Bibliothek das **ohne Zusatzaufwand nicht leisten**. Alle Prozessknoten, die „menschliche Bedenkzeit" erfordern, müssen in zwei eigenständige Runs zerlegt werden:
>
> ```text
> ❌ 一张图跑完：提交 → [挂起等审批 3 天] → 打款
> ✅ 拆成两张图：
>    图1：提交 → 校验 → 写入待办库 → 结束
>    （人类三天后在后台点了批准，触发）
>    图2：读取待办 → 打款 → 通知 → 结束
> ```
>
> Diese Aufteilung ist an sich nicht kompliziert, sie muss aber **bereits in der Entwurfsphase entschieden werden** und darf nicht erst nach Abschluss der Entwicklung auffallen.

### 10.2 Wenn Unterbrechen und Fortsetzen unbedingt sein müssen — der Lösungsansatz

Offiziell wird zu einer Durable-Execution-Lösung geraten (etwa Temporal). Wer es selbst zusammenbauen will, geht so vor:

```text
1. 用 graph.iter() 驱动，不用 graph.run()
2. 每推进一步，把这些东西序列化存库：
     - run.next_task  →  [(node_id, inputs, fork_stack), ...]
     - run.state      →  你的状态对象
3. 恢复时：
     - 反序列化出 state
     - 开一个新的 graph.iter(state=恢复的state, ...)
     - 立刻用 run.override_next([GraphTaskRequest(存下来的 node_id, inputs, fork_stack)])
     - 继续跑
```

**Wo die Schwierigkeiten liegen:**

| Schwierigkeit | Erläuterung |
|---|---|
| `inputs` muss serialisierbar sein | Handelt es sich um beliebige Python-Objekte, müssen Sie einen eigenen Encoder schreiben |
| `fork_stack` muss mitgespeichert werden | Wird er im Parallelfall nicht gespeichert, wartet der Join vergeblich |
| Paralleler Zustand lässt sich schwer konsistent snapshotten | Bei fünf parallelen Aufgaben sind zum Speicherzeitpunkt vielleicht drei fertig und zwei noch unterwegs — dieser Zwischenzustand ist nur schwer korrekt wiederherzustellen |
| Schritte müssen idempotent sein | Bei der Wiederherstellung kann ein Schritt erneut laufen, und bei Operationen wie „Abbuchung" hat ein zweiter Durchlauf schwerwiegende Folgen |

**Genau deshalb heißt es offiziell „zu komplex, deshalb entfernt".** Bauen Sie das nicht selbst nach, es sei denn, der Prozess ist rein linear (ohne map/broadcast) — dann ist `fork_stack` konstant `()` und alles wird erheblich einfacher.

### 10.3 Weitere Einschränkungen und Fallstricke (Übersicht)

| # | Einschränkung / Fallstrick | Auswirkung | Gegenmaßnahme |
|---|---|---|---|
| 1 | **Keine Persistenz** | Kein prozessübergreifendes Fortsetzen | In mehrere Runs zerlegen oder Durable Execution einsetzen |
| 2 | **Ein `@g.step`, der eine Union von BaseNodes zurückgibt, stürzt zur Laufzeit ab** | `build()` meldet nichts, es fliegt erst bei der Ausführung auseinander | Verzweigungslogik in eine `BaseNode` verlagern oder explizites `g.decision()` verwenden (siehe 3.7) |
| 3 | **Eine Decision ohne Auffangzweig stürzt ab** | `RuntimeError: No branch matched` | Bei jeder Decision zuletzt ein `g.match(TypeExpression[object])` ergänzen |
| 4 | **Eine leere Liste bei `.map()` führt dazu, dass der Join nichts erhält** | Einfache Graphen werfen einen `RuntimeError`; mehrzweigige Graphen **verwerfen Daten stillschweigend** (das Ergebnis stimmt nicht, ohne Fehlermeldung — am gefährlichsten) | Immer `downstream_join_id=` setzen |
| 5 | **Keine Obergrenze für Nebenläufigkeit** | Es werden so viele parallele Aufgaben gestartet, wie die Liste lang ist — nachgelagerte Systeme können überlastet werden | Innerhalb des Steps selbst ein Semaphor einbauen |
| 6 | **Schleifen haben keine maximale Rundenzahl** | Wird die Bedingung nie erfüllt, entsteht eine Endlosschleife | Einen Zähler in den durchfließenden Daten mitführen und einen Sicherungszweig ergänzen |
| 7 | **`matches` hat keinen Zugriff auf state/deps** | Verzweigungsbedingungen dürfen nicht vom Zustand abhängen | Die benötigten Informationen in den durchfließenden Wert packen |
| 8 | **`.transform()` ist synchron** | Darin ist kein `await` möglich | Wird Asynchronität benötigt, als `@g.step` schreiben |
| 9 | **Bei Parallelität ist der state ungesichert** | „Lesen-Ändern-Schreiben" verliert Aktualisierungen | Nur anfügende Operationen ausführen, zum Aufsummieren einen Reducer nutzen |
| 10 | **`initial=[]` vermischt Daten über Runs hinweg** | Der zweite Durchlauf schleppt die Ergebnisse des ersten mit | Für veränderliche Typen immer `initial_factory=` |
| 11 | **`run_sync` darf nicht in async aufgerufen werden** | `RuntimeError: This event loop is already running` | In asynchroner Umgebung `await graph.run()` verwenden |
| 12 | **Nacktes `async for node in agent_run` löst keine Node-Hooks aus** | Audit/Abrechnung/Drosselung fallen stillschweigend aus | `agent.run()` oder `agent_run.next(node)` verwenden |
| 13 | **Konflikt bei Knoten-IDs** | `GraphBuildingError` | Bei mehreren gleichnamigen Funktionen (etwa `process` in verschiedenen Modulen) manuell `node_id=` setzen |
| 14 | **Nicht erreichbare Knoten lassen build fehlschlagen** | Will man einen Knoten vorhalten, der „nur per override_next angesprungen wird", gibt es einen Fehler | `g.build(validate_graph_structure=False)` |
| 15 | **Steile Lernkurve** | Offizieller Wortlaut: "designed for advanced users and makes heavy use of Python generics and type hints. It is not designed to be as beginner-friendly as Pydantic AI." | Die Fähigkeiten des Teams einschätzen und schrittweise einführen |

### 10.4 Checkliste vor dem Produktivgang

Eine Liste für den CEO, die sich in einer Prüfungssitzung Punkt für Punkt abfragen lässt:

| # | Frage | Warum diese Frage |
|---|---|---|
| 1 | Sind bei jedem Entscheidungsknoten alle Fälle abgedeckt? Wohin führt der Auffangzweig? | Verhindert Abstürze durch `No branch matched` |
| 2 | Gibt es Schleifen? Wie viele Runden maximal? Was passiert bei Überschreitung? | Verhindert geldverbrennende Endlosschleifen |
| 3 | Gibt es Massenparallelität? Wie viele maximal? Droht Drosselung? | Verhindert Überlastung nachgelagerter Systeme |
| 4 | Was geschieht, wenn die Eingabe der Massenverarbeitung leer ist? | Verhindert ein vergessenes `downstream_join_id` |
| 5 | Was passiert, wenn ein Schritt fehlschlägt? Wie viele Wiederholungen? Und wohin danach? | Klärt den Degradierungspfad |
| 6 | Welche Audit-Informationen kann ich nach dem Durchlauf dieses Prozesses aus dem state entnehmen? | Sichert die Nachvollziehbarkeit |
| 7 | Enthält der Prozess Knoten, die menschliche Bedenkzeit erfordern? | Löst den Entwurf „in mehrere Runs zerlegen" aus |
| 8 | Hat jeder Knoten ein sprechendes `label`? Haben die wichtigen Entscheidungen ein `note`? | Stellt sicher, dass das Diagramm der Fachabteilung vorgelegt werden kann |
| 9 | Sind Capabilities installiert? Wird irgendwo ein nacktes `async for` verwendet? | Verhindert den stillen Ausfall von Audit/Abrechnung |
| 10 | Gibt es in parallelen Zweigen „Lesen-Ändern-Schreiben"-Operationen auf dem state? | Verhindert verlorene Aktualisierungen |

---

## Anhang A: API-Kurzreferenz

### A.1 Bauzeit

| API | Wesentliches zur Signatur | Erläuterung |
|---|---|---|
| `GraphBuilder(...)` | `name=, state_type=, deps_type=, input_type=, output_type=, auto_instrument=True` | Erzeugt den Builder |
| `g.start_node` | Attribut | Eingebauter Startpunkt, ID = `__start__` |
| `g.end_node` | Attribut | Eingebauter Endpunkt, ID = `__end__` |
| `@g.step` | `(node_id=, label=)` | Definiert einen funktionalen Knoten |
| `@g.stream` | `(node_id=, label=)` | Definiert einen Streaming-Knoten (async-Generator) |
| `g.node(X)` | `X` ist eine Unterklasse von `BaseNode` | Registriert einen deklarativen Knoten + legt Kanten automatisch an |
| `g.join(reducer, ...)` | `initial=` oder `initial_factory=`, `node_id=`, `parent_fork_id=`, `preferred_parent_fork=` | Erzeugt einen Zusammenführungsknoten |
| `g.decision(...)` | `note=`, `node_id=` | Erzeugt einen Entscheidungsknoten |
| `g.match(T, matches=)` | `T` kann eine Klasse oder `TypeExpression[...]` sein | Erzeugt eine Verzweigungsbedingung |
| `g.match_node(X)` | `X` ist eine Unterklasse von `BaseNode` | Verzweigt nach Knotentyp |
| `g.edge_from(*sources)` | Liefert einen `EdgePathBuilder` | Beginnt den Aufbau einer Kante |
| `g.add(*edges)` | | Fügt die Kanten in den Graphen ein |
| `g.add_edge(A, B, label=)` | | Kurzform für einfache Kanten |
| `g.add_mapping_edge(A, B, ...)` | `pre_map_label=, post_map_label=, fork_id=, downstream_join_id=` | Kurzform für map-Kanten |
| `g.build(validate_graph_structure=True)` | Liefert einen `Graph` | Kompiliert |

### A.2 Kettenmethoden auf Kanten

| Methode | Erläuterung |
|---|---|
| `.to(A)` / `.to(A, B, C)` | Legt das Ziel fest, mehrere = Broadcast |
| `.map(fork_id=, downstream_join_id=)` | Fan-out |
| `.broadcast(lambda b: [...], fork_id=)` | Explizites Broadcast |
| `.transform(func)` | Synchrone Umwandlung, `func(StepContext) -> neuer Wert` |
| `.label('...')` | Kantenbeschriftung (nur Visualisierung) |

### A.3 Laufzeit

| API | Erläuterung |
|---|---|
| `await graph.run(state=, deps=, inputs=)` | Durchlaufen und Ergebnis abholen |
| `graph.run_sync(...)` | Synchrone Variante, ⚠️ nicht in async aufrufbar |
| `async with graph.iter(...) as run:` | Schrittweise Ausführung |
| `graph.render(title=, direction=)` | Liefert Mermaid-Quelltext |
| `graph.nodes` | `dict[Knoten-ID, Knoten-Objekt]` |
| `run.state` / `run.deps` / `run.inputs` | Der Kontext dieses Durchlaufs |
| `run.next_task` | Was als Nächstes ausgeführt wird |
| `run.output` | Das Ergebnis, vor Abschluss `None` |
| `await run.next(value=None)` | Einen Schritt manuell weiterschalten |
| `run.override_next(Wert)` | Schreibt den nächsten Schritt um; der Wert kann `[GraphTaskRequest(...)]` oder `EndMarker(...)` sein |
| `async for event in run` | Automatisches Weiterschalten |

### A.4 Kontextobjekte

| Objekt | Wo man es erhält | Was es bietet |
|---|---|---|
| `StepContext[S, D, I]` | `@g.step` / `@g.stream` / `.transform()` | `.state` `.deps` `.inputs` |
| `GraphRunContext[S, D]` | `BaseNode.run()` | `.state` `.deps` |
| `ReducerContext[S, D]` | Reducer-Funktion mit drei Parametern | `.state` `.deps` `.cancel_sibling_tasks()` |

### A.5 Eingebaute Reducer

| Name | Schreibweise des Anfangswerts | Wirkung |
|---|---|---|
| `reduce_list_append` | `initial_factory=list[T]` | Sammeln per append |
| `reduce_list_extend` | `initial_factory=list[T]` | Flaches Zusammenführen |
| `reduce_dict_update` | `initial_factory=dict[K,V]` | Wörterbücher zusammenführen |
| `reduce_sum` | `initial=0` | Summenbildung |
| `reduce_null` | `initial=None` | Verwirft alles, dient nur als Synchronisationsbarriere |
| `ReduceFirstValue[T]()` | `initial=None` | Nimmt das schnellste Ergebnis, bricht die übrigen Aufgaben ab |

### A.6 Ausnahmetypen

| Ausnahme | Basisklasse | Wann sie geworfen wird |
|---|---|---|
| `GraphSetupError` | `TypeError` | Konfigurationsfehler im Graphen (fehlende Rückgabeannotation, `StepNode` ohne `Annotated`) |
| `GraphBuildingError` | `ValueError` | Fehler zur Bauzeit (Konflikt bei Knoten-IDs) |
| `GraphValidationError` | `ValueError` | Fehlgeschlagene Strukturprüfung (nicht erreichbare Knoten vorhanden) |
| `GraphRuntimeError` | `RuntimeError` | Fehler zur Laufzeit |

---

## Anhang B: Verifikationsumgebung

Sämtlicher Code dieses Textes wurde in folgender Umgebung real ausgeführt:

| Position | Version |
|---|---|
| `pydantic-graph` | 2.17.0 |
| `pydantic-ai` | 2.17.0 |
| Python | 3.11 |
| Plattform | Linux |

Herkunft des Codes und Art der Verifikation:

- Offizielles README (eingebettet in `pydantic_graph-2.17.0.dist-info/METADATA`)
- Offizielle Dokumentation `docs/graph.md`, `docs/graph/builder/{index,steps,joins,decisions,parallel}.md`
- Quelltext `pydantic_graph/{graph_builder,step,join,decision,basenode,node,paths,util,exceptions}.py`
- Zum Agenten-Graphen: Quelltext `pydantic_ai/_agent_graph.py`, `pydantic_ai/run.py`, `pydantic_ai/agent/abstract.py`

Alle Ausgaben von `render()`, alle Ausnahmemeldungen und Warntexte sind unveränderte Originalausgaben tatsächlicher Programmläufe.

---

## Zusammengefasst in einem Satz

**`pydantic-graph` verwandelt das „Flussdiagramm" in „lauffähigen Code" — und umgekehrt: Der Code ist das Flussdiagramm, das niemals veraltet.**

Seine drei Kernwerte, nach Bedeutung geordnet:

1. **Kanten werden aus den Rückgabetyp-Annotationen abgeleitet** → Flussdiagramm und Implementierung sind dauerhaft deckungsgleich, `render()` liefert das Diagramm jederzeit
2. **Echte Parallelität durch `.map()` / `g.join()`** → Massenaufgaben laufen statt seriell parallel, ein Leistungsunterschied um Größenordnungen
3. **`iter()` + `override_next()`** → Jeder Schritt lässt sich beobachten, beeinflussen und degradieren — die Grundlage sämtlicher Human-in-the-Loop-Produktformen

Seine drei Kosten:

1. **Keine Persistenz** → Prozesse mit langem Aussetzen müssen in mehrere Runs zerlegt werden
2. **Steile Lernkurve** → Offiziell heißt es ausdrücklich "designed for advanced users"
3. **Prozessänderungen erfordern Codeänderungen** → anders als bei zusammenklickbaren Workflows kann der Fachbereich nichts selbst anpassen

Zum Schluss noch einmal der offizielle Satz: **Wenn Sie sich nicht sicher sind, ob ein Graph eine gute Idee ist, dann ist er höchstwahrscheinlich unnötig.**
