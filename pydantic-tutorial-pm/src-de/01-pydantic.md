## 0. Auftakt: Warum ein CEO Pydantic verstehen sollte

Wenn Sie ein PRD schreiben, haben Sie ganz sicher schon einmal so etwas verfasst:

| Feld | Typ | Pflicht | Regel | Beschreibung |
|---|---|---|---|---|
| Mobilnummer | Text | ja | 11 Stellen, beginnt mit 1 | für Login und SMS-Benachrichtigung |
| Alter | Ganzzahl | nein | 18–120 | Minderjährige dürfen nicht bestellen |
| Mitgliedsstufe | Enum | ja | Standard / Silber / Gold | beeinflusst die Rabattberechnung |

Diese Tabelle ist die klassische „Feldregel-Tabelle" aus dem PRD. Sobald ein Entwickler sie bekommt, muss er drei Dinge tun:

1. Diese Tabelle **in eine Datenstruktur im Code übersetzen**;
2. an den Systemgrenzen **Punkt für Punkt prüfen**, ob die von außen hereinkommenden Daten dieser Tabelle entsprechen;
3. die geprüften Daten **wieder ausgeben** an nachgelagerte Stellen (Datenbank speichern, ans Frontend zurückgeben, an Dritte schicken).

**Genau diese drei Dinge erledigt Pydantic.** Es sorgt dafür, dass ein Entwickler die „Feldregel-Tabelle" nur ein einziges Mal schreibt – Prüflogik, Fehlermeldungen und die Dokumentation nach außen entstehen dann vollautomatisch.

In einem Satz definiert:

> **Pydantic ist eine Python-Bibliothek, die „die Feldregel-Tabelle aus dem PRD in ausführbaren Code verwandelt".**

Für alles Weitere in diesem Buch gibt es noch einen wichtigeren Grund: **Dass Pydantic AI ein LLM dazu bringt, in einem festen Format auszugeben, beruht vollständig auf Pydantics Fähigkeit, JSON Schema zu erzeugen.** Die Tabelle, die Sie in Pydantic zeichnen, wird automatisch in eine „Ausfüllanleitung für das LLM" übersetzt. Kapitel 7 zu JSON Schema ist deshalb das Scharnier des ganzen Buches – lesen Sie es besonders aufmerksam.

Sämtlicher Code dieses Tutorials wurde real auf **Pydantic 2.13.4 / Python 3.11** ausgeführt, die Ausgaben sind echte Kopien (aus Platzgründen wurde bei manchen Fehlerausgaben die letzte Zeile `For further information visit https://errors.pydantic.dev/...` weggelassen, einzelne JSON-Ausgaben wurden kompakter gesetzt – inhaltlich wurde nichts verändert; wenn Sie es selbst laufen lassen, erscheinen womöglich ein paar Link-Zeilen mehr, das ist normal).

> 💡 **Zu den Codeblöcken**: Die Codeblöcke dieses Buches bauen **der Reihe nach aufeinander auf** (wie in einem Jupyter Notebook, Zelle für Zelle), `import` steht meist nur einmal am Kapitelanfang, spätere Blöcke nutzen es einfach weiter. Wenn Sie also **einen einzelnen Block aus der Mitte herauskopieren und laufen lassen, kann eine Meldung über einen undefinierten Namen kommen** – ergänzen Sie dann einfach das passende `from pydantic import BaseModel, Field` o. Ä., der Code ist nicht fehlerhaft.

> ⚠️ **Fallstrick**: Sehr viele Pydantic-Tutorials im Netz stammen noch aus der V1-Zeit (vor 2023). V1 und V2 unterscheiden sich stark in den API-Namen (`parse_obj` → `model_validate`, `dict()` → `model_dump`, `@validator` → `@field_validator`). Prüfen Sie bei Fundstücken immer zuerst die Version.

---

## 1. Architekturüberblick: erst die Gesamtkarte

Bevor wir in die Details eintauchen, zeichnen wir eine Gesamtkarte. Die Welt von Pydantic besteht aus nur **drei Aktionen** und **fünf Bauteilen**.

### 1.1 Drei Aktionen: hinein, verweilen, hinaus

Aus Sicht von Pydantic durchlaufen alle Daten dieselbe Fertigungsstraße:

```text
        ①  校验 (Validation)              ②  持有 (Model Instance)         ③  产出 (Serialization / Schema)
   ┌────────────────────────┐        ┌───────────────────────────┐      ┌──────────────────────────────┐
   │  外部来的"脏"数据       │        │   干净、类型正确、        │      │  model_dump()      → dict     │
   │  · HTTP 请求 JSON       │  ───▶  │   规则已保证的对象        │ ───▶ │  model_dump_json() → JSON 串  │
   │  · 数据库/Excel 行      │        │                           │      │  model_json_schema() → 说明书 │
   │  · 大模型返回的文本     │        │   代码里可以放心地用      │      │                              │
   │  · 用户表单             │        │   o.price * o.qty         │      │                              │
   └────────────────────────┘        └───────────────────────────┘      └──────────────────────────────┘
              │                                                                        │
              │  不合规 → 抛 ValidationError                                            │  说明书交给：
              ▼                                                                        ▼   · 前端渲染表单
      ┌──────────────────┐                                                       · API 文档 (OpenAPI)
      │ 一次性列出所有错误│                                                       · 大模型（结构化输出）★
      │ 定位到具体字段    │
      └──────────────────┘
```

**Analogie aus der Produktwelt**: Diese Fertigungsstraße ist das Muster „**Annahme → Archivierung → Ausstellung**".

| Abschnitt der Fertigungsstraße | Entsprechung in der Produktwelt |
|---|---|
| ① Validierung | Der Empfang nimmt Unterlagen an, gleicht sie Punkt für Punkt mit einer Checkliste ab und weist bei fehlenden Teilen sofort zurück, mit klarer Ansage, was fehlt |
| ② Halten | Die Unterlagen wandern ins Archiv; alle Abteilungen gehen danach davon aus, dass diese Akte vollständig und korrekt formatiert ist |
| ③ Ausgabe | Aus der Akte entstehen Dokumente nach außen: Berichte für die Finanzabteilung, Bestätigungen für Kunden, „Hinweise zum Ausfüllen" für neue Antragsteller |

### 1.2 Fünf Bauteile: wer wofür zuständig ist

```text
                          ┌─────────────────────────────────────┐
                          │            BaseModel                │
                          │      （表 / 模具 / 数据契约）        │
                          │   一个 class = 一张 PRD 字段规则表    │
                          └──────────────┬──────────────────────┘
                                         │ 由以下部件组装而成
        ┌────────────────┬───────────────┼────────────────┬──────────────────┐
        ▼                ▼               ▼                ▼                  ▼
 ┌────────────┐   ┌────────────┐  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐
 │  类型注解   │   │  Field()   │  │  校验器      │  │ model_config │  │ computed_field │
 │ Type Hints │   │ 字段元数据  │  │ Validators  │  │  ConfigDict  │  │   计算字段      │
 ├────────────┤   ├────────────┤  ├─────────────┤  ├──────────────┤  ├────────────────┤
 │ 这一列是    │   │ 这一列的    │  │ 表格填完后  │  │ 整张表的      │  │ 不用填，        │
 │ 什么类型？  │   │ 取值范围、  │  │ 还要跑的    │  │ 全局开关：    │  │ 系统自己算出来  │
 │ str/int/   │   │ 默认值、    │  │ 业务规则：  │  │ 多余字段咋办  │  │ 的列：          │
 │ 日期/枚举/ │   │ 别名、      │  │ 跨字段校验  │  │ 能不能改      │  │ 小计、是否包邮  │
 │ 嵌套表     │   │ 字段说明    │  │ 先算再判    │  │ 大小写处理    │  │                │
 └────────────┘   └────────────┘  └─────────────┘  └──────────────┘  └────────────────┘

        另有两个"表外"的工具：
 ┌──────────────────────────┐        ┌────────────────────────────────┐
 │  TypeAdapter             │        │  ValidationError               │
 │  给不是"表"的东西做校验    │        │  校验失败时的标准化错误报告      │
 │  （一个列表、一个数字）    │        │  （谁错了 / 错在哪 / 为什么错）  │
 └──────────────────────────┘        └────────────────────────────────┘
```

### 1.3 Bauteil-Übersicht auf einen Blick

Überfliegen Sie sie zunächst nur, um ein Gefühl zu bekommen – jede Zeile bekommt später einen eigenen `###`-Abschnitt mit ausführlicher Erklärung.

| Bauteil | Wie der Code aussieht | Aufgabe in einem Satz | CEO-Intuition zum Vergleich |
|---|---|---|---|
| **BaseModel** | `class Order(BaseModel):` | definiert eine „Tabelle" (Datenvertrag) | die Feldregel-Tabelle im PRD / der Entwurf einer Datenbanktabelle |
| **Typannotation** | `price: float` | erklärt, was diese Spalte enthält | Excel-„Zellformat": Text/Zahl/Datum |
| **Field()** | `= Field(gt=0)` | fügt dieser Spalte Beschränkungen und Erläuterungen hinzu | Excel-„Datenüberprüfung" + Feldnotiz |
| **field_validator** | `@field_validator("code")` | eigene Regel für ein einzelnes Feld | Prüfungen wie „der Gutscheincode muss mit CP beginnen" |
| **model_validator** | `@model_validator(mode="after")` | feldübergreifende Regeln | „das Enddatum muss nach dem Startdatum liegen" |
| **computed_field** | `@computed_field` | abgeleitete, nur lesbare Spalte | Excel-Formelspalte: Zwischensumme = Einzelpreis × Menge |
| **model_config** | `model_config = ConfigDict(...)` | globale Schalter für die gesamte Tabelle | globale Formulareinstellungen: darf mehr eingetragen werden, darf geändert werden |
| **model_dump / _json** | `o.model_dump()` | gibt das Objekt wieder als dict / JSON aus | „Export nach Excel / CSV" |
| **model_json_schema** | `Order.model_json_schema()` | macht aus der Tabelle eine maschinenlesbare Spezifikation ★ | „Hinweise zum Ausfüllen", für Frontend/LLM |
| **Diskriminierte Union** | `Field(discriminator="type")` | „nur wenn A gewählt ist, erscheint die Feldgruppe B" | Formularlogik / bedingte Anzeige |
| **ValidationError** | `except ValidationError as e:` | standardisierter Fehlerbericht | die rot markierten Hinweise nach dem Absenden eines Formulars |
| **TypeAdapter** | `TypeAdapter(list[int])` | validiert Typen, die keine BaseModel sind | geprüft wird nicht „eine Tabelle", sondern „eine Datenspalte" |

### 1.4 Ein Bild, das Pydantics Platz im System zeigt

```text
  外部世界（不可信）                    │        你的系统内部（可信）
 ─────────────────────────────────────┼──────────────────────────────────────
  前端表单提交                          │
  第三方 API 回调         ┌───────────┐ │   业务逻辑代码
  数据库里的历史脏数据 ──▶ │  Pydantic  │─┼─▶ 不用再写 if x is None
  运营上传的 Excel        │   校验层   │ │   不用再写 try: int(x)
  大模型返回的 JSON  ★    └───────────┘ │   直接 order.total * 0.9
                              │         │
                              ▼         │
                        ValidationError │
                        （挡在门外）     │
```

> 👉 **CEO-Perspektive**: Pydantic ist der **Empfang bzw. Pförtner** Ihres Systems. Es steht zwischen dem „nicht vertrauenswürdigen Außen" und dem „vertrauenswürdigen Innen" und lässt nur Daten durch, die den PRD-Regeln vollständig entsprechen. Daraus ergibt sich ein enormer Produktnutzen: **Alle Datenformatprobleme treten an ein und derselben Stelle zutage, und zwar sehr früh.** Der klassische Produktionsvorfall – „ein Nutzer trägt ein falsches Alter ein, und erst im Abrechnungsmodul kommt eine kryptische Fehlermeldung" – entsteht im Kern genau durch das Fehlen dieses Pförtners. Im Review können Sie Ihre Entwickler schlicht fragen: „Werden die Eingabeparameter dieser Schnittstelle gegen ein Schema validiert?" – Damit fragen Sie, ob es diese Tür gibt.

### 1.5 Unter der Haube: warum Pydantic so schnell ist

```python
import pydantic, pydantic_core
print("pydantic:", pydantic.VERSION, "| pydantic_core:", pydantic_core.__version__)
```

```text
pydantic: 2.13.4 | pydantic_core: 2.46.4
```

Pydantic 2 besteht aus zwei Schichten: dem syntaktischen Zucker in Python, den Sie schreiben (`pydantic`), und der Rust-Engine, die die eigentliche Arbeit macht (`pydantic-core`). Deshalb ist es trotz feldweiser Prüfung sehr schnell:

```python
class P(BaseModel):
    n: int

import timeit
print("校验 10000 次耗时(秒):", round(timeit.timeit(lambda: P(n=1), number=10000), 4))
```

```text
校验 10000 次耗时(秒): 0.0059
```

Zehntausend Validierungen brauchten 6 Millisekunden.

> 👉 **CEO-Perspektive**: Wenn Entwickler sagen „verlangsamen so viele Prüfungen nicht die Schnittstelle?", können Sie mit dieser Zahl antworten. Die Validierung selbst kostet praktisch keine Zeit; langsam sind Datenbank und Netzwerk. **Streichen Sie Datenvalidierung niemals aus Performancegründen** – das ist der klassische Fall, bei dem man an der falschen Stelle spart.

---
## 2. BaseModel: die Definition einer Tabelle

### 2.1 Definition vs. Instanz: Gussform und Bauteil

**Welches Problem es löst**: Es verwandelt die „Feldregel-Tabelle aus dem PRD" in etwas, das im Code beliebig oft wiederverwendet werden kann.

```python
from datetime import date
from pydantic import BaseModel


# Das ist die "Gussform": einmal definiert, beschreibt sie, wie alle User aussehen
class User(BaseModel):
    name: str
    age: int
    signup_date: date | None = None


# Das ist das "Bauteil": eine konkrete Instanz, hergestellt mit der Gussform
u = User(name="张三", age=28, signup_date="2024-03-15")
print(u)
print(repr(u.age), repr(u.signup_date))
print(type(u.signup_date))
```

```text
name='张三' age=28 signup_date=datetime.date(2024, 3, 15)
28 datetime.date(2024, 3, 15)
<class 'datetime.date'>
```

Beachten Sie ein Detail: Hineingegeben haben wir die Zeichenkette `"2024-03-15"`, heraus kommt ein echtes **Datumsobjekt** `datetime.date(2024, 3, 15)`. Pydantic „prüft" also nicht nur, es sorgt auch für die „Umwandlung in den richtigen Typ".

Sehen wir uns nun die Gussform selbst an – sie lässt sich programmatisch auslesen:

```python
print(User.model_fields.keys())
for n, f in User.model_fields.items():
    print(n, "| required:", f.is_required(), "| default:", f.default)
```

```text
dict_keys(['name', 'age', 'signup_date'])
name | required: True | default: PydanticUndefined
age | required: True | default: PydanticUndefined
signup_date | required: False | default: None
```

`PydanticUndefined` ist die spezielle Markierung, mit der Pydantic ausdrückt, dass „überhaupt kein Standardwert vorhanden ist" – halten Sie das nicht für einen echten Wert.

> 👉 **CEO-Perspektive**: **Klasse = Tabellenstrukturdefinition, Instanz = eine Datenzeile in der Tabelle**. Das „Formular für Nutzerdaten", das Sie in Axure gezeichnet haben, ist die Gussform; jede Absendung durch einen Nutzer erzeugt ein Bauteil. Noch interessanter ist eine Fähigkeit wie `model_fields`: Sie bedeutet, dass **die Feldregel-Tabelle im Code selbst von Programmen ausgelesen werden kann**. Genau deshalb kann Pydantic automatisch API-Dokumentation, Frontend-Formulare und Spezifikationen für das LLM erzeugen – weil die Regeltabelle nicht als Kommentar für Menschen dasteht, sondern im Code für Maschinen lesbar ist.

### 2.2 Drei Eingänge: woher die Daten kommen

**Welches Problem es löst**: Daten aus unterschiedlichen Quellen (Python-Dictionary / JSON-String / handgeschriebene Parameter) müssen alle in diese Tabelle gelangen können.

```python
# Eingang 1: Parameter direkt übergeben (für Tests und Skripte)
u1 = User(name="张三", age=28)

# Eingang 2: Validierung aus einem Dictionary (am häufigsten: HTTP-Request-Body, Datenbankzeile, Excel-Zeile)
raw = {"name": "赵六", "age": 41, "signup_date": "2023-01-01"}
u3 = User.model_validate(raw)
print(u3)

# Eingang 3: Validierung direkt aus einem JSON-String (spart den Schritt json.loads)
u4 = User.model_validate_json('{"name": "钱七", "age": 19}')
print(u4)
```

```text
name='赵六' age=41 signup_date=datetime.date(2023, 1, 1)
name='钱七' age=19 signup_date=None
```

| Methode | Eingabe | Typisches Szenario |
|---|---|---|
| `User(...)` | Schlüsselwortargumente | manuelle Konstruktion im Code |
| `User.model_validate(d)` | dict / Objekt | Verarbeitung von Request-Bodys, Datenbankergebnissen |
| `User.model_validate_json(s)` | JSON-String/Bytes | direkte Verarbeitung von HTTP-Bodys, LLM-Ausgaben ★ |

> 👉 **CEO-Perspektive**: `model_validate_json` ist der Schlüssel für die spätere Verarbeitung von **LLM-Ausgaben**. Was ein LLM ausspuckt, ist ein Stück Text; `model_validate_json` macht daraus in einem Schritt ein validiertes Objekt – was nicht dem Format entspricht, erzeugt sofort eine Fehlermeldung, statt mit schmutzigen Daten weiterzulaufen.

### 2.3 Was passiert, wenn ein Feld fehlt

**Welches Problem es löst**: Fehlt ein Pflichtfeld, braucht es eine klare, lesbare und lokalisierbare Fehlermeldung – statt eines Programms, das unerklärlich abstürzt.

```python
from pydantic import ValidationError

try:
    User(name="王五")     # age fehlt
except ValidationError as e:
    print(e)
```

```text
1 validation error for User
age
  Field required [type=missing, input_value={'name': '王五'}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.13/v/missing
```

Diese Fehlermeldung enthält vier Informationsebenen: **welches Modell** (User), **welches Feld** (age), **welches Problem** (Field required) und **welchen Fehlercode** (`missing`, der sich für die Mehrsprachigkeit im Frontend zuordnen lässt).

> 👉 **CEO-Perspektive**: Das ist genau die „Pflichtfeldprüfung samt Fehlermeldungstexten", die Sie im PRD festgehalten haben – nur dass Pydantic standardmäßig englische Texte plus einen stabilen Fehlercode liefert. **Für das Frontend zählt der Fehlercode `missing`**: Das Frontend erhält `type: "missing"` und `loc: ["age"]` und kann darauf hin unter dem Eingabefeld für das Alter einen roten Hinweis auf Chinesisch einblenden: „Bitte geben Sie Ihr Alter an". Kapitel 9 erklärt ausführlich, wie man diesen Fehlerbericht liest.

### 2.4 Typ-Coercion: großzügig hinein, streng hinaus

**Welches Problem es löst**: In der realen Welt haben Daten häufig „den falschen Typ, aber die richtige Bedeutung" – etwa wenn ein Formular sämtliche Werte als Zeichenketten überträgt.

```python
u2 = User(name="李四", age="30")     # übergeben wird der String "30"
print(u2)
print(type(u2.age))
```

```text
name='李四' age=30 signup_date=None
<class 'int'>
```

Pydantic verfährt standardmäßig nach dem Prinzip **großzügig hinein, streng hinaus**: Was sich sicher umwandeln lässt, wird umgewandelt (`"30"` → `30`); nur was sich nicht umwandeln lässt, erzeugt eine Fehlermeldung. Kapitel 4 liefert die vollständige Tabelle der Umwandlungsregeln.

> 👉 **CEO-Perspektive**: Alle Felder, die ein HTML-Formular absendet, sind im Kern Zeichenketten; `age=30` und `age="30"` sind auf Browserseite nicht zu unterscheiden. Die automatische Umwandlung von Pydantic erspart Ihnen große Mengen an Klebecode nach dem Muster „erst Typ umwandeln, dann prüfen". Aber sie hat ihre Grenzen: `"abc"` lässt sich nicht in eine Zahl umwandeln und erzeugt garantiert eine Fehlermeldung – es wird nicht klammheimlich zu 0. **Dieses „großzügig hinein" hat eine Untergrenze, es ist kein fauler Kompromiss.**

### 2.5 Gebräuchliche Methoden einer Instanz

**Welches Problem es löst**: Wie kopiert, ändert und prüft man ein vorliegendes Objekt – und woher weiß man, welche Felder der Nutzer tatsächlich ausgefüllt hat?

```python
class U(BaseModel):
    a: int
    b: str = "默认"


u = U(a=1)
print("model_fields_set:", u.model_fields_set)   # welche Felder der Nutzer "explizit ausgefüllt" hat
u2 = u.model_copy(update={"a": 99})              # eine Kopie anlegen und einige Werte ändern
print("model_copy       :", u2)
u3 = U.model_construct(a="不校验")                # ohne Validierung direkt erzeugen, gefährlich
print("model_construct  :", u3)
```

```text
model_fields_set: {'a'}
model_copy       : a=99 b='默认'
model_construct  : a='不校验' b='默认'
```

| Methode | Wirkung | Zu beachten |
|---|---|---|
| `model_fields_set` | welche Felder der Nutzer explizit übergeben hat | unterscheidet „nicht ausgefüllt" von „mit einem Wert ausgefüllt, der dem Standardwert entspricht" |
| `model_copy(update={})` | kopieren und teilweise ändern | **validiert nicht erneut** |
| `model_construct()` | ohne Validierung direkt konstruieren | nur einsetzen, wenn „die Daten gesichert vertrauenswürdig sind", etwa beim Lesen aus der eigenen Datenbank |

> 👉 **CEO-Perspektive**: `model_fields_set` entspricht einer sehr verbreiteten Produktanforderung – der **PATCH-Semantik**. Ob ein Nutzer auf der Einstellungsseite „Push-Nachrichten empfangen" auf dem Standardwert „aus" belässt oder aktiv „aus" auswählt, kann fachlich völlig Unterschiedliches bedeuten (im ersten Fall darf der serverseitige Wert nicht überschrieben werden, im zweiten schon). `model_fields_set` ist genau die Grundlage, um beides zu unterscheiden.
>
> Verstehen Sie `model_construct` bitte als „**Grüner Kanal ohne Kontrolle**". Bei internen, vertrauenswürdigen Daten ist das eine Performance-Optimierung; bei externen Daten ist es ein Unfall.

### 2.6 Ein großer Fallstrick: Attributänderungen werden standardmäßig nicht validiert

```python
u4 = User(name="钱七", age=19)
u4.age = "not a number"       # direkte Zuweisung
print(u4.age)
```

```text
not a number
```

Pydantic validiert standardmäßig **nur im Moment der Objekterzeugung**. Was Sie danach dem Objekt zuweisen, kümmert es nicht.

Erst mit aktiviertem `validate_assignment` greift die Prüfung:

```python
from pydantic import ConfigDict

class VA(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    n: int = Field(ge=0)


va = VA(n=1)
try:
    va.n = -5
except ValidationError as e:
    print(e.errors()[0]["msg"])
```

```text
Input should be greater than or equal to 0
```

> ⚠️ **Fallstrick**: Viele halten Pydantic-Modelle für „dauerhaft gültig", tatsächlich sind sie nur „im Moment der Geburt gültig". Wenn Ihr Code Felder auch nach der Objekterzeugung noch ändert, müssen Sie unbedingt `validate_assignment=True` einschalten.

> 👉 **CEO-Perspektive**: Das ist wie die **Prüfung bei der Einstellung** – beim Eintritt werden Abschluss und Werdegang geprüft, aber wenn Sie danach Ihren Lebenslauf im System ändern, prüft niemand noch einmal nach. Wollen Sie, dass „jede Änderung erneut geprüft wird", müssen Sie dafür einen eigenen Schalter umlegen (und das kostet ein wenig Performance).

### 2.7 Vererbung: gemeinsame Felder herausziehen

**Welches Problem es löst**: Mehrere Tabellen haben einen Satz gemeinsamer Felder (id, Erstellungszeit, Ersteller), und man möchte sie nicht in jeder Tabelle erneut abschreiben.

```python
class Base(BaseModel):
    id: int
    created_at: date | None = None


class Article(Base):
    title: str
    body: str = ""


a = Article(id=1, title="标题")
print(a)
print(list(Article.model_fields))
```

```text
id=1 created_at=None title='标题' body=''
['id', 'created_at', 'title', 'body']
```

Die Unterklasse besitzt automatisch sämtliche Felder der Oberklasse, und zwar in der Reihenfolge „Felder der Oberklasse zuerst".

> 👉 **CEO-Perspektive**: Das entspricht der „**Konvention für gemeinsame Felder**" aus dem PRD – alle Geschäftsobjekte haben id, Erstellungszeit, Änderungszeit und Ersteller. Diese in eine Base-Klasse herauszuziehen bedeutet, die Konvention im Code zu verankern: Sie ändern eine Stelle, und alle Tabellen ziehen mit.
>
> Denken Sie aber an einen großen Fallstrick, den Abschnitt 6.5 behandeln wird: **Vererbung ist bei der „Validierung" sehr praktisch, bei der „Serialisierung" beißt sie zurück**. Wollen Sie mit Vererbung eine Verzweigung nach dem Muster „Typ A / Typ B" ausdrücken, lautet die richtige Antwort: die diskriminierte Union aus Kapitel 8, nicht Vererbung.

---
## 3. Field(): Jeder Spalte Regeln und Erläuterungen mitgeben

`Field()` ist die Funktion, die in Pydantic am häufigsten auftaucht. Sie erledigt zwei Dinge:

1. **Beschränkung** (constraint): Welche Bedingung muss der Wert dieser Spalte erfüllen — das Gegenstück zur „Datenüberprüfung" in Excel;
2. **Metadaten** (metadata): Wie heißt diese Spalte, was bedeutet sie, Standardwert, Alias — das Gegenstück zu Feldkommentaren und Dokumentation.

### 3.1 Numerische Beschränkungen: gt / ge / lt / le

**Welches Problem wird gelöst**: Bereichsregeln der Art „Der Preis muss größer als 0 sein" oder „Die Bewertung muss zwischen 1 und 5 liegen".

```python
from pydantic import BaseModel, Field, ValidationError


class Product(BaseModel):
    price: float = Field(gt=0, le=99999)      # größer als 0, kleiner oder gleich 99999
    stock: int = Field(ge=0, default=0)       # größer oder gleich 0, Standard 0
```

| Parameter | Langform | Bedeutung | Mathematisches Zeichen |
|---|---|---|---|
| `gt` | greater than | größer als | `>` |
| `ge` | greater than or equal | größer oder gleich | `≥` |
| `lt` | less than | kleiner als | `<` |
| `le` | less than or equal | kleiner oder gleich | `≤` |
| `multiple_of` | — | muss ein ganzzahliges Vielfaches sein | Schrittweite |

```python
try:
    Product(price=-5, stock=-1)
except ValidationError as e:
    print(e)
```

```text
2 validation errors for Product
price
  Input should be greater than 0 [type=greater_than, input_value=-5, input_type=int]
    For further information visit https://errors.pydantic.dev/2.13/v/greater_than
stock
  Input should be greater than or equal to 0 [type=greater_than_equal, input_value=-1, input_type=int]
    For further information visit https://errors.pydantic.dev/2.13/v/greater_than_equal
```

Beachten Sie: **Beide Fehler werden auf einen Schlag gemeldet** — es wird nicht nach dem ersten Fehler abgebrochen.

> 👉 **CEO-Perspektive**: Der Unterschied zwischen `gt=0` und `ge=0` ist genau der zwischen „muss größer als null sein" und „darf null sein" — und genau das wird in Pflichtenheften ständig unscharf formuliert. „Der Lagerbestand darf nicht negativ sein" ist `ge=0` (0 ist zulässig und bedeutet ausverkauft); „Der Preis muss positiv sein" ist `gt=0` (Artikel für 0 Euro laufen über eine andere Logik). **Wenn Sie diese beiden Begriffe sauber trennen, entfällt die Hälfte des Hin und Her bei der Integration.**
>
> Achten Sie außerdem auf das Verhalten „alle Fehler auf einmal melden". Das entscheidet unmittelbar über die Nutzererfahrung im Frontend: Werden alle Fehler auf einmal rot markiert (der Nutzer korrigiert einmal alles), oder kommt nach jeder Korrektur der nächste Fehler (der Nutzer muss fünfmal absenden)? Pydantic macht standardmäßig Ersteres.

### 3.2 String-Beschränkungen: min_length / max_length / pattern

**Welches Problem wird gelöst**: Textregeln der Art „Anzeigename 2–20 Zeichen" oder „Mobilnummer 11 Stellen, beginnend mit 1".

```python
class Product2(BaseModel):
    sku: str = Field(min_length=6, max_length=12)
    title: str = Field(max_length=30, description="商品标题，展示在列表页")
    phone: str = Field(pattern=r"^1\d{10}$")     # Regex: beginnt mit 1 + 10 Ziffern
```

```python
try:
    Product2(sku="A1", title="x" * 40, phone="13800138000")
except ValidationError as e:
    print(e)
```

```text
sku
  String should have at least 6 characters [type=string_too_short, input_value='A1', input_type=str]
title
  String should have at most 30 characters [type=string_too_long, input_value='xxxx...', input_type=str]
```

Die Fehlermeldung bei nicht passendem regulären Ausdruck:

```python
try:
    Product2(sku="ABC123", title="正常标题", phone="123")
except ValidationError as e:
    print(e)
```

```text
1 validation error for Product2
phone
  String should match pattern '^1\d{10}$' [type=string_pattern_mismatch, input_value='123', input_type=str]
    For further information visit https://errors.pydantic.dev/2.13/v/string_pattern_mismatch
```

> 👉 **CEO-Perspektive**: `pattern` ist die „benutzerdefinierte Formel" aus der Excel-Datenüberprüfung und zugleich der reguläre Ausdruck im Frontend-Formular. **Wichtiger Hinweis: Der Regex im Frontend und der Regex im Backend müssen ein und derselbe sein**, sonst entsteht der ärgerlichste aller Bugs: „Das Frontend lässt es durch, das Backend lehnt es ab." Ideal ist, die Regel einmal im Backend zu definieren und sie über das JSON Schema (Kapitel 7) automatisch ans Frontend zu übergeben — `pattern` taucht dort unverändert im Schema auf.

### 3.3 Fortgeschrittene String-Verarbeitung: StringConstraints

**Welches Problem wird gelöst**: Nicht nur „prüfen", sondern gleich „mitreinigen" — Leerzeichen entfernen, in Groß- oder Kleinbuchstaben umwandeln.

`Field()` kann solche Anforderungen nicht ausdrücken, dafür braucht es `StringConstraints`:

```python
from typing import Annotated
from pydantic import BaseModel, StringConstraints


class Form(BaseModel):
    code: Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True)]


print(Form(code="  ab12 ").code)
```

```text
AB12
```

| Parameter | Wirkung |
|---|---|
| `strip_whitespace=True` | entfernt führende und abschließende Leerzeichen |
| `to_upper=True` / `to_lower=True` | wandelt in Groß- / Kleinbuchstaben um |
| `min_length` / `max_length` / `pattern` | wie bei `Field()` |

> 👉 **CEO-Perspektive**: Das entspricht einer Produktregel, die gern übersehen wird, im Produktivbetrieb aber garantiert Ärger macht — **Leerzeichen am Anfang und Ende von Nutzereingaben**. Beim Kopieren eines Gutscheincodes nimmt der Nutzer fast zwangsläufig Leerzeichen mit; und `Foo@Bar.com` sollte als dieselbe Adresse gelten wie `foo@bar.com`. Statt ins Pflichtenheft zu schreiben „das Frontend macht ein Trim", lassen Sie das Backend in der Validierungsschicht einheitlich trimmen. **Reinigungsregeln gehören zum Datenvertrag, nicht zu einer einzelnen Seite des Systems.**

### 3.4 Beschränkungen für Sammlungen: min_length / max_length auf Listen

**Welches Problem wird gelöst**: Mengenregeln der Art „mindestens 1, höchstens 20 Artikel im Warenkorb" oder „höchstens 3 Tags auswählbar".

Dieselben Parameter `min_length` / `max_length` beziehen sich, an eine Liste gehängt, auf die **Anzahl der Elemente**, nicht auf die Zeichenzahl.

```python
class Cart(BaseModel):
    items: list[str] = Field(min_length=1, max_length=20, description="购物车明细")
    tags: list[str] = Field(default_factory=list, max_length=3)


try:
    Cart(items=[], tags=["a", "b", "c", "d"])
except ValidationError as e:
    print(e)
```

```text
2 validation errors for Cart
items
  List should have at least 1 item after validation, not 0 [type=too_short, input_value=[], input_type=list]
    For further information visit https://errors.pydantic.dev/2.13/v/too_short
tags
  List should have at most 3 items after validation, not 4 [type=too_long, input_value=['a', 'b', 'c', 'd'], input_type=list]
    For further information visit https://errors.pydantic.dev/2.13/v/too_long
```

> 👉 **CEO-Perspektive**: „Der Warenkorb darf nicht leer sein", „höchstens 3 Tags", „maximal 1000 Datensätze pro Massenimport" — das sind alles Längenbeschränkungen für Sammlungen. Im Pflichtenheft die Obergrenze ausdrücklich zu nennen ist wichtig: Sie ist zugleich **Produktregel** und **Schutz vor Missbrauch**.

### 3.5 Standardwerte: default und default_factory

**Welches Problem wird gelöst**: Ein Rückfallwert, wenn ein Feld nicht ausgefüllt wird.

```python
from datetime import datetime
import uuid


class Order(BaseModel):
    order_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    created_at: datetime = Field(default_factory=datetime.now)
    tags: list[str] = Field(default_factory=list)
    status: str = "pending"          # einfache Konstante, Gleichheitszeichen genügt


o1 = Order()
o2 = Order()
print(o1.order_id != o2.order_id, "两次生成的 id 不同")
o1.tags.append("vip")
print("o1.tags:", o1.tags, "o2.tags:", o2.tags)
```

```text
True 两次生成的 id 不同
o1.tags: ['vip'] o2.tags: []
```

| Schreibweise | Wofür | Beispiel |
|---|---|---|
| `= "pending"` | feste, unveränderliche Konstante | Standardstatus, Schalter standardmäßig aus |
| `Field(default_factory=...)` | Werte, die **jedes Mal neu berechnet** werden | aktuelle Uhrzeit, zufällige ID, leere Liste |

> ⚠️ **Fallstrick**: Für Standardwerte veränderlicher Typen (Listen, Dictionaries) **muss** `default_factory=list` bzw. `default_factory=dict` verwendet werden. Die Ausgabe oben belegt, dass ein Tag an `o1` nicht auf `o2` durchschlägt — würde eine gemeinsame Liste verwendet, teilten sich alle Bestellungen dieselbe Tag-Liste, einer der klassischsten Bugs in Python überhaupt. (Pydantic legt bei `= []` zwar eine schützende Kopie an, das explizite `default_factory` ist aber die robustere und ausdrucksstärkere Schreibweise.)

> 👉 **CEO-Perspektive**: Der Unterschied zwischen `default` und `default_factory` entspricht dem Unterschied zwischen „**Standardwert**" und „**Regel zur automatischen Erzeugung**" im Pflichtenheft. „Der Bestellstatus ist standardmäßig ‚zahlungsoffen'" ist eine Konstante; „die Bestellnummer wird automatisch erzeugt" und „der Anlagezeitpunkt ist die aktuelle Zeit" sind Regeln. Wenn Sie die automatisch erzeugten Felder im Pflichtenheft in einem eigenen Abschnitt aufführen, wissen die Entwickler sofort, dass sie `default_factory` einsetzen müssen.

### 3.6 Der Klassiker: „sieht aus wie ein Standardwert, ist aber Pflicht"

```python
class Bad(BaseModel):
    a: int = Field(description="看起来像有默认值，其实是必填")


try:
    Bad()
except ValidationError as e:
    print(e)
```

```text
1 validation error for Bad
a
  Field required [type=missing, input_value={}, input_type=dict]
```

Das Gleichheitszeichen in `a: int = Field(...)` **ist kein Standardwert**, es hängt lediglich das „Konfigurationspaket" `Field()` an das Feld. Solange kein `default=` angegeben ist, bleibt das Feld Pflicht.

> ⚠️ **Fallstrick**: Das ist der Fallstrick, in den Pydantic-Neulinge am häufigsten tappen. Man sieht das Gleichheitszeichen, hält das Feld für optional — und im Produktivbetrieb kommt dauerhaft `missing` zurück.

Empfehlenswert ist die `Annotated`-Schreibweise, die diese Mehrdeutigkeit vermeidet:

```python
from typing import Annotated

class Good(BaseModel):
    a: Annotated[int, Field(description="必填，一眼看得出")]          # Pflicht
    b: Annotated[int, Field(ge=0, description="选填")] = 1           # Gleichheitszeichen = optional

try:
    Good()
except ValidationError as e:
    print("Good 同样必填:", e.errors()[0]["type"])
```

```text
Good 同样必填: missing
```

### 3.7 Zwei Schreibweisen: Zuweisungsform vs. Annotated-Form

**Welches Problem wird gelöst**: Dasselbe `Field()` lässt sich auf zwei Arten anhängen — wann verwendet man welche?

```python
# Schreibweise A: Zuweisungsform (assignment form)
class M1(BaseModel):
    price: float = Field(gt=0, description="单价")

# Schreibweise B: Annotated-Form (annotated pattern)
class M2(BaseModel):
    price: Annotated[float, Field(gt=0, description="单价")]
```

| Vergleichspunkt | Zuweisungsform `x: T = Field(...)` | Annotated-Form `x: Annotated[T, Field(...)]` |
|---|---|---|
| Lesbarkeit | kurz, am weitesten verbreitet | etwas umständlicher |
| Pflicht/optional auf einen Blick erkennbar | ❌ mehrdeutig (siehe 3.6) | ✅ nur mit Gleichheitszeichen optional |
| Mehrere Metadaten kombinierbar | nur ein einziges `Field()` | ✅ beliebig viele kombinierbar |
| `default` / `default_factory` / `alias` | ✅ **hierfür diese Form verwenden** | ⚠️ vom Typprüfer nicht erkannt |
| Typalias wiederverwendbar | ❌ | ✅ `Score = Annotated[int, Field(ge=0, le=100)]` |

Annotated kann mehrere Quellen von Beschränkungen übereinanderlegen:

```python
from annotated_types import Gt, Le

class M(BaseModel):
    score: Annotated[int, Gt(0), Le(100), Field(description="0-100 分")]


print(M(score=88))
try:
    M(score=101)
except ValidationError as e:
    print(e.errors()[0]["msg"])
```

```text
score=88
Input should be less than or equal to 100
```

**Praktische Empfehlung**:
- Standardwerte und Aliasse → Zuweisungsform verwenden (`= Field(default=..., alias=...)`);
- Wenn Sie „die Regeln einer Feldkategorie" an mehreren Stellen wiederverwenden wollen → einen `Annotated`-Typalias definieren.

Beispiel für Wiederverwendung:

```python
Score = Annotated[int, Field(ge=0, le=100, description="0-100 分")]

class Exam(BaseModel):
    chinese: Score
    math: Score
    english: Score
```

> 👉 **CEO-Perspektive**: Ein `Annotated`-Typalias = das „**Felderverzeichnis / die Datenelement-Definition**" aus dem Pflichtenheft. Große Unternehmen pflegen stets eine „Standarddefinition der Mobilnummer" und eine „Standarddefinition des Betrags", auf die sich alle Module beziehen, statt dass jedes seine eigene erfindet. `Score = Annotated[int, Field(ge=0, le=100)]` schreibt genau dieses Felderverzeichnis in den Code: einmal geändert, wirkt es überall.

> ⚠️ **Fallstrick**: Feldspezifische Metadaten (`alias`, `deprecated`) müssen am **äußersten Typ** hängen. Die folgenden beiden Zeilen unterscheiden sich erheblich:
>
> ```python
> class M(BaseModel):
>     field_bad: Annotated[int, Field(deprecated=True)] | None = None   # wirkungslos
>     field_ok: Annotated[int | None, Field(deprecated=True)] = None    # wirksam
> ```
>
> Bei tatsächlicher Ausführung gibt 2.13.4 direkt eine Warnung aus:
> ```text
> UnsupportedFieldAttributeWarning: The 'deprecated' attribute with value True was provided to
> the `Field()` function, which has no effect in the context it was used.
> ```
> Beim Lesen von `field_bad` erscheint keine Verfallswarnung, beim Lesen von `field_ok` schon. Der Unterschied liegt darin, ob `Field()` um das gesamte `int | None` gelegt ist oder nur um `int`.

### 3.8 description: Feldern eine Erläuterung mitgeben

**Welches Problem wird gelöst**: Die fachliche Bedeutung einer Spalte steht im Code selbst und lässt sich automatisch in Dokumentation exportieren.

```python
class Feedback(BaseModel):
    score: int = Field(ge=1, le=5, description="满意度打分，1 最差 5 最好")
```

`description` nimmt nicht an der Validierung teil, erscheint aber **unverändert im JSON Schema** (zu sehen in Kapitel 7).

> 👉 **CEO-Perspektive**: **Das ist der Parameter, der einen CEO in diesem gesamten Kapitel am meisten interessieren sollte.**
>
> `description` ist der einzige Ort, an dem der von Ihnen formulierte fachliche Erklärungssatz Platz findet. Er fließt an drei Stellen:
> 1. in die automatisch erzeugte API-Dokumentation → für Frontend und Drittanbieter;
> 2. in automatisch erzeugte Formularhinweise → für die Nutzer;
> 3. **in den Prompt für das LLM → entscheidet darüber, ob das Modell richtig ausfüllt** ★
>
> Der dritte Punkt ist das Herzstück des weiteren Buchs. Wenn Sie Pydantic AI einsetzen und das Modell „aus diesem Dialog das Anliegen des Nutzers extrahieren" lassen, sieht das Modell genau die `description`, die Sie geschrieben haben. **Ist die `description` unscharf formuliert, füllt das Modell unscharf aus.** Sie ist damit kein „Kommentar" mehr, sondern Teil des Prompts. Bei Reviews lohnt es sich, gezielt zu prüfen, wie gut diese Felderläuterungen formuliert sind.

### 3.9 alias: Der Name eines Feldes nach außen

**Welches Problem wird gelöst**: Interner Feldname und externer Schnittstellenname stimmen nicht überein (intern `user_name`, in der Schnittstelle `userName`).

```python
class ApiUser(BaseModel):
    user_name: str = Field(alias="userName")
    is_vip: bool = Field(alias="isVIP", default=False)


au = ApiUser.model_validate({"userName": "tom", "isVIP": True})
print(au)                              # intern in Snake-Case-Schreibweise
print(au.model_dump())                 # Export standardmäßig unter den internen Namen
print(au.model_dump(by_alias=True))    # Export unter den externen Namen
```

```text
user_name='tom' is_vip=True
{'user_name': 'tom', 'is_vip': True}
{'userName': 'tom', 'isVIP': True}
```

> ⚠️ **Fallstrick**: Ist ein `alias` gesetzt, wird **standardmäßig nur noch der externe Name akzeptiert**:

```python
try:
    ApiUser(user_name="tom")
except ValidationError as e:
    print(e)
```

```text
1 validation error for ApiUser
userName
  Field required [type=missing, input_value={'user_name': 'tom'}, input_type=dict]
```

Sollen beide Namen akzeptiert werden, setzen Sie die Konfiguration `populate_by_name=True` (**Achtung**: Seit Pydantic 2.11+ empfiehlt das Projekt offiziell das gleichwertige `ConfigDict(validate_by_name=True, validate_by_alias=True)`; `populate_by_name` soll in v3 wegfallen, für neue Projekte ist die neue Schreibweise ratsam):

```python
class ApiUser2(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    user_name: str = Field(alias="userName")


print(ApiUser2(user_name="tom"))
print(ApiUser2(userName="jerry"))
```

```text
user_name='tom'
user_name='jerry'
```

**Ein- und Ausgang dürfen unterschiedliche Namen verwenden**:

```python
class Split(BaseModel):
    n: str = Field(validation_alias="inputName", serialization_alias="outputName")


s = Split.model_validate({"inputName": "x"})
print(s.model_dump(), s.model_dump(by_alias=True))
```

```text
{'n': 'x'} {'outputName': 'x'}
```

**Mehrere vorgelagerte Feldnamen unterstützen** (die alte Schnittstelle nennt es `uid`, die neue `userId`):

```python
from pydantic import AliasChoices

class Compat(BaseModel):
    user_id: int = Field(validation_alias=AliasChoices("uid", "userId", "user_id"))


for k in ["uid", "userId", "user_id"]:
    print(k, "->", Compat.model_validate({k: 7}))
```

```text
uid -> user_id=7
userId -> user_id=7
user_id -> user_id=7
```

| Parameter | Wofür zuständig |
|---|---|
| `alias` | dieser Name gilt für Eingang und Ausgang |
| `validation_alias` | regelt nur, welcher Name „beim Hereinkommen" akzeptiert wird |
| `serialization_alias` | regelt nur, wie das Feld „beim Hinausgehen" heißt |
| `AliasChoices(...)` | akzeptiert beim Hereinkommen mehrere Namenskandidaten |

> 👉 **CEO-Perspektive**: alias entspricht der **Feldzuordnungstabelle bei Systemanbindungen**. Jeder CEO, der schon eine ERP-Anbindung, eine Zahlungsdienstleister-Integration oder den Anschluss an eine Datenplattform begleitet hat, kennt jene Excel-Tabelle: „unser Feld / Feld der Gegenseite / Umwandlungsregel". alias schreibt genau diese Zuordnungstabelle in den Code.
>
> `AliasChoices` entspricht besonders einem realen Szenario: der **Übergangsphase beim Versionswechsel einer Schnittstelle**. Die alte App sendet noch `uid`, die neue `userId`, und der Server muss beides akzeptieren, bis die Nutzerzahl der alten Version so weit gesunken ist, dass sie abgeschaltet werden kann. Im Pflichtenheft heißt das „Abwärtskompatibilität", im Code ist es genau diese eine Zeile.

### 3.10 examples: Beispiele für ein Feld angeben

```python
class P(BaseModel):
    sku: str = Field(description="商品编码", examples=["SKU-001", "SKU-002"],
                     json_schema_extra={"x-internal": True})
```

Der erzeugte Schema-Ausschnitt:

```json
{
  "sku": {
    "description": "商品编码",
    "examples": ["SKU-001", "SKU-002"],
    "title": "Sku",
    "type": "string",
    "x-internal": true
  }
}
```

`json_schema_extra` erlaubt es, beliebige eigene Schlüssel in die Spezifikation zu schreiben (etwa Markierungen für interne Werkzeuge).

> 👉 **CEO-Perspektive**: `examples` fließt in die API-Dokumentation und ebenso in die Spezifikation, die dem LLM vorgelegt wird. **Dem LLM ein Beispiel zu geben ist oft wirksamer als drei Zeilen Beschreibung** — das ist der Few-Shot-Gedanke aus dem Prompt Engineering, und hier genügt dafür das Ausfüllen eines einzigen Parameters.

---
## 4. Das Typsystem: Was darf in diese Spalte eigentlich hinein?

Typannotationen sind das Fundament von Pydantic. Dieses Kapitel geht die gebräuchlichen Typen der Reihe nach durch.

### 4.0 Gesamtübersicht der Typkategorien

| Kategorie | Typische Schreibweise | Entsprechung in Excel/Formular |
|---|---|---|
| Basis-Skalare | `str` `int` `float` `bool` | Text / Ganzzahl / Dezimalzahl / Checkbox |
| Zeit | `date` `datetime` `time` `timedelta` | Datumsauswahl |
| Exakte Zahlen | `Decimal` | Geldbeträge (kein Gleitkomma-Fehler erlaubt) |
| Nullable | `str \| None` | Zelle, die leer bleiben darf |
| Feste Auswahl | `Literal["A","B"]` / `Enum` | Dropdown |
| Verschachtelung | `Address` (ein weiteres BaseModel) | Untertabelle / Positionstabelle |
| Sammlungen | `list[X]` `dict[str,X]` `set[X]` `tuple[X,Y]` | Mehrzeilige Positionen / Schlüssel-Wert-Paare / duplikatfreie Liste |
| Netzwerktypen | `HttpUrl` `EmailStr` `IPvAnyAddress` | Spezielle Eingabefelder mit Formatvalidierung |
| Verzweigung | `Annotated[A \| B, Field(discriminator=...)]` | Verkettetes Formular (Kapitel 8) |
| Beliebig | `Any` | Freies Feld ohne Validierung |

### 4.1 Basistypen und Coercion-Regeln

**Welches Problem löst das**: Externe Daten sind typmäßig nie sauber; es braucht einen klaren Regelsatz dafür, „was umgewandelt werden darf und was nicht".

```python
from decimal import Decimal
from datetime import date, datetime


class Coerce(BaseModel):
    i: int
    f: float
    b: bool
    s: str
    d: date
    dt: datetime
    dec: Decimal


x = Coerce(i="42", f="3.14", b="yes", s="hello", d="2024-01-01",
           dt="2024-01-01T10:30:00", dec="19.99")
print(x)
```

```text
i=42 f=3.14 b=True s='hello' d=datetime.date(2024, 1, 1) dt=datetime.datetime(2024, 1, 1, 10, 30) dec=Decimal('19.99')
```

Was sich nicht umwandeln lässt:

```text
  i='abc' -> 失败: Input should be a valid integer, unable to parse string as an integer
  i=3.7   -> 失败: Input should be a valid integer, got a number with a fractional part
  s=123   -> 失败: Input should be a valid string
  b='maybe' -> 失败: Input should be a valid boolean, unable to interpret input
```

**Kurzreferenz der Umwandlungsregeln**:

| Zieltyp | Akzeptiert | Abgelehnt |
|---|---|---|
| `int` | `"42"`, `42.0` | `"abc"`, `3.7` (Nachkommastellen – Präzisionsverlust droht) |
| `float` | `"3.14"`, `3`, `Decimal` | `"abc"` |
| `str` | Nur Zeichenketten | **Die Zahl `123` wird abgelehnt** (verhindert, dass eine ID versehentlich zur Zeichenkette wird) |
| `bool` | `1/0`, `"true"/"false"`, `"yes"/"no"`, `"on"/"off"`, `"1"/"0"` | `2`, `"maybe"` |
| `date` | `"2024-01-01"`, Zeitstempel | `"2024/13/45"` |
| `Decimal` | `"19.99"`, Zahlen | Nicht-numerischer Text |

Welche Werte `bool` tatsächlich akzeptiert – einmal praktisch durchgetestet:

```text
  1 -> True        0 -> False
  'true' -> True   'True' -> True
  'yes' -> True    'on' -> True
  '1' -> True      '0' -> False
  'no' -> False
  2 -> 报错
```

> ⚠️ **Fallstrick**: Ein `int`-Feld lehnt `3.7` ab, akzeptiert aber `42.0`. Die Logik lautet: „Es darf keine Information verloren gehen." Analog lehnt ein `str`-Feld die Zahl `123` ab, denn Pydantic geht davon aus: „Sie haben Text deklariert – kommt eine Zahl an, hat sich mit ziemlicher Sicherheit das vorgelagerte System vertan."

> 👉 **CEO-Perspektive**: Diese Tabelle ist die stillschweigende Vereinbarung zwischen Ihnen und Ihren Entwicklern darüber, „**was mit schmutzigen Daten geschieht**". Achten Sie besonders auf die Zeile zu `bool`: Wenn das Operations-Team Daten aus Excel importiert, kann in der Ja/Nein-Spalte `1`, `是`, `Y`, `true` oder `TRUE` stehen – Pydantic erkennt nur die letzten davon. **`"是"` und `"Y"` werden nicht erkannt.** Das heißt: Im PRD der Importfunktion muss unmissverständlich stehen, „welche Schreibweisen eine boolesche Spalte akzeptiert", sonst scheitert jeder einzelne Importversuch.
>
> Und dann `Decimal`: **Sobald es um Geld geht, gehört `Decimal` hin und nicht `float`.** In `float` ergibt 0.1 + 0.2 den Wert 0.30000000000000004; beim Aufsummieren von Beträgen führt das zu Vorfällen, bei denen die Abrechnung um einen Cent nicht aufgeht. Dieser Punkt gehört in die Feldkonventionen Ihres Teams.

### 4.2 Optional: nullable ≠ optional

**Welches Problem löst das**: Die Unterscheidung zwischen „dieses Feld muss nicht übergeben werden" und „dieses Feld darf einen leeren Wert tragen" – produktseitig sind das zwei verschiedene Dinge.

```python
class A(BaseModel):
    a: str | None          # Pflicht, aber der Wert darf None sein
    b: str | None = None   # optional, ohne Angabe None
    c: str = "默认值"       # optional, ohne Angabe "默认值"


print(A(a=None))
try:
    A()                    # nur a löst einen Fehler aus
except ValidationError as e:
    print([(x["loc"], x["type"]) for x in e.errors()])
```

```text
a=None b=None c='默认值'
[(('a',), 'missing')]
```

| Schreibweise | Pflicht? | None erlaubt? | Bedeutung im Produkt |
|---|---|---|---|
| `x: str` | ✅ Pflicht | ❌ | Pflicht und muss einen Wert haben |
| `x: str \| None` | ✅ Pflicht | ✅ | **Stellungnahme erzwungen**, aber „keine Angabe" ist eine zulässige Stellungnahme |
| `x: str \| None = None` | ❌ optional | ✅ | Kann ignoriert werden |
| `x: str = "默认值"` | ❌ optional | ❌ | Ohne Angabe gilt der Standardwert |

`Optional[str]` und `str | None` sind vollkommen gleichwertig; Ersteres ist die ältere Schreibweise:

```python
from typing import Optional

class O(BaseModel):
    x: Optional[str]   # immer noch Pflicht!


try:
    O()
except ValidationError as e:
    print(e.errors()[0]["type"], e.errors()[0]["loc"])
print(O(x=None))
```

```text
missing ('x',)
x=None
```

> ⚠️ **Fallstrick**: Der Begriff `Optional` ist ausgesprochen irreführend gewählt. Er bedeutet „**der Wert darf leer sein**", nicht „**das Feld darf fehlen**". Für „darf fehlen" müssen Sie zusätzlich `= None` angeben.

> 👉 **CEO-Perspektive**: Die zweite Zeile `x: str | None` (Pflicht, aber None erlaubt) entspricht einem sehr wertvollen Produktmuster – der **erzwungenen Stellungnahme**. Denken Sie an die Frage „Bestehen Allergien?" in einem Fragebogen: Überspringen darf der Nutzer sie nicht, aber „keine" ankreuzen sehr wohl. „Nicht ausgefüllt" und „mit Nein ausgefüllt" sind zwei völlig verschiedene Datenqualitäten.
>
> Umgekehrt gilt: Steht in Ihrem PRD nur „optional", schreibt der Entwickler mit hoher Wahrscheinlichkeit die dritte Zeile. **Bei den drei Begriffen „optional", „darf leer sein" und „hat einen Standardwert" muss im Anforderungs-Review klar gesagt werden, welcher gemeint ist.**

### 4.3 Literal: die fest verdrahteten Optionen

**Welches Problem löst das**: das Dropdown – dieses Feld darf nur einen aus einer festen Menge von Werten annehmen.

```python
from typing import Literal


class Ticket(BaseModel):
    priority: Literal["P0", "P1", "P2"]
    channel: Literal["app", "web", "wechat"] = "app"


print(Ticket(priority="P0"))
try:
    Ticket(priority="紧急")
except ValidationError as e:
    print(e)
```

```text
priority='P0' channel='app'
1 validation error for Ticket
priority
  Input should be 'P0', 'P1' or 'P2' [type=literal_error, input_value='紧急', input_type=str]
```

Beachten Sie die Fehlermeldung `Input should be 'P0', 'P1' or 'P2'` – sie **listet automatisch alle zulässigen Optionen auf**.

> 👉 **CEO-Perspektive**: `Literal` ist das **Dropdown bzw. die Radiobutton-Gruppe** und entspricht der „Liste" in der Excel-Datenüberprüfung. Zustände als `str` zu führen ist eine schlechte Angewohnheit – das entspricht einem freien Textfeld: Das Operations-Team schreibt „erledigt", „abgeschlossen", „done", „DONE", und alles davon lässt sich speichern; am Ende ist die Auswertungsbasis vollkommen inkonsistent.
>
> Zudem hat `Literal` einen zusätzlichen Vorteil: **Die Optionsliste wandert automatisch ins JSON Schema, wird dort zu den Dropdown-Optionen und zugleich zur Liste zulässiger Werte für das LLM** (Kapitel 7). Das heißt: Die Aufzählungswerte, die Sie im PRD definieren, fließen automatisch bis ins Frontend und in die KI durch – Sie müssen sie nicht an drei Stellen getrennt pflegen.

### 4.4 Enum: den Optionen Namen geben

**Welches Problem löst das**: Wenn es viele Optionen gibt, sie wiederverwendet werden sollen oder im Code über einen Namen referenziert werden, reicht `Literal` nicht mehr aus.

```python
from enum import Enum


class Status(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


class Post(BaseModel):
    status: Status


p = Post(status="published")
print(p, "|", p.status is Status.PUBLISHED)
print(p.model_dump())
print(p.model_dump(mode="json"))
```

```text
status=<Status.PUBLISHED: 'published'> | True
{'status': <Status.PUBLISHED: 'published'>}
{'status': 'published'}
```

| Vergleich | `Literal` | `Enum` |
|---|---|---|
| Schreibaufwand | Einfach, eine Zeile | Erfordert eine eigene Klasse |
| Wiederverwendung | Kopieren und Einfügen | ✅ Einmal definiert, vielfach referenziert |
| Referenz im Code | Nur als Zeichenkette `"published"` | ✅ `Status.PUBLISHED` |
| Im JSON Schema | `enum: [...]` | `enum: [...]` (mit zusätzlicher `$ref`-Ebene) |
| Serialisierung | Direkt eine Zeichenkette | Standardmäßig ein Enum-Objekt; erst `mode="json"` liefert eine Zeichenkette |

> ⚠️ **Fallstrick**: `model_dump()` liefert Ihnen standardmäßig ein **Enum-Objekt**, keine Zeichenkette. Entweder Sie verwenden `model_dump(mode="json")` oder Sie aktivieren die Konfiguration `use_enum_values=True` (siehe 10.6).

> 👉 **CEO-Perspektive**: Wenige Optionen, die nur an einer Stelle vorkommen → `Literal`; Optionen, die über mehrere Module hinweg geteilt werden und einen „fachlichen Namen" tragen (etwa die Zustände einer „Bestell-Zustandsmaschine") → `Enum`. Letzteres entspricht eher jenem eigenständigen Abschnitt im PRD, der „**Tabelle der Statuswerte**" – hier lohnt es sich, jedem Zustand einen offiziellen Namen zu geben.

### 4.5 Verschachtelte Modelle: Tabelle in Tabelle

**Welches Problem löst das**: Ein Geschäftsobjekt enthält ein weiteres Geschäftsobjekt – eine Bestellung enthält eine Lieferadresse, ein Kunde hat mehrere Ansprechpartner.

```python
class Address(BaseModel):
    province: str
    city: str
    detail: str


class Contact(BaseModel):
    name: str
    phone: str = Field(pattern=r"^1\d{10}$")


class Customer(BaseModel):
    name: str
    address: Address                                   # eins zu eins
    contacts: list[Contact] = Field(default_factory=list)   # eins zu viele


c = Customer.model_validate({
    "name": "字节跳动",
    "address": {"province": "北京", "city": "北京", "detail": "海淀区"},
    "contacts": [{"name": "小王", "phone": "13800138000"}],
})
print(c)
print(c.address.city, c.contacts[0].name)
```

```text
name='字节跳动' address=Address(province='北京', city='北京', detail='海淀区') contacts=[Contact(name='小王', phone='13800138000')]
北京 小王
```

Fehlermeldungen aus Verschachtelungen **lokalisieren die betroffene Ebene exakt**:

```python
try:
    Customer.model_validate({
        "name": "X",
        "address": {"province": "北京", "city": "北京"},        # detail fehlt
        "contacts": [{"name": "小王", "phone": "123"}],         # Mobilnummer ungültig
    })
except ValidationError as e:
    print(e)
```

```text
2 validation errors for Customer
address.detail
  Field required [type=missing, input_value={'province': '北京', 'city': '北京'}, input_type=dict]
contacts.0.phone
  String should match pattern '^1\d{10}$' [type=string_pattern_mismatch, input_value='123', input_type=str]
```

`contacts.0.phone` = „das Feld phone des nullten Elements in der Liste contacts".

> 👉 **CEO-Perspektive**: Verschachtelte Modelle = **Haupttabelle + Untertabelle**. Bestellung (Haupttabelle) + Bestellpositionen (Untertabelle) ist das klassischste Beispiel.
>
> Achten Sie besonders auf die Fehlerlokalisierung `contacts.0.phone`. Produktseitig ist das außerordentlich nützlich: Ein Nutzer importiert 100 Datenzeilen auf einmal, in Zeile 37 stimmt das Format der Mobilnummer nicht – die Fehlermeldung nennt Ihnen exakt „Spalte phone in Zeile 37" statt eines pauschalen „Import fehlgeschlagen". **Wie gut die Fehlerhinweise einer Massenimport-Funktion sind, hängt zu einem großen Teil davon ab, ob diese Positionsangabe sinnvoll genutzt wird.**

### 4.6 Selbstreferenz: Baumstrukturen

**Welches Problem löst das**: Kategoriebäume, Organigramme, verschachtelte Kommentare – unter einem Knoten hängen Knoten derselben Art.

```python
class Category(BaseModel):
    name: str
    children: list["Category"] = []      # Selbstreferenz, daher in Anführungszeichen


c = Category.model_validate({
    "name": "电子产品",
    "children": [{"name": "手机", "children": [{"name": "安卓机"}]}],
})
print(c.model_dump())
```

```text
{'name': '电子产品', 'children': [{'name': '手机', 'children': [{'name': '安卓机', 'children': []}]}]}
```

> 👉 **CEO-Perspektive**: Kategoriebäume, Abteilungsbäume, Berechtigungsbäume, mehrstufige Kommentare – jede Produktstruktur mit „beliebig vielen Ebenen" folgt diesem Modell. Pydantic **validiert jede Ebene rekursiv**, ein verkorkster Baum wird also bereits am Eingang abgefangen.

### 4.7 Sammlungstypen

**Welches Problem löst das**: Ein Feld soll mehrere Werte aufnehmen, mit Anforderungen an „Duplikatfreiheit, Reihenfolge und Wiederholbarkeit".

```python
class Coll(BaseModel):
    tags: list[str]           # geordnet, Duplikate erlaubt
    unique_ids: set[int]      # ungeordnet, automatisch dedupliziert
    scores: dict[str, float]  # Schlüssel-Wert-Paare
    point: tuple[int, int]    # feste Länge, Position hat Bedeutung


cc = Coll(tags=("a", "b"), unique_ids=[1, 2, 2, 3],
          scores={"math": "90.5"}, point=[1, 2])
print(cc)
print(type(cc.tags), type(cc.unique_ids))
```

```text
tags=['a', 'b'] unique_ids={1, 2, 3} scores={'math': 90.5} point=(1, 2)
<class 'list'> <class 'set'>
```

Drei Beobachtungen:
1. Hineingegeben wird ein Tupel `("a","b")`, heraus kommt eine Liste – Pydantic konvertiert nach dem von Ihnen **deklarierten Typ**;
2. `set[int]` dedupliziert `[1,2,2,3]` automatisch zu `{1,2,3}`;
3. Auch die Elemente innerhalb der Sammlung **werden validiert und konvertiert** (`"90.5"` → `90.5`).

| Typ | Geordnet | Duplikate | Typischer Einsatz |
|---|---|---|---|
| `list[X]` | ✅ | ✅ | Bestellpositionen, Aktionsprotokolle |
| `set[X]` | ❌ | ❌ automatisch dedupliziert | Tag-Mengen, Berechtigungsmengen |
| `dict[str, X]` | — | Schlüssel eindeutig | Konfigurationseinträge, mehrsprachige Texte |
| `tuple[X, Y]` | ✅ | Feste Länge | Koordinaten, Intervalle `(min, max)` |

> 👉 **CEO-Perspektive**: Ob `list` oder `set` gewählt wird, ist **eine Produktentscheidung und kein technisches Detail**.
> - „Welche Tags hat der Nutzer ausgewählt" → `set`, denn ein zweimal gewähltes Tag darf nur einmal zählen;
> - „Der Browserverlauf des Nutzers" → `list`, denn die Reihenfolge hat Bedeutung und wiederholte Besuche ebenfalls.
>
> Steht in Ihrem PRD nur „Tag-Liste", greift der Entwickler zu `list` – und schon haben Sie den Bug „dasselbe Tag erscheint zweimal". **Schreiben Sie das Wort „duplikatfrei" ausdrücklich hin.**

### 4.8 Spezialtypen: URL, E-Mail

**Welches Problem löst das**: Für gängige Formatprüfungen müssen Sie keine eigenen regulären Ausdrücke schreiben.

```python
from pydantic import HttpUrl, EmailStr


class Special(BaseModel):
    url: HttpUrl
    email: EmailStr


sp = Special(url="https://example.com/path", email="a@b.com")
print(sp)
print(sp.model_dump(mode="json"))
```

```text
url=HttpUrl('https://example.com/path') email='a@b.com'
{'url': 'https://example.com/path', 'email': 'a@b.com'}
```

Pydantic bringt eine ganze Reihe solcher Typen mit: `HttpUrl`, `AnyUrl`, `EmailStr`, `IPvAnyAddress`, `UUID4`, `PositiveInt`, `NonNegativeFloat`, `SecretStr` und weitere.

> ⚠️ **Fallstrick**: `EmailStr` erfordert die zusätzliche Installation von `pydantic[email]`, sonst erhalten Sie eine Fehlermeldung mit der Aufforderung, `email-validator` zu installieren.

> 👉 **CEO-Perspektive**: Reguläre Ausdrücke für E-Mail-Formate sind berüchtigt dafür, dass man sie kaum korrekt hinbekommt (die Regeln für gültige Adressen sind weit komplexer, als die meisten annehmen). Ein eingebauter Typ bedeutet: **Diese Regel pflegt die Bibliothek, nicht Ihre Entwickler.**
>
> Am Rande noch `SecretStr`: Beim Schreiben von Logs erscheint der Wert als `**********`, sodass Passwörter und Schlüssel nicht im Protokoll landen. **Das ist der konkrete Ort im Code, an dem die Compliance-Anforderung „Log-Anonymisierung" umgesetzt wird** – CEOs von Finanz- und Gesundheitsprodukten dürfen hier gezielt nachfragen.

### 4.9 Strict Mode: keine automatische Umwandlung

**Welches Problem löst das**: Bei manchen Feldern ist eine Fehlermeldung allemal besser als eine Vermutung.

```python
class S(BaseModel):
    n: Annotated[int, Field(strict=True)]


try:
    S(n="42")
except ValidationError as e:
    print(e.errors()[0]["msg"])
```

```text
Input should be a valid integer
```

> 👉 **CEO-Perspektive**: Die standardmäßig lockere Umwandlung erspart in 90 % der Fälle Arbeit, doch bei Feldern wie **Betrag, Kontonummer und Bestellnummer** ist „Raten" gefährlich. `strict=True` zu setzen heißt, dem System zu sagen: Diese Spalte muss vom vorgelagerten System explizit typgerecht geliefert werden; ich akzeptiere keinerlei Form von automatischer Interpretation.

---
## 5. Validatoren: Regeln, die sich nicht formulieren lassen, schreiben Sie selbst

`Field()` kann „allgemeine Beschränkungen" ausdrücken (größer als, kleiner als, Länge, reguläre Ausdrücke). Geschäftsregeln sind aber oft komplexer:

- „Ein Gutscheincode muss mit CP beginnen" → eigene Regel für ein einzelnes Feld
- „Das Enddatum einer Kampagne muss nach dem Startdatum liegen" → feldübergreifende Regel
- „Übersteigt die (selbst errechnete) Auftragssumme 50.000, muss ein Freigabeprozess durchlaufen werden" → erst rechnen, dann prüfen

Diese drei Typen entsprechen `field_validator`, `model_validator` und der Kombination aus beiden.

### 5.0 Übersichtstabelle der Validatortypen

| Typ | Dekorator | Zuständig für wie viele Felder | Was er bekommt | Typisches Szenario |
|---|---|---|---|---|
| Feld – before | `@field_validator("x", mode="before")` | 1 Feld | **Rohe Eingabe**, kann alles Mögliche sein | Verschmutzte Daten bereinigen (`¥` entfernen, Kommas entfernen) |
| Feld – after | `@field_validator("x", mode="after")` | 1 Feld | Der bereits **typkonvertierte** Wert | Prüfung von Geschäftsregeln (Standard, empfohlen) |
| Modell – before | `@model_validator(mode="before")` | alle | Das **rohe dict** | Strukturumbau (Verschachtelung flach klopfen, Altformate unterstützen) |
| Modell – after | `@model_validator(mode="after")` | alle | Das **fertig konstruierte Modellobjekt** | Feldübergreifende Validierung, abgeleitete Werte berechnen (empfohlen) |
| Annotationsform | `Annotated[int, AfterValidator(fn)]` | 1 Feld | wie bei after | Wenn eine Regel für mehrere Felder wiederverwendet werden soll |

### 5.1 field_validator: eigene Regel für ein einzelnes Feld

**Welches Problem er löst**: Für diese Spalte gilt eine Geschäftsregel, die sich weder mit einem regulären Ausdruck noch mit einem Wertebereich ausdrücken lässt.

```python
from pydantic import BaseModel, ValidationError, field_validator


class Coupon(BaseModel):
    code: str

    @field_validator("code", mode="after")
    @classmethod
    def code_prefix(cls, v: str) -> str:
        v = v.strip().upper()          # zuerst normalisieren
        if not v.startswith("CP"):     # dann prüfen
            raise ValueError("优惠券码必须以 CP 开头")
        return v                       # den verarbeiteten Wert unbedingt zurückgeben


print(Coupon(code="cp2024"))
try:
    Coupon(code="XX001")
except ValidationError as e:
    print(e)
```

```text
code='CP2024'
1 validation error for Coupon
code
  Value error, 优惠券码必须以 CP 开头 [type=value_error, input_value='XX001', input_type=str]
    For further information visit https://errors.pydantic.dev/2.13/v/value_error
```

Drei Regeln, die Sie sich unbedingt merken müssen:

1. **Sie sollten `@classmethod` hinzufügen (es läuft auch ohne, aber der Typprüfer meldet einen Fehler; die offiziellen Beispiele schreiben es einheitlich so)**, und zwar in der Reihenfolge `@field_validator` oben, `@classmethod` darunter;
2. **Der Wert muss mit `return` zurückgegeben werden** – vergessen Sie das return, wird das Feld zu `None`;
3. Werfen Sie einen `ValueError` (keine andere Exception), dann verpackt Pydantic ihn in einen standardisierten `ValidationError`.

> ⚠️ **Fallstrick**: Achten Sie im Code oben auf die Reihenfolge – **erst `.upper()`, dann die Prüfung `startswith("CP")`**. Prüfen Sie zuerst und wandeln erst danach in Großbuchstaben um, wird die Eingabe `cp2024` (kleingeschrieben) abgelehnt. Das ist der häufigste Logikfehler beim Schreiben von Validatoren: Bereinigung und Prüfung sind in der falschen Reihenfolge.

> 👉 **CEO-Perspektive**: `field_validator` entspricht jener Sorte von Regeln im PRD, die „**über das Format hinaus eine geschäftliche Bedeutung**" haben. Etwa: „Die Ausweisnummer muss den Prüfziffernalgorithmus bestehen", „Die Kartennummer muss die Luhn-Prüfung bestehen", „Die ersten beiden Stellen des Gutscheincodes sind die Kanalkennung".
>
> Wichtiger noch ist der Fehlertext `优惠券码必须以 CP 开头` – **das ist der einzige für Nutzer sichtbare Text, über den Sie (als CEO) unmittelbar entscheiden können**. Die Texte der eingebauten Beschränkungen sind englisch, die Texte eigener Validatoren schreiben Sie. Wenn Sie also im PRD eine eigene Validierungsregel festhalten, **schreiben Sie den Hinweistext gleich mit dazu**.

### 5.2 mode="before" vs. mode="after": Sie bekommen jeweils etwas anderes

**Welches Problem das löst**: Zu verstehen, an welcher Stelle der Fließstrecke ein Validator ausgeführt wird, entscheidet darüber, was Sie bekommen und was Sie damit tun können.

```python
class Demo(BaseModel):
    n: int

    @field_validator("n", mode="before")
    @classmethod
    def show_before(cls, v):
        print(f"  before 拿到: {v!r} ({type(v).__name__})")
        return v

    @field_validator("n", mode="after")
    @classmethod
    def show_after(cls, v: int) -> int:
        print(f"  after  拿到: {v!r} ({type(v).__name__})")
        return v


Demo(n="123")
```

```text
  before 拿到: '123' (str)
  after  拿到: 123 (int)
```

Ein Bild, das die Positionen erklärt:

```text
   原始输入 "123"
       │
       ▼
  ┌─────────────┐
  │ before 校验器│   ← 拿到 '123'（字符串），可以是任何东西
  └─────────────┘
       │
       ▼
  ┌─────────────┐
  │ 类型转换 +   │   ← Pydantic 内置的转换和约束检查
  │ 内置约束     │
  └─────────────┘
       │
       ▼
  ┌─────────────┐
  │ after 校验器 │   ← 拿到 123（整数），类型已保证
  └─────────────┘
       │
       ▼
    最终字段值
```

**Der typische Einsatzzweck von `before`: verschmutzte Daten bereinigen**

```python
class Money(BaseModel):
    amount: float

    @field_validator("amount", mode="before")
    @classmethod
    def clean(cls, v):
        if isinstance(v, str):
            return v.replace("¥", "").replace(",", "").strip()
        return v


print(Money(amount="¥1,299.00"))
```

```text
amount=1299.0
```

Ohne diesen `before`-Validator würde `"¥1,299.00"` schlicht daran scheitern, dass es sich nicht in ein float umwandeln lässt.

| | `before` | `after` |
|---|---|---|
| Ausführungszeitpunkt | **vor** der Typkonvertierung | **nach** der Typkonvertierung |
| Erhaltener Wert | rohe Eingabe, Typ ungewiss | bereits typkonvertiert |
| Hauptzweck | Eingabe **umbauen/bereinigen** | Geschäftsregeln **prüfen** |
| Risiko | hoch (Sie müssen alle Typen selbst behandeln) | niedrig |
| Empfehlung | nur wenn nötig | ✅ Standardwahl |

> 👉 **CEO-Perspektive**: Diese beiden Modi entsprechen zwei verschiedenen Vorgängen im Produkt – **„Vorverarbeitung" und „Prüfung"**.
>
> - `before` = das **Sortieren** beim Wareneingang: aus dem vom Nutzer eingefügten `¥1,299.00` wird `1299.00`, aus dem Vollbreite-Komma aus Excel wird ein normales Komma. Das heißt „dem Nutzer unter die Arme greifen".
> - `after` = die **Prüfung**: Der Betrag ist jetzt eine ordentliche Zahl, und nun wird beurteilt, ob er das Einzellimit überschreitet.
>
> Eine ganz praktische Produktentscheidung: **Was Sie im `before` automatisch für den Nutzer korrigieren können, sollten Sie ihn nicht neu eintippen lassen.** Einen Gutscheincode mit Leerzeichen abzulehnen ist eine schlechte Erfahrung; die Leerzeichen automatisch zu entfernen ist eine gute. Diese Entscheidung gehört zum CEO und in den PRD-Abschnitt „Fehlertoleranz bei Eingaben".

### 5.3 Validatoren in Annotated-Form: wiederverwendbare Regeln

**Welches Problem das löst**: Dieselbe Regel soll für viele Felder und viele Modelle gelten, und Sie wollen den Dekorator nicht ständig kopieren.

```python
from pydantic import AfterValidator
from typing import Annotated


def must_be_even(v: int) -> int:
    if v % 2:
        raise ValueError(f"{v} 不是偶数")
    return v


class Pack(BaseModel):
    qty: Annotated[int, AfterValidator(must_be_even)]


print(Pack(qty=4))
try:
    Pack(qty=5)
except ValidationError as e:
    print(e.errors()[0]["msg"])
```

```text
qty=4
Value error, 5 不是偶数
```

Der Vorteil dieser Schreibweise: Die Validierungsregel steht **direkt neben dem Feld**, man sieht auf einen Blick, welche Regel für dieses Feld gilt; und `Annotated[int, AfterValidator(must_be_even)]` lässt sich benennen und wiederverwenden.

Entsprechend gibt es außerdem `BeforeValidator`, `PlainValidator` und `WrapValidator`.

> 👉 **CEO-Perspektive**: Das ist der Gedanke einer „**Regelbibliothek**". Machen Sie aus „muss gerade sein", „muss ein Werktag sein", „muss ein gültiger Provinzcode sein" jeweils eine wiederverwendbare Regelkomponente und „hängen" Sie sie dann an das Feld. Das ist genau dasselbe, was Sie auf einer Low-Code-Plattform tun, wenn Sie Formularfeldern Validierungsregeln anhängen. Ein Team, das eine gemeinsame Regelbibliothek pflegt, ist besser steuerbar, als wenn jeder seine eigene Variante schreibt.

### 5.4 Ein Validator für mehrere Felder

```python
class Names(BaseModel):
    first: str
    last: str

    @field_validator("first", "last")     # mehrere Feldnamen auflisten
    @classmethod
    def no_space(cls, v: str) -> str:
        return v.strip()


print(Names(first="  A ", last=" B  "))
```

```text
first='A' last='B'
```

Mit `@field_validator("*")` lassen sich auch alle Felder auf einmal treffen.

### 5.5 model_validator: feldübergreifende Regeln

**Welches Problem er löst**: Die Regel betrifft zwei oder mehr Felder, und der Validator eines einzelnen Feldes sieht die Werte der anderen nicht.

```python
from datetime import date
from pydantic import model_validator


class Campaign(BaseModel):
    start: date
    end: date
    budget: float = Field(gt=0)
    spent: float = Field(ge=0, default=0)

    @model_validator(mode="after")
    def check(self):
        if self.end <= self.start:
            raise ValueError("结束时间必须晚于开始时间")
        if self.spent > self.budget:
            raise ValueError(f"已花费 {self.spent} 超过预算 {self.budget}")
        return self          # Achtung: self zurückgeben, nicht cls


print(Campaign(start="2024-01-01", end="2024-02-01", budget=10000, spent=500))
try:
    Campaign(start="2024-03-01", end="2024-02-01", budget=100, spent=500)
except ValidationError as e:
    print(e)
```

```text
start=datetime.date(2024, 1, 1) end=datetime.date(2024, 2, 1) budget=10000.0 spent=500.0
1 validation error for Campaign
  Value error, 结束时间必须晚于开始时间 [type=value_error, input_value={'start': '2024-03-01', '...get': 100, 'spent': 500}, input_type=dict]
```

Beachten Sie beim model_validator mit `mode="after"`:
- **`@classmethod` ist nicht nötig** (er bekommt die Instanz `self`);
- `return self` ist Pflicht;
- Es wird nur der erste Fehler gemeldet – denn sobald eine Exception fliegt, bricht die Verarbeitung ab, anders als bei der Validierung auf Feldebene, die vollständig durchläuft.

> ⚠️ **Fallstrick**: In der Fehlermeldung steht kein konkreter Feldname (`loc` ist leer), denn es handelt sich um einen Fehler des „gesamten Modells". Wenn das Frontend wissen soll, welches Eingabefeld rot aufleuchten muss, müssen Sie das in der Geschäftsschicht selbst festlegen – oder Sie schreiben die Regel zu einem `field_validator` um, der an einem konkreten Feld hängt (dann ist `loc` genau dieses Feld). Beachten Sie: `PydanticCustomError` kann nur den Fehlercode (`type`) und den Text (`msg`) anpassen, **`loc` lässt sich damit nicht ändern**.

> 👉 **CEO-Perspektive**: Feldübergreifende Validierung ist genau das, was im PRD als „**kombinierte Validierungsregeln**" auftaucht – und diese Kategorie wird am häufigsten vergessen. Eine Checkliste:
> - Zeiträume: Ende > Start
> - Beträge im Abgleich: verbraucht ≤ Gesamtsumme, gezahlt = Originalpreis − Rabatt
> - Logischer Ausschluss: Wer „anonym" wählt, darf keine „Namensnennung" eintragen
> - Bedingte Pflichtfelder: Beim Typ „Unternehmen" ist die Gewerbeerlaubnis Pflicht
>
> Solche Regeln sind im PRD meist über das ganze Dokument verstreut; empfehlenswert ist ein **eigener Abschnitt „Feldübergreifende Regeln", in dem sie gebündelt stehen** – dann weiß der Entwickler, dass er `model_validator` schreiben muss.

### 5.6 „Erst rechnen, dann prüfen": das Muster mit dem größten Geschäftswert

**Welches Problem es löst**: Die Grundlage für die Prüfung ist keines der vom Nutzer ausgefüllten Felder, sondern **ein aus mehreren Feldern errechnetes Ergebnis**.

```python
class Order(BaseModel):
    unit_price: float = Field(gt=0)
    qty: int = Field(gt=0)
    discount: float = Field(ge=0, le=1, default=0)
    total: float = 0                      # muss der Nutzer nicht ausfüllen, wir rechnen es aus

    @model_validator(mode="after")
    def calc_total(self):
        # Schritt eins: rechnen
        self.total = round(self.unit_price * self.qty * (1 - self.discount), 2)
        # Schritt zwei: prüfen
        if self.total > 50000:
            raise ValueError(f"单笔订单金额 {self.total} 超过 50000，需要走审批流")
        return self


print(Order(unit_price=99.9, qty=3, discount=0.1))
try:
    Order(unit_price=9999, qty=10)
except ValidationError as e:
    print(e.errors()[0]["msg"])
```

```text
unit_price=99.9 qty=3 discount=0.1 total=269.73
Value error, 单笔订单金额 99990.0 超过 50000，需要走审批流
```

> 👉 **CEO-Perspektive**: Das ist die Standardschreibweise für **Auslösebedingungen von Freigabeprozessen**. In Ihrem PRD steht mit ziemlicher Sicherheit ein ähnlicher Satz:
>
> - „Übersteigt der Auftragswert 50.000 Yuan, ist die Freigabe durch den Abteilungsleiter erforderlich"
> - „Übersteigt die Summe der Spesenbelege das Restbudget, ist die Einreichung gesperrt"
> - „Liegt der Stückpreis nach Rabatt unter den Kosten, ist eine Sondergenehmigung des Direktors nötig"
>
> Diesen Regeln ist gemeinsam: **Gegenstand der Schwellenwertprüfung ist ein Rechenergebnis, nicht ein vom Nutzer ausgefülltes Feld.** Der Nutzer trägt Stückpreis, Menge und Rabatt ein, das System errechnet die Summe und lässt diese Summe gegen den Schwellenwert laufen. Deshalb muss `model_validator(mode="after")` verwendet werden – erst an dieser Stelle stehen alle ursprünglichen Felder bereit.
>
> Nebenbei bemerkt: Der Fehlertext enthält den konkreten Betrag `99990.0` und den Schwellenwert `50000`. **Ein guter Fehlerhinweis sagt dem Nutzer, „um wie viel" er danebenliegt, und nicht bloß „geht nicht".** Dieses Detail sollte im PRD ausdrücklich gefordert werden.

### 5.7 model_validator(mode="before"): die Rohstruktur umbauen

**Welches Problem er löst**: Die vom Vorsystem gelieferte Datenstruktur unterscheidet sich von der gewünschten und muss zuerst „übersetzt" werden.

```python
from typing import Any


class Legacy(BaseModel):
    user_id: int
    user_name: str

    @model_validator(mode="before")
    @classmethod
    def flatten(cls, data: Any) -> Any:
        # Altsystem liefert {"user": {"id":..., "name":...}}, neues System liefert flach
        if isinstance(data, dict) and "user" in data:
            u = data.pop("user")
            data["user_id"] = u["id"]
            data["user_name"] = u["name"]
        return data


print(Legacy.model_validate({"user": {"id": 7, "name": "老系统"}}))
print(Legacy.model_validate({"user_id": 8, "user_name": "新系统"}))
```

```text
user_id=7 user_name='老系统'
user_id=8 user_name='新系统'
```

> ⚠️ **Fallstrick**: Das `data`, das ein model_validator mit `mode="before"` bekommt, **ist nicht garantiert ein dict** – es kann auch ein Objekt oder sonst irgendetwas sein. Deshalb steht in der ersten Zeile fast immer `if isinstance(data, dict)`. Das ist auch der Grund für die offizielle Empfehlung: „Wenn after reicht, verwenden Sie nicht before."

> 👉 **CEO-Perspektive**: Das ist die **Schnittstellen-Adapterschicht bzw. Anti-Corruption-Layer**. Wenn Sie ein Altsystem oder einen Drittkanal anbinden, dessen Feldstruktur Sie nicht ändern können, und diese unschöne Struktur nicht Ihren eigenen Geschäftscode verseuchen soll – dann übersetzen Sie sie einmalig am Eingang.
>
> Die zugehörige Produktentscheidung lautet: **Soll es überhaupt eine Kompatibilitätslogik geben, und wie lange?** Das Beispiel oben unterstützt beide Formate gleichzeitig, das heißt, alte Clients müssen nicht aktualisiert werden. Wann dieser Kompatibilitätscode entfernt wird, ist eine Produktentscheidung (abhängig vom Anteil der Nutzer alter Versionen), keine technische.

### 5.8 Ausführungsreihenfolge: wer kommt zuerst

```python
class Order2(BaseModel):
    a: int

    @model_validator(mode="before")
    @classmethod
    def m_before(cls, d): print("  1. model before"); return d

    @field_validator("a", mode="before")
    @classmethod
    def f_before(cls, v): print("  2. field before"); return v

    @field_validator("a", mode="after")
    @classmethod
    def f_after(cls, v): print("  3. field after"); return v

    @model_validator(mode="after")
    def m_after(self): print("  4. model after"); return self


Order2(a=1)
```

```text
  1. model before
  2. field before
  3. field after
  4. model after
```

Die vollständige Fließstrecke:

```text
原始输入
   │
   ├─▶ ① model_validator(before)   整体结构改造
   │
   ├─▶ ② field_validator(before)   单字段清洗
   │
   ├─▶    [Pydantic 类型转换 + Field 内置约束]
   │
   ├─▶ ③ field_validator(after)    单字段业务规则
   │
   └─▶ ④ model_validator(after)    跨字段规则 / 先算再判
          │
          ▼
      合法的模型对象
```

> 👉 **CEO-Perspektive**: Diese Fließstrecke lässt sich unmittelbar auf die **Prüfkette einer Formulareinreichung** abbilden: Vorverarbeitung des gesamten Vorgangs → Bereinigung jeder Position → Formatprüfung jeder Position → Geschäftsprüfung jeder Position → kombinierte Prüfung des gesamten Vorgangs. Wenn Sie im PRD Validierungsregeln beschreiben und sie in dieser Reihenfolge anordnen, können die Entwickler sie praktisch eins zu eins umsetzen.

### 5.9 Noch einmal betont: Validatoren laufen bei Zuweisungen standardmäßig nicht

```python
c = Coupon(code="CP1")
c.code = "XX"          # verstößt gegen „muss mit CP beginnen", aber kein Fehler
print("默认赋值不校验:", c.code)
```

```text
默认赋值不校验: XX
```

```python
class Coupon2(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    code: str

    @field_validator("code")
    @classmethod
    def chk(cls, v: str) -> str:
        if not v.startswith("CP"):
            raise ValueError("必须 CP 开头")
        return v


c2 = Coupon2(code="CP1")
try:
    c2.code = "XX"
except ValidationError as e:
    print("开了 validate_assignment:", e.errors()[0]["msg"])
```

```text
开了 validate_assignment: Value error, 必须 CP 开头
```

---
## 6. Serialisierung: Objekte wieder in Daten zurückverwandeln

Validierung ist der Weg „hinein", Serialisierung der Weg „hinaus".

### 6.0 Gesamtübersicht der Serialisierungsmöglichkeiten

| Methode/Dekorator | Wirkung | Ergebnis |
|---|---|---|
| `model_dump()` | wandelt in ein Python-Dictionary um | `dict` (die Werte bleiben Python-Objekte) |
| `model_dump(mode="json")` | wandelt in ein Dictionary um, das sich unmittelbar in JSON überführen lässt | `dict` (alle Werte sind JSON-native Typen) |
| `model_dump_json()` | wandelt direkt in einen JSON-String um | `str` |
| `include` / `exclude` | Felder auswählen / Felder ausschließen | — |
| `exclude_none/unset/defaults` | bedingtes Ausschließen | — |
| `Field(exclude=True)` | dieses Feld wird nie exportiert | — |
| `@computed_field` | fügt ein „berechnetes" Exportfeld hinzu | — |
| `@field_serializer` | passt das Exportformat eines bestimmten Feldes an | — |

### 6.1 model_dump vs model_dump_json

**Welches Problem löst das**: Bevor ein Objekt an nachgelagerte Systeme übergeben wird (Speichern in der Datenbank / Rückgabe ans Frontend / Weitergabe an Dritte), muss es wieder in gewöhnliche Daten zurückverwandelt werden.

```python
from decimal import Decimal
from datetime import datetime


class Item(BaseModel):
    name: str
    price: Decimal
    created: datetime


i = Item(name="鼠标", price="99.50", created="2024-05-01T12:00:00")
print("python 模式:", i.model_dump())
print("json   模式:", i.model_dump(mode="json"))
print("json 字符串:", i.model_dump_json())
print(i.model_dump_json(indent=2))
```

```text
python 模式: {'name': '鼠标', 'price': Decimal('99.50'), 'created': datetime.datetime(2024, 5, 1, 12, 0)}
json   模式: {'name': '鼠标', 'price': '99.50', 'created': '2024-05-01T12:00:00'}
json 字符串: {"name":"鼠标","price":"99.50","created":"2024-05-01T12:00:00"}
{
  "name": "鼠标",
  "price": "99.50",
  "created": "2024-05-01T12:00:00"
}
```

**Den entscheidenden Unterschied** sehen Sie an der Spalte `created`:
- `model_dump()` liefert ein Python-`datetime`-Objekt – geeignet für die Weiterverarbeitung innerhalb von Python;
- `model_dump(mode="json")` liefert den String `"2024-05-01T12:00:00"` – geeignet, um ihn direkt an `json.dumps` oder ans Frontend zu übergeben.

> ⚠️ **Fallstrick**: Das Ergebnis von `model_dump()` unmittelbar an `json.dumps()` weiterzureichen, führt zu einem Fehler, denn `datetime` und `Decimal` sind keine JSON-nativen Typen. Verwenden Sie entweder `mode="json"` oder gleich `model_dump_json()`.

> 👉 **CEO-Perspektive**: Diese beiden Methoden entsprechen im Produkt dem Unterschied zwischen „**Export in das interne Format**" und „**Export in das Austauschformat**". Ganz wie in Excel „Speichern unter .xlsx" (behält Formatierung und Formeln vollständig) gegenüber „Speichern unter .csv" (jeder kann es öffnen, aber die Formatinformationen sind verloren).
>
> Beachten Sie nebenbei, dass `Decimal("99.50")` in JSON zu einem **String `"99.50"`** wird und nicht zu einer Zahl. Das ist Absicht – der Zahlentyp von JSON kennt keine exakten Dezimalzahlen, eine Umwandlung in eine Zahl würde Genauigkeit kosten. Wenn in Ihrer Schnittstellendokumentation steht „Betragsfelder sind vom Typ Zahl", kollidiert das mit diesem Standardverhalten. **Ob Beträge als String oder als Zahl übertragen werden, muss beim Schnittstellenentwurf zwingend geklärt werden** – und die dringende Empfehlung lautet: als String.

### 6.2 Felder auswählen: die Familie include / exclude

**Welches Problem löst das**: Dasselbe Objekt soll unterschiedlichen Rollen unterschiedliche Felder zeigen.

```python
class User(BaseModel):
    id: int
    name: str
    password: str
    email: str | None = None


u = User(id=1, name="tom", password="s3cret")
print(u.model_dump())
print(u.model_dump(exclude={"password"}))
print(u.model_dump(include={"id", "name"}))
print(u.model_dump(exclude_none=True))
print(u.model_dump(exclude_defaults=True))
print(u.model_dump(exclude_unset=True))
```

```text
{'id': 1, 'name': 'tom', 'password': 's3cret', 'email': None}
{'id': 1, 'name': 'tom', 'email': None}
{'id': 1, 'name': 'tom'}
{'id': 1, 'name': 'tom', 'password': 's3cret'}
{'id': 1, 'name': 'tom', 'password': 's3cret'}
{'id': 1, 'name': 'tom', 'password': 's3cret'}
```

| Parameter | Bedeutung |
|---|---|
| `include={...}` | nur diese Felder (Whitelist) |
| `exclude={...}` | alle außer diesen Feldern (Blacklist) |
| `exclude_none=True` | Felder mit dem Wert None werden nicht exportiert |
| `exclude_unset=True` | Felder, die der Nutzer nicht ausdrücklich übergeben hat, werden nicht exportiert |
| `exclude_defaults=True` | Felder, deren Wert dem Standardwert entspricht, werden nicht exportiert |

Wenn ein Feld **niemals exportiert werden darf**, schreiben Sie das direkt in die Felddefinition:

```python
class User2(BaseModel):
    id: int
    password: str = Field(exclude=True)


print(User2(id=1, password="x").model_dump())
```

```text
{'id': 1}
```

> 👉 **CEO-Perspektive**: Diese Parametergruppe entspricht unmittelbar zwei sehr häufigen Produktanforderungen:
>
> **1. Feldgenaue Berechtigungen / Datenmaskierung**. Beim selben Nutzerobjekt sehen normale Nutzer Spitzname und Profilbild, der Kundenservice sieht die Mobilnummer, und nur das Risikomanagement sieht die Ausweisnummer. `include`/`exclude` sind die Umsetzung genau dieser „Feld-Sichtbarkeitsmatrix". `Field(exclude=True)` bedeutet dagegen „für niemanden und in keinem Szenario einsehbar" – Passwörter und Schlüssel gehören in diese Kategorie, und es in der Felddefinition festzuschreiben ist erheblich sicherer, als bei jedem Aufruf daran denken zu müssen, sie auszuschließen.
>
> **2. PATCH-Semantik**. `exclude_unset=True` sorgt dafür, dass nur die Felder exportiert werden, die der Nutzer tatsächlich geändert hat. Genau so sollte sich eine Schnittstelle für „Teilaktualisierungen" verhalten: Hat der Nutzer nur den Spitznamen geändert, wird auch nur der Spitzname gesendet und nicht das gesamte Objekt zum Überschreiben (sonst würden Felder überschrieben, die ein anderer Client gerade erst geändert hat). **Ob die Seite „Profil bearbeiten" vollständig überschreiben oder teilweise aktualisieren soll, ist eine Produktentscheidung** – und `exclude_unset` ist die Umsetzung auf der Seite der Teilaktualisierung.

### 6.3 computed_field: die Formelspalte aus Excel

**Welches Problem löst das**: Manche Felder sollten Nutzer gar nicht ausfüllen, sondern das System sollte sie aus anderen Feldern berechnen – sie müssen aber trotzdem im Exportergebnis erscheinen.

```python
from pydantic import computed_field


class Cart(BaseModel):
    unit_price: float
    qty: int

    @computed_field
    @property
    def subtotal(self) -> float:
        return round(self.unit_price * self.qty, 2)

    @computed_field(description="是否满足包邮门槛")
    @property
    def free_shipping(self) -> bool:
        return self.subtotal >= 99


c = Cart(unit_price=33.3, qty=3)
print(c.model_dump())
print(c.model_dump_json())
print("字段列表:", list(Cart.model_fields), "| 计算字段:", list(Cart.model_computed_fields))
```

```text
{'unit_price': 33.3, 'qty': 3, 'subtotal': 99.9, 'free_shipping': True}
{"unit_price":33.3,"qty":3,"subtotal":99.9,"free_shipping":true}
字段列表: ['unit_price', 'qty'] | 计算字段: ['subtotal', 'free_shipping']
```

Drei Punkte sind zu beachten:
1. Nutzer **müssen und können** `subtotal` **nicht ausfüllen**; es steht nicht in `model_fields`;
2. es **erscheint aber im Exportergebnis**, das Frontend kann es also direkt abgreifen;
3. ein berechnetes Feld darf auf ein anderes berechnetes Feld zurückgreifen (`free_shipping` nutzt `subtotal`).

**Der Unterschied zwischen `computed_field` und dem „erst rechnen, dann prüfen" aus Abschnitt 5.6**:

| | `computed_field` | Zuweisung im `model_validator` |
|---|---|---|
| Muss das Feld deklariert werden? | nein | ja (`total: float = 0`) |
| Wann wird gerechnet? | bei jedem Zugriff neu | einmal bei der Erzeugung, danach gespeichert |
| Kann es an der Validierung teilnehmen? | ❌ das Ergebnis wird direkt verwendet | ✅ kann geprüft werden und Fehler auslösen |
| Geeignet für | rein darstellende abgeleitete Werte | Zwischenwerte, auf denen Prüfungen aufbauen |

> 👉 **CEO-Perspektive**: `computed_field` **ist die Formelspalte aus Excel**, exakt dasselbe Konzept. Zwischensumme = Einzelpreis × Menge, Versandkostenfreiheit = Zwischensumme ≥ 99, Mitgliedsstufe = Zuordnung über Punkteintervalle, Kontoalter = heute − Registrierungsdatum.
>
> Im PRD zwischen „**vom Nutzer ausgefüllten Feldern**" und „**vom System berechneten Feldern**" zu unterscheiden, ist eine ausgesprochen wertvolle Gewohnheit, denn davon hängen gleich drei Dinge ab: ob das Eingabefeld im Formular überhaupt angezeigt wird, ob es in der Schnittstellendokumentation ein Eingabeparameter ist, und ob diese Spalte in der Datenbank gespeichert werden muss. Wirft man beides in eine Tabelle, muss das Engineering raten.
>
> Empfehlenswert ist eine zusätzliche Spalte „Herkunft" in der Feldtabelle des PRD, mit den Werten: vom Nutzer ausgefüllt / vom System berechnet / vom Vorsystem geliefert.

### 6.4 field_serializer: das Exportformat anpassen

**Welches Problem löst das**: Das intern gespeicherte Format unterscheidet sich von dem Format, in dem nach außen dargestellt wird.

```python
from pydantic import field_serializer
from datetime import date


class Report(BaseModel):
    day: date
    amount: Decimal

    @field_serializer("day")
    def ser_day(self, v: date) -> str:
        return v.strftime("%Y年%m月%d日")

    @field_serializer("amount")
    def ser_amount(self, v: Decimal) -> str:
        return f"¥{v:,.2f}"


print(Report(day="2024-06-01", amount="12345.6").model_dump())
```

```text
{'day': '2024年06月01日', 'amount': '¥12,345.60'}
```

> ⚠️ **Fallstrick**: Seien Sie zurückhaltend damit, „Darstellungsformatierung" in den Serializer zu verlagern. Sobald Sie das tun, **lassen sich diese Daten vom selben Modell nicht mehr einlesen** (`"2024年06月01日"` ist keine gültige Datumseingabe). Darstellungsformatierung gehört in der Regel besser ins Frontend. Hierher gehört eher das, was „ein externes Protokoll vorschreibt", etwa wenn ein Drittanbieter Datumsangaben zwingend als `YYYYMMDD` verlangt.

> 👉 **CEO-Perspektive**: Das entspricht dem Prinzip „**dieselben Daten, unterschiedliche Darstellungskonventionen**". Der Finanzbericht braucht `¥12,345.60`, die Datenanalyse braucht `12345.6`, die Schnittstelle eines Drittanbieters braucht `1234560` (in Cent). Wer diese Umwandlung vornimmt, ist eine Architekturentscheidung: das Backend (einheitlich, aber unflexibel) oder das Frontend (flexibel, aber jeder Client muss es einzeln umsetzen, mit hoher Gefahr von Abweichungen). **Bei Produkten mit mehreren Clients empfiehlt sich das Backend**, bei einem reinen Web-Produkt ist das Frontend flexibler.

### 6.5 Der klassische große Fallstrick: Serialisierung nach dem „deklarierten Typ"

**Welches Problem löst das**: Dies ist das Verhalten, über das man bei Pydantic am leichtesten stolpert – Sie müssen es kennen.

```python
class Base(BaseModel):
    base_field: int


class Sub(Base):                 # Vererbung, ein Feld mehr
    sub_field: str


class Main(BaseModel):
    model: Base                  # als Base deklariert


m = Main(model=Sub(base_field=1, sub_field="会不见"))
print("m.model 实际是:", type(m.model).__name__)
print("dump 结果      :", m.model_dump())
```

```text
m.model 实际是: Sub
dump 结果      : {'model': {'base_field': 1}}
```

**`sub_field` ist verschwunden.** Die Daten sind nicht verloren (`m.model` ist tatsächlich ein `Sub`-Objekt), aber beim Export wurde gemäß der Definition von `Base` nur `base_field` ausgegeben.

Der Grund: Pydantic **serialisiert nach dem von Ihnen deklarierten Typ, nicht nach dem tatsächlichen Laufzeittyp**. Sie haben gesagt, diese Spalte sei `Base` – also werden nur die Felder exportiert, die `Base` besitzt.

**Lösung 1 (empfohlen): eine diskriminierte Union verwenden** (ausführlich in Kapitel 8)

```python
class SubA(BaseModel):
    type: Literal["a"] = "a"
    base_field: int
    sub_field: str


class MainOK(BaseModel):
    model: SubA


print(MainOK(model=SubA(base_field=1, sub_field="在的")).model_dump())
```

```text
{'model': {'type': 'a', 'base_field': 1, 'sub_field': '在的'}}
```

**Lösung 2 (Notbehelf): `serialize_as_any=True`**

```python
print(m.model_dump(serialize_as_any=True))
```

```text
{'model': {'base_field': 1, 'sub_field': '会不见'}}
```

> ⚠️ **Fallstrick**: Dies ist ein **stiller Fehlschlag** – keine Fehlermeldung, keine Warnung, das Feld ist schlicht weg. Im Produktivbetrieb äußert sich das als „bei bestimmten Bestellungen kommen bestimmte Felder im Frontend nicht an", und die Ursachensuche ist ausgesprochen mühsam. Überall dort, wo ein Modell Vererbung mit einer Deklaration auf den Elterntyp kombiniert, müssen Sie diesen Punkt prüfen.

> 👉 **CEO-Perspektive**: In die Produktsprache übersetzt: **„Ihre Formularvorlage deklariert für dieses Feld ‚allgemeiner Anhang'. Selbst wenn der Nutzer tatsächlich eine ‚Gewerbeerlaubnis des Unternehmens' hochlädt, werden bei der Archivierung nur die allgemeinen Angaben des ‚allgemeinen Anhangs' erfasst, und die für die Gewerbeerlaubnis spezifischen Informationen gehen verloren."**
>
> Das Produktszenario hinter diesem Fallstrick ist ausgesprochen typisch: ein allgemeines „Nachrichten"-Objekt mit den drei Untertypen „SMS/E-Mail/Push", die jeweils eigene Felder besitzen. Modelliert man diese Beziehung über „Vererbung", tappt man genau in diese Falle. **Richtig modelliert man das als „Union mit Typkennzeichen" (Kapitel 8)** – und das ist zugleich genau der Gedanke, der Ihnen beim Entwerfen von Formularabhängigkeiten im PRD ohnehin am natürlichsten kommt: erst den Typ wählen, dann die zugehörigen Felder anzeigen.

### 6.6 Unbekannte Felder werden standardmäßig stillschweigend verworfen

```python
class Strict(BaseModel):
    a: int


print(Strict.model_validate({"a": 1, "b": 2}).model_dump())
```

```text
{'a': 1}
```

Das zusätzlich übergebene `b` wurde stillschweigend ignoriert. Wer stattdessen eine Fehlermeldung möchte, muss `extra="forbid"` aktivieren (siehe 10.1).

> 👉 **CEO-Perspektive**: Das standardmäßige „Ignorieren" ist großzügig; der Vorteil ist, dass ein neues Feld im Vorsystem Ihnen nicht den Betrieb lahmlegt. Der Nachteil: **Wenn das Vorsystem einen Feldnamen falsch schreibt, bemerken Sie es nicht** – aus `phoneNumber` wird `phonNumber`, und die Daten sind klammheimlich verschwunden. Für interne Schnittstellen empfiehlt sich `extra="forbid"` (strikte Abstimmung), für externe Schnittstellen und die von Drittanbietern besser der Standard (Fehlertoleranz).

---
## 7. JSON Schema: Aus Ihrer gezeichneten Tabelle wird eine Spezifikation ★

**Dies ist das Scharnierkapitel des gesamten Buches – nehmen Sie sich dafür Zeit.**

In allen bisherigen Kapiteln ging es darum, „wie man eine Tabelle definiert". In diesem Kapitel geht es darum: **Diese Tabelle lässt sich automatisch in eine Spezifikation übersetzen, die eine Maschine lesen kann.**

Und genau diese Spezifikation ist der zugrunde liegende Mechanismus, mit dem Pydantic AI später das LLM dazu bringt, „formatgerecht auszugeben".

### 7.1 Kernkonzept: Tabelle → Spezifikation

**Welches Problem es löst**: Aus den „Feldregeln im Code" wird eine „standardisierte Formatbeschreibung, die jedes System lesen kann".

```text
   ┌──────────────────────────┐                    ┌────────────────────────────┐
   │   你写的 Pydantic 模型     │                    │      JSON Schema           │
   │   （表 / 数据契约）        │  ──────────────▶   │      （说明书）             │
   │                          │  model_json_schema │                            │
   │  class User(BaseModel):  │                    │  {                         │
   │      name: str           │                    │    "type": "object",       │
   │      age: int            │                    │    "properties": {...},    │
   │                          │                    │    "required": [...]       │
   └──────────────────────────┘                    │  }                         │
                                                   └────────────┬───────────────┘
                                                                │
                          ┌─────────────────────────────────────┼──────────────────────────┐
                          ▼                                     ▼                          ▼
                ┌──────────────────┐              ┌──────────────────────┐    ┌──────────────────────┐
                │  API 文档         │              │  前端表单自动生成      │    │  大模型结构化输出 ★   │
                │  (OpenAPI/Swagger)│              │  (低代码 / 表单引擎)  │    │  (Pydantic AI)       │
                └──────────────────┘              └──────────────────────┘    └──────────────────────┘
```

Minimalbeispiel:

```python
import json
from pydantic import BaseModel


class User(BaseModel):
    name: str
    age: int


print(json.dumps(User.model_json_schema(), indent=2, ensure_ascii=False))
```

```json
{
  "properties": {
    "name": {
      "title": "Name",
      "type": "string"
    },
    "age": {
      "title": "Age",
      "type": "integer"
    }
  },
  "required": [
    "name",
    "age"
  ],
  "title": "User",
  "type": "object"
}
```

Diese Spezifikation Block für Block gelesen:

| Schlüssel im Schema | Bedeutung | Entsprechung im PRD |
|---|---|---|
| `"type": "object"` | Dies ist eine Tabelle (kein Einzelwert) | „Formular" / „Objekt" |
| `"title": "User"` | Wie diese Tabelle heißt | Tabellenname |
| `"properties"` | Welche Spalten es gibt | Feldliste |
| `"required"` | Welche Spalten Pflicht sind | Die Spalte mit der Pflicht-Markierung |
| Das `"type"` jedes Feldes | Welcher Typ in dieser Spalte einzutragen ist | Die Spalte „Typ" |
| Das `"title"` jedes Feldes | Der Anzeigename dieser Spalte (automatisch aus dem Feldnamen erzeugt) | Der Klartextname des Feldes |

Beachten Sie: `title` erzeugt Pydantic **automatisch** aus dem Feldnamen: `user_name` → `"User Name"`.

> 👉 **CEO-Perspektive**: Dieser Schritt ist der wichtigste gedankliche Umbruch des ganzen Buches.
>
> **Die Feldregel-Tabelle, die Sie im PRD gezeichnet haben, liefert Ihnen – sobald die Entwicklung sie einmal in Pydantic geschrieben hat – „gratis" eine standardisierte, maschinenlesbare Spezifikation.** Und diese Spezifikation lässt sich direkt weiterreichen: an Swagger zur Erzeugung der Schnittstellendokumentation, an die Formular-Engine im Frontend zum automatischen Rendern von Formularen – und an das LLM.
>
> Das bedeutet: Die „Feldtabelle im PRD" ist nicht länger ein Word-Dokument, das schon veraltet ist, sobald es fertig geschrieben wurde, sondern die **einzige Quelle der Wahrheit (single source of truth)**: Sie ändern das Modell im Code, und Dokumentation, Formulare und KI-Prompts ziehen automatisch nach. Das ist eine sehr konkrete Verbesserung, die Sie in Ihrem Team anstoßen können.

### 7.2 Wie description in das Schema gelangt

**Welches Problem es löst**: Auch die „fachliche Bedeutung eines Feldes" soll in die Spezifikation einfließen, nicht nur der Typ.

```python
from typing import Literal
from pydantic import Field, ConfigDict


class Feedback(BaseModel):
    """用户反馈工单。"""
    model_config = ConfigDict(title="用户反馈")

    title: str = Field(description="一句话概括反馈内容", max_length=50)
    sentiment: Literal["正面", "中性", "负面"] = Field(description="整体情绪倾向")
    score: int = Field(ge=1, le=5, description="满意度打分，1 最差 5 最好")
    tags: list[str] = Field(default_factory=list, description="问题标签，最多 3 个", max_length=3)
    need_followup: bool = Field(default=False, description="是否需要人工跟进")


print(json.dumps(Feedback.model_json_schema(), indent=2, ensure_ascii=False))
```

```json
{
  "description": "用户反馈工单。",
  "properties": {
    "title": {
      "description": "一句话概括反馈内容",
      "maxLength": 50,
      "title": "Title",
      "type": "string"
    },
    "sentiment": {
      "description": "整体情绪倾向",
      "enum": [
        "正面",
        "中性",
        "负面"
      ],
      "title": "Sentiment",
      "type": "string"
    },
    "score": {
      "description": "满意度打分，1 最差 5 最好",
      "maximum": 5,
      "minimum": 1,
      "title": "Score",
      "type": "integer"
    },
    "tags": {
      "description": "问题标签，最多 3 个",
      "items": {
        "type": "string"
      },
      "maxItems": 3,
      "title": "Tags",
      "type": "array"
    },
    "need_followup": {
      "default": false,
      "description": "是否需要人工跟进",
      "title": "Need Followup",
      "type": "boolean"
    }
  },
  "required": [
    "title",
    "sentiment",
    "score"
  ],
  "title": "用户反馈",
  "type": "object"
}
```

**Drei Informationsquellen**:

| Stelle im Schema | Woher sie stammt |
|---|---|
| `"description"` auf oberster Ebene | Der **Docstring** der Klasse (`"""用户反馈工单。"""`) |
| `"title"` auf oberster Ebene | `model_config = ConfigDict(title="用户反馈")`; ohne diese Angabe wird der Klassenname verwendet |
| Das `"description"` eines Feldes | `Field(description=...)` |

**Wie `required` zustande kommt**: `title`/`sentiment`/`score` haben keinen Standardwert → Pflicht; `tags` hat ein `default_factory`, `need_followup` hat `default=False` → nicht Pflicht, und der Standardwert `false` wandert ebenfalls mit ins Schema.

> 👉 **CEO-Perspektive**: **Schauen Sie sich diese Ausgabe zweimal an – denn genau das ist es, was das LLM später „sehen" wird.**
>
> Sieht das Modell `"description": "满意度打分，1 最差 5 最好"` zusammen mit `"minimum": 1, "maximum": 5`, dann weiß es, dass es eine ganze Zahl zwischen 1 und 5 eintragen soll – und dass 1 die schlechteste Bewertung ist. Stünde in Ihrer description nur das Wort „Bewertung", wüsste das Modell weder, ob eine 5er- oder eine 100er-Skala gemeint ist, noch ob ein hoher Wert gut oder schlecht bedeutet.
>
> Anders gesagt: **`description` ist der Prompt, den der CEO schreibt – nur dass er direkt neben dem Feld steht.** Das ist der Hebel mit der größten Wirkung, den ein CEO in KI-Projekten hat, und zugleich derjenige, der am häufigsten übersehen wird.

### 7.3 Wie Beschränkungen im Schema ausgedrückt werden

**Welches Problem es löst**: Klarheit darüber, wie die Beschränkungen aus Python auf das Standardvokabular von JSON Schema abgebildet werden (die Namen unterscheiden sich).

| Schreibweise in Pydantic | Wird im JSON Schema zu | Erläuterung |
|---|---|---|
| `Field(gt=0)` | `"exclusiveMinimum": 0` | Echt größer als |
| `Field(ge=1)` | `"minimum": 1` | Größer oder gleich |
| `Field(lt=100)` | `"exclusiveMaximum": 100` | Echt kleiner als |
| `Field(le=5)` | `"maximum": 5` | Kleiner oder gleich |
| `Field(min_length=6)` (String) | `"minLength": 6` | |
| `Field(max_length=50)` (String) | `"maxLength": 50` | |
| `Field(min_length=1)` (Liste) | `"minItems": 1` | Derselbe Parameter wird bei Listen zu items |
| `Field(max_length=20)` (Liste) | `"maxItems": 20` | |
| `Field(pattern=r"^1\d{10}$")` | `"pattern": "^1\\d{10}$"` | Der reguläre Ausdruck wird unverändert übernommen |
| `Literal["A","B"]` | `"enum": ["A","B"]` | Liste der Auswahlmöglichkeiten |
| `str` | `"type": "string"` | |
| `int` | `"type": "integer"` | |
| `float` | `"type": "number"` | |
| `bool` | `"type": "boolean"` | |
| `list[X]` | `"type": "array", "items": {...}` | |
| `dict[str,X]` | `"type": "object"` | |
| `X \| None` | `"anyOf": [{...}, {"type":"null"}]` | „Nullbar" wird als „oder eben null" ausgedrückt |
| `date` | `"type": "string", "format": "date"` | |
| `datetime` | `"type": "string", "format": "date-time"` | |
| `ConfigDict(extra="forbid")` | `"additionalProperties": false` | Zusätzliche Angaben sind nicht erlaubt |
| `@computed_field` | `"readOnly": true` | Nur-Lese-Spalte. **Erscheint ausschließlich bei `mode="serialization"`**; im standardmäßigen Validierungsmodus landen berechnete Felder gar nicht erst im Schema |

So sieht ein nullbares Feld aus (aus der tatsächlichen Ausgabe von 7.9):

```json
"remark": {
  "anyOf": [
    { "maxLength": 200, "type": "string" },
    { "type": "null" }
  ],
  "default": null,
  "title": "Remark"
}
```

> 👉 **CEO-Perspektive**: Der Wert dieser Gegenüberstellung liegt darin – **wenn in der Schnittstellendokumentation (Swagger), die Ihnen die Entwicklung vorlegt, `exclusiveMinimum: 0` steht, müssen Sie sofort erkennen: „Der Preis muss größer als 0 sein, 0 Euro geht nicht."** Und umgekehrt: Wenn Sie im PRD „Preis > 0" schreiben, wissen Sie auch, dass daraus am Ende genau diese Zeile wird. Das ist eine der wenigen Stellen, an denen sich Produkt und Entwicklung wörtlich aufeinander abstimmen können.
>
> Achten Sie besonders auf die Umbenennung `gt` → `exclusiveMinimum`. Zwischen `minimum` und `exclusiveMinimum` liegt nur ein Wort, fachlich aber ein ganzer Grenzwert – und Grenzwerte sind die Stelle, an der in Testfällen am häufigsten Fehler auftreten.

### 7.4 Verschachtelte Modelle: Was $defs und $ref sind

**Welches Problem es löst**: Wenn eine Tabelle eine andere Tabelle referenziert – wie schreibt man die Spezifikation, ohne sich zu wiederholen?

```python
class Address(BaseModel):
    city: str
    zipcode: str = Field(pattern=r"^\d{6}$")


class Person(BaseModel):
    name: str
    home: Address
    others: list[Address] = []


print(json.dumps(Person.model_json_schema(), indent=2, ensure_ascii=False))
```

```json
{
  "$defs": {
    "Address": {
      "properties": {
        "city": {
          "title": "City",
          "type": "string"
        },
        "zipcode": {
          "pattern": "^\\d{6}$",
          "title": "Zipcode",
          "type": "string"
        }
      },
      "required": [
        "city",
        "zipcode"
      ],
      "title": "Address",
      "type": "object"
    }
  },
  "properties": {
    "name": {
      "title": "Name",
      "type": "string"
    },
    "home": {
      "$ref": "#/$defs/Address"
    },
    "others": {
      "default": [],
      "items": {
        "$ref": "#/$defs/Address"
      },
      "title": "Others",
      "type": "array"
    }
  },
  "required": [
    "name",
    "home"
  ],
  "title": "Person",
  "type": "object"
}
```

**`$defs` und `$ref` gehören zusammen**:

```text
  ┌────────────────────────────────────────────────┐
  │  "$defs": {          ← 「附录：子表定义区」      │
  │      "Address": { ...完整的 Address 表定义... } │
  │  }                                             │
  │                                                │
  │  "properties": {                               │
  │      "home":   { "$ref": "#/$defs/Address" }   │  ← 「详见附录 Address」
  │      "others": { "type": "array",              │
  │                  "items": {                    │
  │                     "$ref": "#/$defs/Address"  │  ← 「每一项详见附录 Address」
  │                  } }                           │
  │  }                                             │
  └────────────────────────────────────────────────┘
```

- **`$defs`** = der **„Anhang" bzw. der Definitionsbereich für Untertabellen** am Ende der Spezifikation; jedes referenzierte Untermodell wird hier genau einmal vollständig definiert;
- **`$ref`** = der Verweis „**siehe Anhang X**" im Fließtext; `#/$defs/Address` liest sich als „dieses Dokument → Abschnitt $defs → Eintrag Address".

**Warum dieser Umweg?** Weil `Address` zweimal referenziert wird (je einmal in `home` und in `others`). Ohne Referenz müsste dieselbe Definition zweimal abgeschrieben werden; sobald eine Tabellenstruktur etwas tiefer wird, bläht sich die Spezifikation explosionsartig auf. Und selbstreferenzierende Baumstrukturen (das `Category` aus Abschnitt 4.6) **lassen sich überhaupt nicht ausschreiben** – sie sind unendlich tief und nur über Referenzen ausdrückbar.

> 👉 **CEO-Perspektive**: `$defs` + `$ref` ist genau der Kniff, den Sie beim Schreiben eines langen PRD verwenden – **wiederkehrende Definitionen in den Anhang auslagern und im Fließtext „Felddefinition siehe Anhang 3.2" schreiben**. Die Struktur „Lieferadresse" taucht auf der Bestellseite, im Adressbuch und im Retourenbeleg auf; Sie würden sie im PRD nicht dreimal abschreiben, sondern einmal definieren und überall darauf verweisen. JSON Schema macht es exakt genauso.
>
> Praktischer Hinweis: **Manche LLM-Schnittstellen für strukturierte Ausgabe unterstützen `$ref` nur eingeschränkt** (besonders bei tiefer Verschachtelung oder zirkulären Referenzen). Halten Sie deshalb beim Entwurf von Ausgabestrukturen für KI **die Hierarchie flach** (in der Regel nicht mehr als 2–3 Ebenen). Das ist eine Entwurfsbeschränkung, bei der der CEO mitabwägen muss: Je feingliedriger die Struktur, desto höher die Wahrscheinlichkeit, dass das Modell falsch ausfüllt – und desto höher auch die Wahrscheinlichkeit von Schnittstellenfehlern.

### 7.5 Zwei Modi: validation und serialization

**Welches Problem wird gelöst**: Die Spezifikation für „hinein" und die für „hinaus" haben unterschiedliche Inhalte – berechnete Felder existieren nur beim Hinausgehen.

```python
from pydantic import computed_field


class C(BaseModel):
    a: int

    @computed_field
    @property
    def double(self) -> int:
        return self.a * 2


print("validation:", list(C.model_json_schema(mode="validation")["properties"]))
print("serialization:", list(C.model_json_schema(mode="serialization")["properties"]))
```

```text
validation: ['a']
serialization: ['a', 'double']
```

| Modus | Beschreibt | Wofür |
|---|---|---|
| `mode="validation"` (Standard) | wie die **Eingabeparameter der Schnittstelle** aussehen | Formulare fürs Frontend, Ausfüllvorlage fürs LLM ★ |
| `mode="serialization"` | wie die **Rückgabe der Schnittstelle** aussieht | API-Antwortdokumentation |

> 👉 **CEO-Perspektive**: Das entspricht exakt den beiden Tabellen „**Anfrageparameter**" und „**Antwortfelder**" in einer Schnittstellendokumentation. Berechnete Felder (Zwischensumme, versandkostenfrei ja/nein) tauchen nur in der Antwort auf, nicht in der Anfrage – denn der Nutzer soll sie gar nicht ausfüllen.
>
> Wenn ein LLM das Formular ausfüllt, wird der **validation-Modus** verwendet; das Modell wird also nie aufgefordert, ein berechnetes Feld auszufüllen. Dieses Design ist klug durchdacht: Was das Modell ermitteln soll, definieren Sie als normales Feld; was das Modell nicht ermitteln soll, weil Sie es selbst exakt berechnen, definieren Sie als `computed_field`. **Das ist eine Schlüsselentscheidung, die der CEO treffen kann**: Welche Zahlen überlässt man dem Urteil der KI, und welche muss das System exakt berechnen? (Bei allem, was mit Geld zu tun hat, immer Letzteres.)

### 7.6 Auswirkungen von alias auf die Spezifikation

```python
class Al(BaseModel):
    user_name: str = Field(alias="userName")


print("by_alias=True (默认):", list(Al.model_json_schema()["properties"]))
print("by_alias=False      :", list(Al.model_json_schema(by_alias=False)["properties"]))
```

```text
by_alias=True (默认): ['userName']
by_alias=False      : ['user_name']
```

Die standardmäßig erzeugte Spezifikation verwendet den **nach außen sichtbaren Namen** (Alias) – und das ist richtig so, denn die Spezifikation richtet sich an Externe.

### 7.7 json_schema_extra: eigene Inhalte in die Spezifikation einschleusen

```python
class P(BaseModel):
    sku: str = Field(description="商品编码", examples=["SKU-001", "SKU-002"],
                     json_schema_extra={"x-internal": True})
```

```json
{
  "sku": {
    "description": "商品编码",
    "examples": ["SKU-001", "SKU-002"],
    "title": "Sku",
    "type": "string",
    "x-internal": true
  }
}
```

> 👉 **CEO-Perspektive**: Eigene Schlüssel mit dem Präfix `x-` sind eine Konvention aus OpenAPI; dort legt man „Informationen außerhalb des Standards ab, die wir intern vereinbart haben". Zum Beispiel markiert `x-pii: true` ein personenbezogenes, sensibles Datum, und `x-since: "v2.3"` hält fest, ab welcher Version es dieses Feld gibt. **Daraus kann ein sehr praktischer Mechanismus für Datenverwaltung werden**: Felder verschlagworten, dann ein Skript schreiben, das alle Modelle durchsucht und automatisch eine „systemweite Liste aller personenbezogenen Felder" für die Rechtsabteilung erzeugt. Aus der Compliance-Prüfung „Code von Hand durchblättern" wird „ein Skript laufen lassen".

### 7.8 ★ Das ist der Mechanismus hinter der „formatgetreuen Ausgabe" von LLMs

**Welches Problem wird gelöst**: Das LLM soll nicht frei improvisieren, sondern brav die von Ihnen definierte Tabelle ausfüllen.

Der vollständige Ablauf:

```text
 ①  CEO 定义需求：「从用户反馈里提取：一句话摘要、情绪、打分、标签、是否需跟进」
                                  │
                                  ▼
 ②  工程师写成 Pydantic 模型（就是 7.2 的 Feedback 类）
                                  │
                                  ▼
 ③  Feedback.model_json_schema()  →  一份 949 字符的说明书
                                  │
                                  ▼
 ④  说明书 + 用户原始反馈文本  →  一起发给大模型
                                  │
                                  ▼
 ⑤  模型返回一段 JSON 文本
                                  │
                                  ▼
 ⑥  Feedback.model_validate_json(模型输出)
                                  │
                     ┌────────────┴────────────┐
                     ▼                         ▼
              校验通过 → 拿到对象         校验失败 → ValidationError
              直接 fb.score               把错误信息发回给模型，让它重填
```

Führen wir die Schritte ③⑤⑥ einmal wirklich aus:

```python
schema = Feedback.model_json_schema()
print("发给模型的 schema 大小:", len(json.dumps(schema)), "字符")

# Eine vom LLM zurückgegebene JSON-Antwort simulieren
fake_llm_output = '{"title":"App 启动很慢","sentiment":"负面","score":2,"tags":["性能"],"need_followup":true}'

fb = Feedback.model_validate_json(fake_llm_output)
print("解析回对象:", fb)
print("直接拿字段:", fb.score, fb.sentiment)
```

```text
发给模型的 schema 大小: 949 字符
解析回对象: title='App 启动很慢' sentiment='负面' score=2 tags=['性能'] need_followup=True
直接拿字段: 2 负面
```

**Was passiert, wenn die Modellausgabe nicht regelkonform ist**:

```python
bad = '{"title":"App 启动很慢","sentiment":"很生气","score":8,"tags":["a","b","c","d"]}'
try:
    Feedback.model_validate_json(bad)
except ValidationError as e:
    print(e)
```

```text
3 validation errors for 用户反馈
sentiment
  Input should be '正面', '中性' or '负面' [type=literal_error, input_value='很生气', input_type=str]
score
  Input should be less than or equal to 5 [type=less_than_equal, input_value=8, input_type=int]
tags
  List should have at most 3 items after validation, not 4 [type=too_long, input_value=['a', 'b', 'c', 'd'], input_type=list]
```

Das Modell hat sich an drei Stellen etwas eigenes ausgedacht: Als Stimmung schrieb es „很生气" (sehr verärgert), was gar nicht zur Auswahl steht; als Bewertung vergab es eine 8 und damit einen Wert außerhalb der Fünf-Punkte-Skala; und es lieferte 4 Tags und damit mehr als die Obergrenze. **Alle drei Stellen wurden abgefangen – und die Fehlermeldung selbst ist bereits eine „Korrekturanweisung", die man direkt an das Modell zurückschicken kann.**

> 👉 **CEO-Perspektive**: **Dieser Abschnitt ist der Dreh- und Angelpunkt des ganzen Buches, bitte verinnerlichen Sie ihn wirklich.**
>
> LLMs improvisieren von Natur aus: Bitten Sie eines, Feedback zusammenzufassen, bekommen Sie vielleicht einen Fließtext, vielleicht JSON, vielleicht eine Markdown-Tabelle – und jedes Mal etwas anderes. In einer Demo ist das kein Problem, in einem Produkt ist es eine Katastrophe: Der nachgelagerte Code kann damit schlicht nicht umgehen.
>
> Pydantic liefert **zwei Sicherungen für die strukturierte Ausgabe**:
> 1. **Vorher**: Das Schema wird an das Modell geschickt und sagt ihm klipp und klar: „Fülle genau diese Tabelle aus, für die Stimmung gibt es nur drei Optionen, die Bewertung liegt zwischen 1 und 5" – das erhöht die Trefferquote beim ersten Versuch deutlich;
> 2. **Nachher**: Dasselbe Modell validiert die Ausgabe – Fehler fallen sofort auf, und keine schmutzigen Daten fließen ins Geschäft.
>
> Zudem lässt sich die Fehlermeldung aus Schritt 2 automatisch an das Modell zurückspielen, damit es einen neuen Versuch unternimmt. Genau hier verläuft die Wasserscheide zwischen „KI-Anwendung produktionsreif" und nicht: **Eine durch ein Schema beschränkte KI-Ausgabe ist eine steuerbare Komponente; eine unbeschränkte KI-Ausgabe ist ein unkontrollierbares Zufallsereignis.**
>
> Die direkte Konsequenz für den CEO: Wenn Sie eine KI-Funktion entwerfen, **besteht Ihre Kernarbeit tatsächlich darin, diese Tabelle zu entwerfen** – welche Felder extrahiert werden sollen, welchen Wertebereich jedes Feld hat, wie die Beschreibung jedes Feldes formuliert wird. Diese Arbeit unterscheidet sich im Kern nicht vom Entwurf eines Backoffice-Formulars; sie ist die Domäne des CEO, nicht die des Algorithmen-Ingenieurs.

### 7.9 Durchgängiges Beispiel: aus einem PRD wird eine Spezifikation

Hier laufen alle bisherigen Wissensbausteine zusammen. Angenommen, das PRD sieht so aus:

> **Bestellschnittstelle**
> - Käufer-ID: Ganzzahl, Pflicht, muss größer als 0 sein
> - Positionsliste: Liste, Pflicht, 1–20 Einträge; jeder Eintrag enthält Artikelnummer (beginnt mit SKU- plus 4 Ziffern), Einzelpreis (>0), Menge (1–99)
> - Gutschein: optional; enthält Gutscheincode und Rabattsatz (0–1)
> - Bemerkung: optional, höchstens 200 Zeichen
> - Vom System berechnet: Bruttowert der Bestellung, Zahlbetrag
> - Geschäftsregel: Liegt der Bruttowert der Bestellung unter 100 Yuan, darf kein Gutschein eingesetzt werden
> - Undefinierte Felder dürfen nicht übergeben werden

Der Code:

```python
class Sku(BaseModel):
    sku_id: str = Field(pattern=r"^SKU-\d{4}$", description="商品编码")
    price: float = Field(gt=0, description="单价，单位元")
    qty: int = Field(gt=0, le=99, description="购买数量")


class Coupon(BaseModel):
    code: str
    off: float = Field(ge=0, le=1, description="折扣率，0.1 表示打 9 折")


class OrderReq(BaseModel):
    model_config = ConfigDict(extra="forbid", title="下单请求")

    buyer_id: int = Field(gt=0)
    items: list[Sku] = Field(min_length=1, max_length=20, description="购物车明细")
    coupon: Coupon | None = None
    remark: str | None = Field(default=None, max_length=200)

    @computed_field(description="订单原价")
    @property
    def gross(self) -> float:
        return round(sum(i.price * i.qty for i in self.items), 2)

    @computed_field(description="应付金额")
    @property
    def payable(self) -> float:
        off = self.coupon.off if self.coupon else 0
        return round(self.gross * (1 - off), 2)

    @model_validator(mode="after")
    def check(self):
        if self.coupon and self.gross < 100:
            raise ValueError("订单原价不足 100 元，不可使用优惠券")
        return self
```

Reguläre Eingabe:

```python
payload = {
    "buyer_id": 1001,
    "items": [{"sku_id": "SKU-0001", "price": 59.9, "qty": 2},
              {"sku_id": "SKU-0002", "price": 12.5, "qty": 1}],
    "coupon": {"code": "CP10", "off": 0.1},
}
print(OrderReq.model_validate(payload).model_dump_json(indent=2))
```

```json
{
  "buyer_id": 1001,
  "items": [
    {"sku_id": "SKU-0001", "price": 59.9, "qty": 2},
    {"sku_id": "SKU-0002", "price": 12.5, "qty": 1}
  ],
  "coupon": {"code": "CP10", "off": 0.1},
  "remark": null,
  "gross": 132.3,
  "payable": 119.07
}
```

Regelwidrige Eingabe – alle vier Fehler werden auf einmal gemeldet:

```python
bad = {"buyer_id": 0, "items": [], "coupon": {"code": "X", "off": 2}, "unknown": 1}
try:
    OrderReq.model_validate(bad)
except ValidationError as e:
    print(e)
```

```text
4 validation errors for 下单请求
buyer_id
  Input should be greater than 0 [type=greater_than, input_value=0, input_type=int]
items
  List should have at least 1 item after validation, not 0 [type=too_short, input_value=[], input_type=list]
coupon.off
  Input should be less than or equal to 1 [type=less_than_equal, input_value=2, input_type=int]
unknown
  Extra inputs are not permitted [type=extra_forbidden, input_value=1, input_type=int]
```

Die daraus automatisch erzeugte Spezifikation (`mode="serialization"`, also die Rückgabestruktur der Schnittstelle):

```json
{
  "$defs": {
    "Coupon": {
      "properties": {
        "code": {"title": "Code", "type": "string"},
        "off": {
          "description": "折扣率，0.1 表示打 9 折",
          "maximum": 1, "minimum": 0,
          "title": "Off", "type": "number"
        }
      },
      "required": ["code", "off"],
      "title": "Coupon", "type": "object"
    },
    "Sku": {
      "properties": {
        "sku_id": {
          "description": "商品编码",
          "pattern": "^SKU-\\d{4}$",
          "title": "Sku Id", "type": "string"
        },
        "price": {
          "description": "单价，单位元",
          "exclusiveMinimum": 0,
          "title": "Price", "type": "number"
        },
        "qty": {
          "description": "购买数量",
          "exclusiveMinimum": 0, "maximum": 99,
          "title": "Qty", "type": "integer"
        }
      },
      "required": ["sku_id", "price", "qty"],
      "title": "Sku", "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "buyer_id": {"exclusiveMinimum": 0, "title": "Buyer Id", "type": "integer"},
    "items": {
      "description": "购物车明细",
      "items": {"$ref": "#/$defs/Sku"},
      "maxItems": 20, "minItems": 1,
      "title": "Items", "type": "array"
    },
    "coupon": {
      "anyOf": [{"$ref": "#/$defs/Coupon"}, {"type": "null"}],
      "default": null
    },
    "remark": {
      "anyOf": [{"maxLength": 200, "type": "string"}, {"type": "null"}],
      "default": null, "title": "Remark"
    },
    "gross": {
      "description": "订单原价", "readOnly": true,
      "title": "Gross", "type": "number"
    },
    "payable": {
      "description": "应付金额", "readOnly": true,
      "title": "Payable", "type": "number"
    }
  },
  "required": ["buyer_id", "items", "gross", "payable"],
  "title": "下单请求", "type": "object"
}
```

Stellen wir jede Zeile des PRD der entsprechenden Zeile im Schema gegenüber:

| Wortlaut im PRD | Entsprechung im Schema |
|---|---|
| Käufer-ID muss größer als 0 sein | `"buyer_id": {"exclusiveMinimum": 0}` |
| Positionsliste 1–20 Einträge | `"minItems": 1, "maxItems": 20` |
| Beginnt mit SKU- plus 4 Ziffern | `"pattern": "^SKU-\\d{4}$"` |
| Menge 1–99 | `"exclusiveMinimum": 0, "maximum": 99` |
| Gutschein optional | `"anyOf": [{...}, {"type":"null"}], "default": null` |
| Bemerkung höchstens 200 Zeichen | `"maxLength": 200` |
| Vom System berechnete Felder | `"readOnly": true` |
| Keine undefinierten Felder erlaubt | `"additionalProperties": false` |
| Unter 100 Yuan Bruttowert kein Gutschein | **nicht im Schema enthalten** (eigene Geschäftsregeln lassen sich nicht ausdrücken) |

> ⚠️ **Fallstrick**: Die letzte Zeile ist wichtig. **Eigene Geschäftsregeln in einem `model_validator` erscheinen nicht im JSON Schema.** JSON Schema kann nur „strukturelle" Beschränkungen ausdrücken (Typ, Wertebereich, Länge, Aufzählung), aber keine Geschäftslogik wie „unter 100 Yuan Bruttowert kein Gutschein".
>
> Für KI-Szenarien bedeutet das: **Solche Regeln sieht das Modell nicht, es kann also Ergebnisse erzeugen, die gegen Geschäftsregeln verstoßen.** Es gibt zwei Auswege: (1) Die Regel in die `description` eines Feldes schreiben, damit das Modell sie sieht; (2) auf nachgelagerte Validierung plus Wiederholung nach Fehlermeldung setzen. Im Produktivbetrieb brauchen Sie beides.

### 7.10 Schema auf oberster Ebene und über mehrere Modelle

**Welches Problem wird gelöst**: die Spezifikationen mehrerer Modelle in einem Rutsch zu einer einzigen zusammenführen (nützlich beim Erstellen einer vollständigen API-Dokumentation).

```python
from pydantic.json_schema import models_json_schema


class A1(BaseModel):
    x: int


class B1(BaseModel):
    y: A1


keys, top = models_json_schema([(A1, "validation"), (B1, "validation")])
print(json.dumps(top, indent=2, ensure_ascii=False))
```

```json
{
  "$defs": {
    "A1": {
      "properties": {"x": {"title": "X", "type": "integer"}},
      "required": ["x"], "title": "A1", "type": "object"
    },
    "B1": {
      "properties": {"y": {"$ref": "#/$defs/A1"}},
      "required": ["y"], "title": "B1", "type": "object"
    }
  }
}
```

**Referenzpfad anpassen** (bei der Anbindung an OpenAPI muss das Referenzpräfix `#/components/schemas/` lauten):

```python
print(json.dumps(B1.model_json_schema(ref_template="#/components/schemas/{model}"),
                 indent=2, ensure_ascii=False))
```

```json
{
  "$defs": { "A1": {...} },
  "properties": {
    "y": { "$ref": "#/components/schemas/A1" }
  },
  "required": ["y"],
  "title": "B1",
  "type": "object"
}
```

> 👉 **CEO-Perspektive**: Der Parameter `ref_template` erklärt, warum Frameworks wie FastAPI automatisch eine vollständige Swagger-Dokumentation erzeugen können – sie nehmen schlicht die Schemas aller Pydantic-Modelle und fügen sie gemäß der OpenAPI-Spezifikation zu einem großen Dokument zusammen. **Ob die Schnittstellendokumentation Ihres Teams „immer deckungsgleich mit dem Code" ist, hängt daran, ob dieser Weg gegangen wird** (automatische Erzeugung) oder ob jemand von Hand ein Word-Dokument pflegt. Das ist eine Sache, für die es sich zu kämpfen lohnt.

---
## 8. Diskriminierte Unions: „Erst wer A wählt, bekommt die Feldgruppe B zu sehen"

### 8.1 Welches Problem sie löst

Das ist eine Anforderung, die Sie aus der Produktarbeit bestens kennen — **Formular-Verkettung / bedingte Felder**:

- Benachrichtigung versenden: Bei „SMS" braucht es Mobilnummer + Template-ID; bei „E-Mail" Empfängeradresse + Betreff + CC; bei „App-Push" Device-Token + Badge-Zahl
- Zahlungsart: Bei „Bankkarte" braucht es Kartennummer + Kontoinhaber; bei „Alipay" die Kontokennung
- Rechnungstyp: Bei „Umsatzsteuer-Sonderrechnung" braucht es Steuernummer + Bankverbindung; bei „einfacher Rechnung" nur den Rechnungsempfänger

Die gemeinsame Struktur lautet stets: **ein Typ-Auswahlfeld + je Typ eine eigene Gruppe von Feldern**.

In Pydantic heißt das **discriminated union (diskriminierte Union)**, und das Feld `type` heißt **discriminator (Diskriminator)**.

### 8.2 Was ohne Diskriminator passiert

Sehen wir uns zunächst das Negativbeispiel an:

```python
class Sms(BaseModel):
    phone: str
    template_id: str


class Email(BaseModel):
    address: str
    subject: str


class NotifyBad(BaseModel):
    channel: Sms | Email          # gewöhnliche Union, ohne Diskriminator


try:
    NotifyBad(channel={"phone": "138", "subject": "x"})
except ValidationError as e:
    print(e)
```

```text
2 validation errors for NotifyBad
channel.Sms.template_id
  Field required [type=missing, input_value={'phone': '138', 'subject': 'x'}, input_type=dict]
channel.Email.address
  Field required [type=missing, input_value={'phone': '138', 'subject': 'x'}, input_type=dict]
```

Pydantic hat nacheinander `Sms` und `Email` durchprobiert, beide sind gescheitert — und deshalb **meldet es Ihnen beide Fehlergruppen zugleich**. Wollte die Nutzerin nun eine SMS oder eine E-Mail versenden? Das Programm weiß es nicht, und folglich kann auch die Fehlermeldung keine brauchbare Orientierung geben. Sobald die Datenmenge und die Zahl der Zweige wachsen, ist eine solche Fehlermeldung schlicht unlesbar.

### 8.3 Mit Diskriminator

```python
from typing import Annotated, Literal


class SmsCfg(BaseModel):
    type: Literal["sms"]                            # ← Diskriminator-Feld
    phone: str = Field(pattern=r"^1\d{10}$")
    template_id: str


class EmailCfg(BaseModel):
    type: Literal["email"]
    address: str
    subject: str
    cc: list[str] = []


class PushCfg(BaseModel):
    type: Literal["push"]
    device_token: str
    badge: int = Field(ge=0, default=1)


# Die entscheidende Zeile: Pydantic soll anhand des Felds type unterscheiden
Channel = Annotated[SmsCfg | EmailCfg | PushCfg, Field(discriminator="type")]


class Notification(BaseModel):
    title: str
    channel: Channel
```

In der Anwendung:

```python
n = Notification.model_validate({
    "title": "订单已发货",
    "channel": {"type": "sms", "phone": "13800138000", "template_id": "T001"},
})
print(n)
print(n.model_dump())

n2 = Notification.model_validate({
    "title": "周报",
    "channel": {"type": "email", "address": "a@b.com", "subject": "本周数据"},
})
print(n2.model_dump())
```

```text
title='订单已发货' channel=SmsCfg(type='sms', phone='13800138000', template_id='T001')
{'title': '订单已发货', 'channel': {'type': 'sms', 'phone': '13800138000', 'template_id': 'T001'}}
{'title': '周报', 'channel': {'type': 'email', 'address': 'a@b.com', 'subject': '本周数据', 'cc': []}}
```

Als Strukturbild:

```text
                          channel
                             │
                   看 type 这一个字段
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
   type="sms"           type="email"         type="push"
   ┌──────────┐        ┌──────────┐        ┌──────────────┐
   │ phone    │        │ address  │        │ device_token │
   │ template │        │ subject  │        │ badge        │
   │  _id     │        │ cc       │        │              │
   └──────────┘        └──────────┘        └──────────────┘
```

### 8.4 Die Fehlermeldungen werden präzise

**Ein nicht existierender Typ wurde gewählt**:

```text
1 validation error for Notification
channel
  Input tag 'fax' found using 'type' does not match any of the expected tags: 'sms', 'email', 'push'
  [type=union_tag_invalid, input_value={'type': 'fax', 'no': '1'}, input_type=dict]
```

Sie erfahren unmittelbar: „Zur Auswahl stehen nur diese drei Typen."

**Der Typ stimmt, aber ein Feld dieses Zweigs fehlt**:

```text
1 validation error for Notification
channel.sms.template_id
  Field required [type=missing, input_value={'type': 'sms', 'phone': '13800138000'}, input_type=dict]
```

`channel.sms.template_id` — punktgenau bis auf „das Feld template_id im sms-Zweig des Felds channel". Verglichen mit dem „alle Fehler aller Zweige auf einmal" aus Abschnitt 8.2 liegen dazwischen Welten.

**Das Feld type wurde vergessen**:

```text
1 validation error for Notification
channel
  Unable to extract tag using discriminator 'type' [type=union_tag_not_found, input_value={'phone': '13800138000'}, input_type=dict]
```

| Fehlercode | Bedeutung | Wie das Frontend damit umgehen sollte |
|---|---|---|
| `union_tag_not_found` | Kein Typ übergeben | Hinweis „Bitte wählen Sie zuerst einen Benachrichtigungsweg" |
| `union_tag_invalid` | Typ steht nicht zur Auswahl | Hinweis „Nicht unterstützter Benachrichtigungsweg" |
| Gewöhnlicher Fehler innerhalb eines Zweigs | Typ stimmt, aber ein Feld ist fehlerhaft | Das betroffene Eingabefeld des Zweigs rot markieren |

### 8.5 Bei der Serialisierung gehen keine Felder verloren

Erinnern Sie sich an den Fallstrick aus Abschnitt 6.5, bei dem „Vererbung Felder verschwinden lässt". Diskriminierte Unions haben dieses Problem nicht:

```python
print(Notification(title="t", channel=PushCfg(type="push", device_token="abc")).model_dump())
```

```text
{'title': 't', 'channel': {'type': 'push', 'device_token': 'abc', 'badge': 1}}
```

`device_token` und `badge` sind beide vorhanden. Denn der deklarierte Typ ist eben jene Union, und Pydantic weiß daher, dass es nach dem tatsächlich vorliegenden Zweig exportieren muss.

### 8.6 Das JSON Schema einer diskriminierten Union

Hier treffen sich dieses Kapitel und Kapitel 7:

```json
"channel": {
  "discriminator": {
    "mapping": {
      "email": "#/$defs/EmailCfg",
      "push": "#/$defs/PushCfg",
      "sms": "#/$defs/SmsCfg"
    },
    "propertyName": "type"
  },
  "oneOf": [
    {"$ref": "#/$defs/SmsCfg"},
    {"$ref": "#/$defs/EmailCfg"},
    {"$ref": "#/$defs/PushCfg"}
  ],
  "title": "Channel"
}
```

Drei Bestandteile:
- `"oneOf"`: **eines von dreien** (nicht anyOf, sondern streng genau eines);
- `"propertyName": "type"`: **anhand welcher Spalte entschieden wird**;
- `"mapping"`: die Zuordnungstabelle **Wert → zugehörige Untertabelle**.

Das Feld `type` jedes Zweigs sieht im Schema so aus:

```json
"type": { "const": "sms", "title": "Type", "type": "string" }
```

`const` bedeutet: „In dieses Feld darf ausschließlich dieser feste Wert eingetragen werden."

> 👉 **CEO-Perspektive**: Der Abschnitt `mapping` ist exakt jene **Verkettungsregel-Tabelle**, die Sie im PRD gezeichnet haben:
>
> | Auswahl „Benachrichtigungsweg" | Eingeblendete Felder |
> |---|---|
> | SMS | Mobilnummer, SMS-Template |
> | E-Mail | Empfängeradresse, Betreff, CC |
> | Push | Device-Token, Badge-Zahl |
>
> Haargenau dasselbe. Und weil es Eingang ins JSON Schema gefunden hat, gilt: **Die Formular-Engine im Frontend kann es direkt auslesen und daraus das verkettete Formular rendern, und auch das LLM versteht, dass bei sms die Felder phone und template_id auszufüllen sind**. Die Verkettungslogik, die Sie im PRD skizziert haben, fließt automatisch bis ins Frontend und in die KI durch — ohne dass jemand dazwischen mündlich weitererzählen müsste.

### 8.7 Diskriminierte Unions in Listen

```python
class Flow(BaseModel):
    steps: list[Channel]


f = Flow.model_validate({"steps": [
    {"type": "sms", "phone": "13800138000", "template_id": "T1"},
    {"type": "push", "device_token": "tok", "badge": 3},
]})
print(f.model_dump())
print([type(s).__name__ for s in f.steps])
```

```text
{'steps': [{'type': 'sms', 'phone': '13800138000', 'template_id': 'T1'}, {'type': 'push', 'device_token': 'tok', 'badge': 3}]}
['SmsCfg', 'PushCfg']
```

> 👉 **CEO-Perspektive**: Genau das ist die Datenstruktur einer **Workflow-Orchestrierung bzw. einer Regel-Engine für Automatisierung**. „Nach der Registrierung eines neuen Nutzers: ① Willkommens-SMS senden ② nach 3 Tagen einen Push senden ③ nach 7 Tagen eine E-Mail senden" — eine Liste aus Schritten unterschiedlichen Typs. Marketing-Automation, die Konfiguration von Genehmigungsprozessen, der mehrstufige Plan eines Agenten: Auf der Modellierungsebene sehen sie alle so aus.

### 8.8 Der Smart-Modus gewöhnlicher Unions

Nicht jede Union braucht einen Diskriminator. Bei einfachen Unions aus völlig verschiedenen Typen trifft Pydantic eine intelligente Wahl:

```python
class U(BaseModel):
    v: int | str


print(U(v="123").v, type(U(v="123").v).__name__)
print(U(v=123).v, type(U(v=123).v).__name__)
```

```text
123 str
123 int
```

Wer eine Zeichenkette übergibt, behält eine Zeichenkette; wer eine Ganzzahl übergibt, behält eine Ganzzahl — **bevorzugt wird derjenige Zweig, der „keine Konvertierung erfordert"**, und nicht etwa der erste von links, der sich erfolgreich konvertieren ließe.

> ⚠️ **Fallstrick**: Die offizielle Empfehlung lautet, **gewöhnliche Unions möglichst sparsam einzusetzen**. Der Grund: An jeder Stelle, die dieses Feld verwendet, muss zuerst geprüft werden, „welcher Typ es diesmal denn ist" — der Code wird dadurch sehr geschwätzig. Wenn Ihr Ziel lediglich lautet, „Zahlen auch in Zeichenkettenform anzunehmen", schreiben Sie einfach `int` (Pydantic konvertiert automatisch) und nicht `int | str`.

---
## 9. ValidationError: Wie Sie diesen Fehlerbericht lesen

### 9.1 Welches Problem löst er

Wenn die Validierung fehlschlägt, brauchen Sie einen **strukturierten, maschinell weiterverarbeitbaren** Fehlerbericht – und nicht nur einen Satz in Alltagssprache.

```python
class Addr(BaseModel):
    city: str
    zipcode: str = Field(pattern=r"^\d{6}$")


class Reg(BaseModel):
    name: str = Field(min_length=2)
    age: int = Field(ge=18)
    role: Literal["admin", "user"]
    addr: Addr


try:
    Reg.model_validate({"name": "A", "age": 15, "role": "boss",
                        "addr": {"zipcode": "12"}})
except ValidationError as e:
    print(e)
```

```text
5 validation errors for Reg
name
  String should have at least 2 characters [type=string_too_short, input_value='A', input_type=str]
    For further information visit https://errors.pydantic.dev/2.13/v/string_too_short
age
  Input should be greater than or equal to 18 [type=greater_than_equal, input_value=15, input_type=int]
    For further information visit https://errors.pydantic.dev/2.13/v/greater_than_equal
role
  Input should be 'admin' or 'user' [type=literal_error, input_value='boss', input_type=str]
    For further information visit https://errors.pydantic.dev/2.13/v/literal_error
addr.city
  Field required [type=missing, input_value={'zipcode': '12'}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.13/v/missing
addr.zipcode
  String should match pattern '^\d{6}$' [type=string_pattern_mismatch, input_value='12', input_type=str]
    For further information visit https://errors.pydantic.dev/2.13/v/string_pattern_mismatch
```

**Alle fünf Fehler werden auf einen Schlag gemeldet – einschließlich derer in der verschachtelten Untertabelle.**

### 9.2 Strukturiert auslesen: e.errors()

```python
for item in err.errors():
    print(item)
```

```text
{'type': 'string_too_short', 'loc': ('name',), 'msg': 'String should have at least 2 characters', 'input': 'A', 'ctx': {'min_length': 2}, 'url': '...'}
{'type': 'greater_than_equal', 'loc': ('age',), 'msg': 'Input should be greater than or equal to 18', 'input': 15, 'ctx': {'ge': 18}, 'url': '...'}
{'type': 'literal_error', 'loc': ('role',), 'msg': "Input should be 'admin' or 'user'", 'input': 'boss', 'ctx': {'expected': "'admin' or 'user'"}, 'url': '...'}
{'type': 'missing', 'loc': ('addr', 'city'), 'msg': 'Field required', 'input': {'zipcode': '12'}, 'url': '...'}
{'type': 'string_pattern_mismatch', 'loc': ('addr', 'zipcode'), 'msg': "String should match pattern '^\\d{6}$'", 'input': '12', 'ctx': {'pattern': '^\\d{6}$'}, 'url': '...'}
```

Die fünf Schlüssel jedes einzelnen Fehlers:

| Schlüssel | Bedeutung | Wer nutzt ihn |
|---|---|---|
| `type` | **Fehlercode**, eine maschinenlesbare, stabile Kennung | Das Frontend für die Zuordnung mehrsprachiger Texte, das Monitoring für Auswertungen nach Kategorien |
| `loc` | **Position**, ein Tupel, das Ebene für Ebene lokalisiert | Das Frontend, um das konkrete Eingabefeld zu treffen |
| `msg` | Menschenlesbare englische Beschreibung | Rückfallanzeige / Protokoll |
| `input` | Was der Nutzer tatsächlich übergeben hat | Fehlersuche |
| `ctx` | Der Kontext der Beschränkung (etwa `{'min_length': 2}`) | **Der Schlüssel für den fertig formulierten Anzeigetext** |

### 9.3 loc: die genaue Position bestimmen

```python
class Deep(BaseModel):
    orders: list[Reg]


try:
    Deep.model_validate({"orders": [{"name": "ok", "age": 20, "role": "user",
                                     "addr": {"city": "北京", "zipcode": "1"}}]})
except ValidationError as e:
    print(e.errors()[0]["loc"], "->", ".".join(str(x) for x in e.errors()[0]["loc"]))
```

> ⚠️ **Fallstrick (von Python selbst, nicht von Pydantic)**: In den folgenden Abschnitten dieses Kapitels analysieren wir dieses Fehlerobjekt weiter. Allerdings **löscht Python die Variable `e` automatisch, sobald der `except`-Block endet**; ein Zugriff außerhalb des Blocks führt zu einem `NameError`. Beim tatsächlichen Ausführen müssen Sie sie deshalb zuerst sichern:
>
> ```python
> except ValidationError as e:
>     err = e            # ← in eine andere Variable sichern, sonst steht sie später nicht zur Verfügung
> ```
>
> In den folgenden Beispielen bezeichnet einheitlich `err` dieses bereits abgefangene Fehlerobjekt.

```text
('orders', 0, 'addr', 'zipcode') -> orders.0.addr.zipcode
```

Im Tupel von `loc` gilt: **Zeichenketten sind Feldnamen, Zahlen sind Listenindizes.** `('orders', 0, 'addr', 'zipcode')` bedeutet also „die Postleitzahl in der Adresse der 1. Bestellung".

### 9.4 Kurzreferenz der häufigsten Fehlercodes

| `type` | Auslösende Bedingung | Empfohlener Anzeigetext |
|---|---|---|
| `missing` | Pflichtfeld wurde nicht übergeben | Bitte {Feldname} ausfüllen |
| `string_too_short` / `string_too_long` | Länge der Zeichenkette | Die Länge muss zwischen {min} und {max} liegen |
| `string_pattern_mismatch` | Regulärer Ausdruck passt nicht | Das Format ist nicht korrekt |
| `greater_than` / `greater_than_equal` | Untergrenze eines Zahlenwerts | Muss größer (oder gleich) {ctx.gt} sein |
| `less_than` / `less_than_equal` | Obergrenze eines Zahlenwerts | Muss kleiner (oder gleich) {ctx.le} sein |
| `int_parsing` / `float_parsing` | Lässt sich nicht in eine Zahl umwandeln | Bitte eine Zahl eingeben |
| `literal_error` | Wert steht nicht in der Auswahlliste | Bitte wählen Sie: {ctx.expected} |
| `too_short` / `too_long` | Länge einer Liste | Die Anzahl muss zwischen {min} und {max} liegen |
| `extra_forbidden` | Ein nicht definiertes Feld wurde übergeben | Es wurde ein nicht unterstützter Parameter übergeben |
| `value_error` | Von einem eigenen Validator ausgelöst | Ihr eigener, selbst formulierter Text |
| `union_tag_not_found` / `union_tag_invalid` | Typproblem bei einer diskriminierten Union | Bitte wählen Sie den richtigen Typ |
| `frozen_instance` | Ein unveränderliches Objekt wurde geändert | Dieser Datensatz darf nicht geändert werden |

### 9.5 Eigene Fehlertexte

```python
class Order(BaseModel):
    qty: int

    @field_validator("qty")
    @classmethod
    def chk(cls, v):
        if v > 100:
            raise ValueError("单次下单不能超过 100 件，请联系客服走大宗采购")
        return v


try:
    Order(qty=500)
except ValidationError as e:
    print(e.errors()[0]["msg"])
```

```text
Value error, 单次下单不能超过 100 件，请联系客服走大宗采购
```

Ein `ValueError`, den ein eigener Validator auslöst, wird in `type='value_error'` verpackt, und dem `msg` wird automatisch das Präfix `Value error, ` vorangestellt.

### 9.6 Als JSON an das Frontend ausgeben

```python
print(err.json())                                        # Vollversion
print(err.json(include_url=False, include_input=False))  # Schlanke Version: direkt ein JSON-String
```

Die schlanke Version:

```json
[
  {"type": "string_too_short", "loc": ["name"], "msg": "String should have at least 2 characters", "ctx": {"min_length": 2}},
  {"type": "greater_than_equal", "loc": ["age"], "msg": "Input should be greater than or equal to 18", "ctx": {"ge": 18}},
  {"type": "literal_error", "loc": ["role"], "msg": "Input should be 'admin' or 'user'", "ctx": {"expected": "'admin' or 'user'"}},
  {"type": "missing", "loc": ["addr", "city"], "msg": "Field required"},
  {"type": "string_pattern_mismatch", "loc": ["addr", "zipcode"], "msg": "String should match pattern '^\\d{6}$'", "ctx": {"pattern": "^\\d{6}$"}}
]
```

> ⚠️ **Fallstrick**: **Im Produktivbetrieb müssen Sie unbedingt `include_input=False` verwenden.** Das Feld `input` gibt den vom Nutzer übergebenen Originalwert unverändert zurück – handelt es sich dabei um ein Passwort, eine Ausweis- oder eine Kontonummer, landet dieser Wert im Fehlerprotokoll oder geht direkt an das Frontend zurück. Das ist ein ganz realer Weg, auf dem Daten abfließen.

> 👉 **CEO-Perspektive**: Der Produktwert dieses Kapitels lässt sich in einem Satz bündeln: **Ein Fehlerbericht ist ein Datensatz, kein Fließtext.**
>
> Weil er ein Datensatz ist, können Sie die folgenden Anforderungen in Ihr PRD schreiben – und alle sind technisch leicht umzusetzen:
> 1. **Alles auf einmal melden**: Der Nutzer korrigiert einmal und kann dann absenden, statt fünfmal abzuschicken und fünf Fehler nacheinander zu beheben (Pydantic tut das standardmäßig bereits);
> 2. **Punktgenaue Verortung**: `loc` sagt dem Frontend, unter welchem Eingabefeld die rote Meldung erscheint – auch bei verschachtelten Positionen wie „die Mobilnummer in Position 3";
> 3. **Texte in der Landessprache**: Das Frontend setzt aus `type` + `ctx` den Anzeigetext zusammen; werfen Sie dem Nutzer nicht einfach `String should have at least 2 characters` vor die Füße;
> 4. **Sensible Werte nicht zurückspiegeln**: `include_input=False`;
> 5. **Auswertbarkeit**: Wenn Sie `type` + `loc` als Messpunkte erfassen und melden, erkennen Sie, „bei welchem Feld sich Nutzer am häufigsten vertun" – das sind Daten aus erster Hand für die Optimierung Ihres Formulardesigns. Punkt 5 lohnt sich besonders: Er sagt Ihnen unmittelbar, an welcher Stelle das Formular schlecht gestaltet ist.
>
> Wir empfehlen, diese fünf Punkte im Abschnitt „Fehlerbehandlung" Ihres PRD als allgemeingültige Vorgabe festzuschreiben.

---
## 10. model_config / ConfigDict: die globalen Schalter für die ganze Tabelle

### 10.0 Konfigurations-Gesamtübersicht

Die Konfiguration steht innerhalb der Klasse und wird über `model_config = ConfigDict(...)` gesetzt:

```python
from pydantic import ConfigDict


class M(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    a: int
```

| Konfigurationsoption | Wirkung | CEO-Intuition |
|---|---|---|
| `extra` | Was passiert mit zusätzlich übergebenen Feldern (`ignore`/`forbid`/`allow`) | Darf das Formular mehr enthalten als vorgesehen |
| `frozen` | Nach der Erzeugung nicht mehr änderbar | Nur-Lese-Datensatz / Snapshot |
| `validate_assignment` | Bei jeder Zuweisung wird erneut validiert | Auch Änderungen müssen durch die Prüfung |
| `populate_by_name` | Alias und Originalname werden beide akzeptiert | Kompatibilität zwischen alten und neuen Feldnamen (ab 2.11 wird stattdessen `validate_by_name` + `validate_by_alias` empfohlen, diese Option entfällt in v3) |
| `str_strip_whitespace` | Bei allen Strings werden führende und abschließende Leerzeichen automatisch entfernt | Globale Eingabebereinigung |
| `str_to_lower` / `str_to_upper` | Alle Strings werden einheitlich klein- bzw. großgeschrieben | Globale Normalisierung |
| `use_enum_values` | Speichert den Wert des Enums statt des Enum-Objekts | Vereinfachte Speicherung |
| `title` | Der Anzeigename dieser Tabelle | Tabellenname (fließt ins Schema ein) |
| `validate_default` | Auch Standardwerte müssen die Validierung bestehen | Auch Standardwerte müssen regelkonform sein |
| `arbitrary_types_allowed` | Erlaubt Typen, die Pydantic nicht kennt | Notausstieg |
| `alias_generator` | Erzeugt Aliase im Stapel (z. B. alles in CamelCase) | Namenskonvention per Knopfdruck umstellen |

### 10.1 extra: Was passiert mit zusätzlich übergebenen Feldern

**Welches Problem es löst**: Von außen kommt ein Feld, das im Modell gar nicht definiert ist – ignorieren, Fehler melden oder behalten?

```python
class Ignore(BaseModel):
    model_config = ConfigDict(extra="ignore")     # Standard
    a: int


class Forbid(BaseModel):
    model_config = ConfigDict(extra="forbid")
    a: int


class Allow(BaseModel):
    model_config = ConfigDict(extra="allow")
    a: int


print("ignore:", Ignore(a=1, b=2).model_dump())
try:
    Forbid(a=1, b=2)
except ValidationError as e:
    print("forbid:", e.errors()[0]["type"], e.errors()[0]["loc"])
al = Allow(a=1, b=2)
print("allow :", al.model_dump(), "| al.b =", al.b)
```

```text
ignore: {'a': 1}
forbid: extra_forbidden ('b',)
allow : {'a': 1, 'b': 2} | al.b = 2
```

| Wert | Verhalten | Wann einsetzen |
|---|---|---|
| `"ignore"` (Standard) | Wird stillschweigend verworfen | Anbindung an Dritte, bei denen die Gegenseite jederzeit Felder ergänzen kann |
| `"forbid"` | Fehlermeldung | Interne Schnittstellen, bei denen strikte Übereinstimmung gewünscht ist; verhindert Tippfehler in Feldnamen |
| `"allow"` | Bleibt unverändert erhalten, lesbar und exportierbar | Wenn unbekannte Felder durchgereicht werden müssen (z. B. Gateway, Proxy-Schicht) |

> 👉 **CEO-Perspektive**: Das ist eine **Governance-Strategie für Schnittstellen**, und je nach Szenario ist ein anderer Wert richtig:
> - **Interne Schnittstellen** → `forbid`. Wenn das Frontend `phoneNumber` als `phonNumber` schreibt, gibt es sofort einen Fehler, statt dass das Feld stillschweigend verloren geht und zwei Tage später beim Kundenservice die Beschwerde eingeht: „Ich habe meine Handynummer doch eingetragen."
> - **Externe Schnittstellen / Callbacks von Dritten** → `ignore` (Standard). Wenn die Gegenseite ein Update mit neuen Feldern ausrollt, darf Ihr System deswegen nicht ausfallen.
> - **Gateway- / Vermittlungsschicht** → `allow`. Auch Felder, die Sie nicht verstehen, müssen unverändert weitergereicht werden.
>
> Diese drei Punkte können Sie unmittelbar in Ihre Schnittstellenrichtlinie übernehmen.

### 10.2 frozen: nur lesbar

```python
class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)
    a: int


fz = Frozen(a=1)
try:
    fz.a = 2
except ValidationError as e:
    print(e.errors()[0]["type"], e.errors()[0]["msg"])
print("可以做 dict 的 key:", {fz: "ok"}[Frozen(a=1)])
```

```text
frozen_instance Instance is frozen
可以做 dict 的 key: ok
```

`frozen=True` hat einen zusätzlichen Effekt: Das Objekt wird hashbar und kann damit als Schlüssel eines Dictionarys oder als Element einer Menge verwendet werden.

> 👉 **CEO-Perspektive**: `frozen` entspricht dem, was im Produkt „**Snapshot / Nachweis / unveränderbarer Datensatz**" heißt.
> - Der Preis-Snapshot **zum Zeitpunkt des Kaufabschlusses** – wenn der Artikelpreis später geändert wird, darf sich der Preis in historischen Bestellungen nicht mitverändern;
> - Vertragsklauseln nach der Unterzeichnung;
> - Audit-Logs.
>
> Wenn im PRD steht „Historische Bestellungen zeigen den Preis zum Bestellzeitpunkt", dann steckt genau dieses Konzept dahinter. Mit `frozen=True` verankern Sie die Regel „nicht veränderbar" fest im Code – das ist erheblich verlässlicher, als sich darauf zu verlassen, dass Entwickler von sich aus nichts daran ändern.

### 10.3 validate_assignment

Siehe Abschnitt 2.6 und 5.9. Standardmäßig deaktiviert; ist es aktiviert, läuft bei jeder Zuweisung die Validierung erneut durch (mit einem geringen Performance-Aufwand, der in der Regel vernachlässigbar ist).

### 10.4 populate_by_name

Siehe Abschnitt 3.9. Sorgt dafür, dass sowohl der Alias als auch der ursprüngliche Feldname als Eingabe akzeptiert werden.

### 10.5 Globale String-Bereinigung

```python
class Clean(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, str_to_lower=True)
    email: str


print(repr(Clean(email="  Foo@Bar.COM ").email))
```

```text
'foo@bar.com'
```

> 👉 **CEO-Perspektive**: Damit heben Sie „Leerzeichen entfernen" und „E-Mail-Adressen einheitlich kleinschreiben" auf die Ebene einer **Standardregel für die gesamte Tabelle**, statt sie an jedem Feld einzeln zu setzen. Bei Formularen wie einer Nutzerregistrierung ist das sehr praktisch – dass E-Mail-Adressen nicht zwischen Groß- und Kleinschreibung unterscheiden und Benutzernamen keine führenden oder abschließenden Leerzeichen enthalten dürfen, ist eine allgemeine Regel und kein Sonderfall eines einzelnen Feldes.
>
> ⚠️ Vorsicht jedoch bei `str_to_lower`: Wenn diese Tabelle ein Feld für „Passwort" oder einen „Code mit Groß-/Kleinschreibungsunterscheidung" enthält, richtet eine globale Kleinschreibung Schaden an. Solche Konfigurationen eignen sich für Tabellen, deren Felder einem einheitlichen Zweck dienen.

### 10.6 use_enum_values

```python
from enum import Enum


class Status(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


class E1(BaseModel):
    s: Status


class E2(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    s: Status


print("默认           :", repr(E1(s="draft").s))
print("use_enum_values:", repr(E2(s="draft").s))
```

```text
默认           : <Status.DRAFT: 'draft'>
use_enum_values: 'draft'
```

Ist die Option aktiviert, steht im Feld direkt der String `'draft'` und nicht das Enum-Objekt. Der Vorteil: Speichern in der Datenbank und die Umwandlung nach JSON werden einfacher. Der Nachteil: Sie verlieren die Typunterstützung und die Methoden des Enum-Objekts.

### 10.7 Weitere gebräuchliche Konfigurationen

```python
class Misc(BaseModel):
    model_config = ConfigDict(
        title="配置示例",                  # Tabellenname, der ins JSON Schema wandert
        populate_by_name=True,            # Alias und Originalname werden beide akzeptiert
        validate_default=True,            # Auch Standardwerte müssen die Validierung bestehen
        arbitrary_types_allowed=True,     # Erlaubt Typen, die Pydantic nicht kennt
    )
    a: int = Field(alias="A", default=1)


print(Misc(a=5), Misc(A=6))
print(Misc.model_json_schema()["title"])
```

```text
a=5 a=6
配置示例
```

**`validate_default=True`** verdient eine gesonderte Erwähnung: Standardmäßig werden Standardwerte **nicht validiert**. Sie können also `age: int = Field(ge=18, default=0)` schreiben, und Pydantic hält diesen offensichtlich regelwidrigen Standardwert nicht auf. Erst mit aktiviertem `validate_default` tut es das.

> 👉 **CEO-Perspektive**: `title` fließt direkt ins JSON Schema ein und taucht damit in der API-Dokumentation und in der Spezifikation für das LLM auf. **Der Tabelle einen sprechenden Namen in der Landessprache zu geben, ist deutlich freundlicher, als sie als `OrderReq` anzuzeigen** – besonders dann, wenn das LLM sie liest: Ein Tabellenname in der Landessprache plus Feldbeschreibungen in der Landessprache erhöhen die Trefferquote beim Verständnis des Modells spürbar.

### 10.8 Auch die Konfiguration ist vererbbar

Unterklassen erben die `model_config` ihrer Oberklasse und können einzelne Optionen davon überschreiben. Ein Team kann also eine „Basisklasse" definieren, in der die Unternehmensvorgaben stehen (etwa einheitlich `extra="forbid"` plus `str_strip_whitespace=True`), und alle Fachmodelle erben von ihr.

> 👉 **CEO-Perspektive**: Genau so **setzt man technische Vorgaben tatsächlich durch**. Statt im Wiki den Satz „Alle Schnittstellen müssen den Strict Mode aktivieren" zu hinterlegen und dann im Code-Review darauf zu hoffen, stellen Sie besser eine Basisklasse bereit, von der alle erben – **machen Sie die Vorgabe zum Standardverhalten statt zur Disziplinanforderung**. Dieselbe Denkweise trägt auch im Produktdesign.

---

## 11. TypeAdapter: Validierung für alles, was „keine Tabelle" ist

### 11.1 Welches Problem es löst

Alle bisherigen Fähigkeiten hängen an `BaseModel`. Manchmal ist das, was Sie validieren wollen, aber **keine Tabelle**:

- Die Schnittstelle liefert ein **Array** zurück: `[{...}, {...}]`
- Ein Konfigurationswert ist ein **Dictionary**: `{"key": "value"}`
- Sie wollen lediglich prüfen, ob **eine einzelne Zahl** im gültigen Bereich liegt

In diesen Fällen brauchen Sie kein Modell drumherum zu bauen – mit `TypeAdapter` validieren Sie beliebige Typen direkt.

```python
from pydantic import TypeAdapter


ta_list = TypeAdapter(list[int])
print(ta_list.validate_python(["1", 2, "3"]))     # Konvertiert genauso
try:
    ta_list.validate_python(["a"])
except ValidationError as e:
    print(e)
```

```text
[1, 2, 3]
1 validation error for list[int]
0
  Input should be a valid integer, unable to parse string as an integer [type=int_parsing, input_value='a', input_type=str]
```

Beachten Sie die `0` in der Fehlermeldung – das ist der Listenindex.

### 11.2 Eine Liste von Modellen validieren

Der häufigste Anwendungsfall: Die Schnittstelle liefert ein Array zurück.

```python
class Addr(BaseModel):
    city: str
    zipcode: str = Field(pattern=r"^\d{6}$")


ta = TypeAdapter(list[Addr])
print(ta.validate_json('[{"city":"上海","zipcode":"200000"}]'))
```

```text
[Addr(city='上海', zipcode='200000')]
```

Mit Dictionarys funktioniert es ebenso:

```python
ta_dict = TypeAdapter(dict[str, Addr])
print(ta_dict.validate_python({"home": {"city": "北京", "zipcode": "100000"}}))
```

```text
{'home': Addr(city='北京', zipcode='100000')}
```

### 11.3 Einen einzelnen Wert mit Beschränkung validieren

```python
Score = Annotated[int, Field(ge=0, le=100)]
ta_score = TypeAdapter(Score)

print(ta_score.validate_python(88))
try:
    ta_score.validate_python(120)
except ValidationError as e:
    print(e.errors()[0]["msg"])
```

```text
88
Input should be less than or equal to 100
```

### 11.4 TypeAdapter liefert ebenfalls Schema und Serialisierung

```python
print(json.dumps(TypeAdapter(list[Addr]).json_schema(), indent=2, ensure_ascii=False))
print(ta_list.dump_json([1, 2, 3]))
```

```json
{
  "$defs": {
    "Addr": {
      "properties": {
        "city": {"title": "City", "type": "string"},
        "zipcode": {"pattern": "^\\d{6}$", "title": "Zipcode", "type": "string"}
      },
      "required": ["city", "zipcode"],
      "title": "Addr", "type": "object"
    }
  },
  "items": {"$ref": "#/$defs/Addr"},
  "type": "array"
}
```

```text
b'[1,2,3]'
```

Die Methoden von `TypeAdapter` entsprechen denen von `BaseModel`:

| BaseModel | TypeAdapter |
|---|---|
| `Model.model_validate(x)` | `ta.validate_python(x)` |
| `Model.model_validate_json(s)` | `ta.validate_json(s)` |
| `obj.model_dump()` | `ta.dump_python(obj)` |
| `obj.model_dump_json()` | `ta.dump_json(obj)` |
| `Model.model_json_schema()` | `ta.json_schema()` |

### 11.5 Auch TypedDict und dataclass lassen sich validieren

```python
from typing_extensions import TypedDict   # Unter Python < 3.12 zwingend erforderlich
from dataclasses import dataclass


class TD(TypedDict):
    a: int
    b: str


print(TypeAdapter(TD).validate_python({"a": "1", "b": "x"}))


@dataclass
class DC:
    a: int


print(TypeAdapter(DC).validate_python({"a": "9"}))
```

```text
{'a': 1, 'b': 'x'}
DC(a=9)
```

> ⚠️ **Fallstrick**: Unter Python 3.11 und älter müssen Sie zwingend `typing_extensions.TypedDict` verwenden; mit `typing.TypedDict` aus der Standardbibliothek gibt es unmittelbar eine Fehlermeldung:
>
> ```text
> pydantic.errors.PydanticUserError: Please use `typing_extensions.TypedDict`
> instead of `typing.TypedDict` on Python < 3.12.
> ```
>
> Das ist in der Praxis so aufgetreten; die Fehlermeldung selbst ist sehr klar formuliert, man muss ihr nur folgen.

> 👉 **CEO-Perspektive**: Die bloße Existenz von `TypeAdapter` verdeutlicht einen Grundgedanken von Pydantic – **die Validierungsfähigkeit ist davon entkoppelt, ob man eine Tabelle anlegt oder nicht**.
>
> Übertragen aufs Produkt: Sie müssen keine „Handynummern-Tabelle" anlegen, nur um „einen Stapel Handynummern auf Gültigkeit zu prüfen". **Validierungsregeln sollten unabhängig von der Datenstruktur wiederverwendbar sein.** In realen Projekten sind die häufigsten Einsatzfelder von `TypeAdapter`: Massenimporte (Validierung einer ganzen Liste), das Einlesen von Konfigurationsdateien (Validierung eines Dictionarys) und die Validierung der Ausgabe eines LLM (manchmal liefert das Modell eben ein Array und kein Objekt zurück).
>
> Dem letzten Szenario begegnen wir später in diesem Buch noch: Wenn Sie das Modell „alle erwähnten Produkte extrahieren" lassen, ist die Rückgabe naturgemäß eine Liste – und dann kommt genau `TypeAdapter(list[Product])` zum Einsatz.

---
## 12. Liste häufiger Fallstricke

Alle Fallstricke des gesamten Textes an einer Stelle gebündelt – so können Sie später schnell nachschlagen.

| # | Fallstrick | Symptom | Richtiges Vorgehen | Abschnitt |
|---|---|---|---|---|
| 1 | In Unterlagen stoßen Sie auf die API von V1 | `parse_obj` / `@validator` meldet einen Fehler oder gilt als veraltet | Auf V2 achten: `model_validate` / `@field_validator` | 0 |
| 2 | Zuweisungen werden standardmäßig nicht validiert | Nach dem Anlegen lassen sich Attribute beliebig ändern, ohne dass ein Fehler kommt | `ConfigDict(validate_assignment=True)` | 2.6 |
| 3 | `x: int = Field(...)` wird für optional gehalten | Dauerhaft die Meldung `missing` | Ohne `default=` ist das Feld Pflicht; alternativ die Annotated-Form nutzen | 3.6 |
| 4 | Veränderliche Standardwerte | Mehrere Instanzen teilen sich dieselbe Liste | `Field(default_factory=list)` | 3.5 |
| 5 | Nach dem Setzen eines Alias wird der ursprüngliche Name nicht mehr akzeptiert | Übergabe unter dem ursprünglichen Namen meldet `missing` | `populate_by_name=True` (ab 2.11 empfohlen: `validate_by_name=True`) | 3.9 |
| 6 | `Optional` ≠ optional | `x: str \| None` ist weiterhin Pflicht | Für optional muss `= None` dabeistehen | 4.2 |
| 7 | Enum kommt beim Dump als Objekt statt als Zeichenkette heraus | `json.dumps` meldet einen Fehler | `mode="json"` oder `use_enum_values=True` | 4.4 |
| 8 | Beträge als `float` | Beim Aufsummieren erscheint 0.30000000000000004 | `Decimal` verwenden | 4.1 |
| 9 | Boolesche Spalte erkennt „是/Y" nicht | Excel-Import scheitert auf breiter Front | Im PRD klar festlegen, welche Schreibweisen die boolesche Spalte akzeptiert | 4.1 |
| 10 | Im Validator das `return` vergessen | Das Feld wird zu `None` | Den Wert unbedingt zurückgeben | 5.1 |
| 11 | Im Validator sind Bereinigung und Prüfung vertauscht | Kleingeschriebene Eingaben werden fälschlich abgelehnt | Erst normalisieren, dann prüfen | 5.1 |
| 12 | `model_validator(before)` setzt voraus, dass immer ein dict ankommt | Sporadische Abstürze | Zuerst `isinstance(data, dict)` prüfen | 5.7 |
| 13 | `model_dump()` direkt an `json.dumps` weiterreichen | `datetime` ist nicht serialisierbar | `mode="json"` oder `model_dump_json()` | 6.1 |
| 14 | Vererbung + Deklaration mit dem Elterntyp lässt Felder verschwinden | Felder gehen stillschweigend verloren – am schwersten zu finden | Diskriminierte Union verwenden; als Notlösung `serialize_as_any=True` | 6.5 |
| 15 | Unbekannte Felder werden stillschweigend verworfen | Selbst ein Tippfehler im Feldnamen löst keinen Fehler aus | Für interne Schnittstellen `extra="forbid"` aktivieren | 6.6 |
| 16 | Geschäftsregeln aus `model_validator` landen nicht im Schema | Das LLM sieht diese Regel nicht | In `description` schreiben + nachgelagerte Validierung mit Retry | 7.9 |
| 17 | Der Fehlerbericht spiegelt sensible Eingaben zurück | Passwörter landen im Log | `errors(include_input=False)` | 9.6 |
| 18 | Standardwerte werden nicht validiert | Regelwidrige Standardwerte rutschen durch | `validate_default=True` | 10.7 |
| 19 | Fehlermeldungen gewöhnlicher Unions sind schwer lesbar | Die Fehler sämtlicher Zweige werden allesamt gemeldet | Diskriminator ergänzen | 8.2 |
| 20 | Unter Python < 3.12 `typing.TypedDict` verwenden | Direkt ein PydanticUserError | `typing_extensions.TypedDict` verwenden | 11.5 |
| 21 | `deprecated` hängt an einem einzelnen Zweig der Union | Bleibt wirkungslos, es gibt nur eine Warnung | Auf der äußersten Ebene ansetzen: `Annotated[int \| None, Field(...)]` | 3.7 |

---

## 13. Kurzreferenz

### 13.1 Häufig genutzte APIs

| Ich möchte … | Schreibweise |
|---|---|
| eine Tabelle definieren | `class X(BaseModel):` |
| aus einem dict validieren | `X.model_validate(d)` |
| aus einer JSON-Zeichenkette validieren | `X.model_validate_json(s)` |
| in ein dict umwandeln | `x.model_dump()` |
| in ein JSON-fähiges dict umwandeln | `x.model_dump(mode="json")` |
| in eine JSON-Zeichenkette umwandeln | `x.model_dump_json(indent=2)` |
| die Spezifikation erzeugen | `X.model_json_schema()` |
| kopieren und einzelne Werte ändern | `x.model_copy(update={...})` |
| sehen, welche Felder es gibt | `X.model_fields` |
| sehen, welche berechneten Felder es gibt | `X.model_computed_fields` |
| Nicht-Modell-Typen validieren | `TypeAdapter(list[int]).validate_python(v)` |

### 13.2 Gegenüberstellung: vom PRD zum Code

| Im PRD steht | In Pydantic steht |
|---|---|
| Pflicht | keinen Standardwert angeben |
| optional | `= None` oder `= Standardwert` |
| Pflicht, darf aber leer sein | `x: str \| None` (ohne Standardwert) |
| Text, 2–20 Zeichen | `Field(min_length=2, max_length=20)` |
| Zahl, größer als 0 | `Field(gt=0)` |
| Zahl, 0–100 | `Field(ge=0, le=100)` |
| Auswahlliste: A/B/C | `Literal["A","B","C"]` |
| Format einer Mobilnummer | `Field(pattern=r"^1\d{10}$")` |
| Betrag | `Decimal` + `Field(gt=0)` |
| Datum | `date` |
| Positionsliste, höchstens 20 Einträge | `list[Item] = Field(max_length=20)` |
| Tags, ohne Dubletten | `set[str]` |
| Untertabelle / verschachteltes Objekt | ein weiteres `BaseModel` |
| vom System automatisch erzeugt | `Field(default_factory=...)` |
| vom System berechnet | `@computed_field` |
| Felderläuterung | `Field(description="……")` |
| interner und externer Feldname unterschiedlich | `Field(alias="外部名")` |
| Geschäftsregel für ein einzelnes Feld | `@field_validator` |
| feldübergreifende Regel | `@model_validator(mode="after")` |
| ab einem Schwellenwert in die Freigabe | `@model_validator(mode="after")` – erst rechnen, dann prüfen |
| Feldgruppe B erscheint nur bei Auswahl A | diskriminierte Union `Field(discriminator="type")` |
| zusätzliche Felder nicht erlaubt | `ConfigDict(extra="forbid")` |
| nach dem Anlegen unveränderlich | `ConfigDict(frozen=True)` |
| Eingaben automatisch von Leerzeichen befreien | `ConfigDict(str_strip_whitespace=True)` |

### 13.3 Das ganze Kapitel in drei Grafiken

**Datenfluss**:

```text
外部数据 ──▶ [before 校验器] ──▶ [类型转换 + Field 约束] ──▶ [after 校验器]
                                                                  │
                                                                  ▼
                                                          合法的模型对象
                                                                  │
                        ┌─────────────────────────────────────────┼─────────────────────┐
                        ▼                                         ▼                     ▼
                  model_dump()                            model_dump_json()    model_json_schema()
                   给 Python                                  给接口              给文档/前端/大模型 ★
```

**Woraus eine Tabelle besteht**:

```text
class Order(BaseModel):
    model_config = ConfigDict(...)          ← 整表开关（第 10 章）

    price: float = Field(gt=0, ...)         ← 类型（第 4 章）+ 约束和说明（第 3 章）
    channel: Annotated[A|B, Field(
        discriminator="type")]              ← 分支字段（第 8 章）

    @field_validator("price")               ← 单字段规则（5.1）
    @model_validator(mode="after")          ← 跨字段规则、先算再判（5.5、5.6）
    @computed_field                         ← 计算字段（6.3）
    @field_serializer("price")              ← 导出格式（6.4）
```

**Welche Parameter einen CEO interessieren sollten**:

```text
优先级最高 ★★★   Field(description=...)     决定 AI 填得对不对、文档写得清不清楚
优先级高   ★★     Literal / Enum             决定枚举值全链路一致
优先级高   ★★     必填 / 选填 / 可为空        三者含义不同，评审时要说清
优先级高   ★★     gt / ge、lt / le           边界值，测试用例最容易出问题的地方
优先级中   ★       extra 策略                 对内 forbid、对外 ignore
优先级中   ★       computed_field            区分「用户填」和「系统算」
```

---

## 14. Fazit: Was Sie aus diesem Teil mitnehmen sollten

Wenn Sie sich nur drei Sätze merken:

1. **Pydantic ist die Bibliothek, die „die Feldregel-Tabelle aus dem PRD in ausführbaren Code verwandelt".** Sie steht am Eingang des Systems, lässt nur regelkonforme Daten passieren und meldet sämtliche Fehler auf einen Schlag.

2. **`model_json_schema()` ist ihre am meisten unterschätzte Fähigkeit.** Die Tabelle, die Sie entworfen haben, wird automatisch zu einer maschinenlesbaren Spezifikation und versorgt zugleich die API-Dokumentation, das Frontend-Formular und das LLM. Das ist der Mechanismus, auf dem die strukturierte Ausgabe von Pydantic AI im weiteren Verlauf dieses Buches aufsetzt.

3. **`Field(description=...)` ist der größte Hebel, den ein CEO in KI-Projekten hat.** Es ist kein Kommentar mehr, sondern Teil des Prompts und entscheidet unmittelbar darüber, ob das Modell richtig ausfüllt.

Im nächsten Teil sehen wir: Wie Pydantic AI, sobald Sie ihm diese Modelle übergeben, das LLM dazu bringt, entlang der von Ihnen definierten Tabelle stabil strukturierte Ergebnisse zu liefern.
