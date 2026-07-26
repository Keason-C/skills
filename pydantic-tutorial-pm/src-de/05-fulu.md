## Anhang A: Schnellübersicht der Änderungen v1 → v2

Dieser Anhang ist aus der offiziellen `docs/changelog.md` zusammengestellt (der Titel der Datei lautet tatsächlich *Upgrade Guide*). **Die finale Version v2.0 wurde am 23.06.2026 veröffentlicht.**

Wozu diese Tabelle dient: **Wenn Sie ein Stück Pydantic-AI-Code sehen und beurteilen wollen, ob es neu oder alt ist, schlagen Sie hier nach.** Was in der linken Spalte steht, ist v1-Schreibweise; rechts steht die korrekte v2-Schreibweise.

### A.1 Die Leitlinie des Designs: Konfiguration konvergiert auf „Capability-Karten"

Die offizielle Einordnung von v2 im Originalwortlaut:

> "V2 leans into a **harness-first design** with capabilities as a core primitive: a single, composable unit that bundles an agent's tools, hooks, instructions, and model settings, reaching every layer of the agent through one concept."

Übersetzt: **Sehr viele Einstellungen, die ursprünglich über die `Agent(...)`-Parameter verstreut waren, sind einheitlich in `capabilities=[...]` zusammengeführt worden.** Das ist das erste Prinzip, aus dem sich alle Änderungen in v2 verstehen lassen.

| v1-Schreibweise | v2-Schreibweise |
|---|---|
| `Agent(instrument=...)` | `capabilities=[Instrumentation(...)]` |
| `Agent(prepare_tools=...)` | `capabilities=[PrepareTools(...)]` |
| `Agent(history_processors=...)` | `capabilities=[ProcessHistory(...)]` |
| `Agent(event_stream_handler=...)` | `capabilities=[ProcessEventStream(...)]` |
| `Agent(builtin_tools=[...])` | `capabilities=[NativeTool(...)]` |
| `Agent(mcp_servers=[...])` | `Agent(toolsets=[...])` |

> 👉 **CEO-Perspektive**: Der Trick, um Code auf einen Blick als neu oder alt einzuordnen – **schauen Sie, ob `capabilities=[...]` vorkommt**. Wenn ja, ist es im Grunde v2; wenn die ganze Konfiguration in den `Agent()`-Parametern liegt, ist es im Grunde v1.

### A.2 Verhaltensänderungen, die „stillschweigend umschlagen" (am gefährlichsten: kein Fehler, aber geändertes Verhalten)

| Änderung | Auswirkung | Schreibweise zur Wiederherstellung des v1-Verhaltens |
|---|---|---|
| Nacktes Präfix `openai:` läuft jetzt über die **Responses API** | Der API-Kanal hat gewechselt | `openai-chat:` schreiben |
| `WebSearch`/`WebFetch` werden **native-only** | Unterstützt das Modell es nicht, wird direkt ein Fehler geworfen | `WebSearch(local='duckduckgo')`, `WebFetch(local=True)` |
| `MCP(url=...)` läuft standardmäßig **lokal** | Der Ausführungsort hat sich geändert | `MCP(url=..., native=True)` |
| `end_strategy` standardmäßig `'early'` → **`'graceful'`** | Tools, die das Modell in derselben Runde aufruft, in der es das Ergebnis zurückgibt, **werden jetzt tatsächlich ausgeführt** (samt Seiteneffekten) | Explizit `end_strategy='early'` setzen |

> ⚠️ **Fallstrick**: Bei `end_strategy` geht am ehesten etwas schief. Gab das Modell in v1 gleichzeitig „endgültige Antwort" und „Tool-Aufruf" zurück, wurde das Tool übersprungen; **in v2 wird das Tool wirklich ausgeführt**. Hat dieses Tool Seiteneffekte (Nachricht versenden, Geld abbuchen, in die Datenbank schreiben), ist der Verhaltensunterschied substanziell. Beim Upgrade müssen alle Tools mit Seiteneffekten einzeln reviewt werden.

### A.3 Gegenüberstellung von Umbenennungen und Entfernungen

**Modelle und Anbieter**

| v1 | v2 |
|---|---|
| `grok:`-Präfix / `GrokProvider` | `xai:` / `XaiProvider` + `XaiModel` |
| `google-gla:` / `google-vertex:` / `vertexai:` | `google:` / `google-cloud:` |
| `GoogleGLAProvider` / `GoogleVertexProvider` / das gesamte `models.gemini` | `GoogleProvider` / `GoogleCloudProvider` + `GoogleModel` |
| `OpenAIModel` / `OpenAIModelSettings` | `OpenAIChatModel` / `OpenAIChatModelSettings` |
| `Agent('gpt-5')` (ohne Präfix) | **wirft `UserError`**, es muss `Agent('openai:gpt-5')` heißen |

**Rund um Tools**

| v1 | v2 |
|---|---|
| `pydantic_ai.builtin_tools` | **`pydantic_ai.native_tools`** |
| `BuiltinToolCallPart` / `BuiltinToolReturnPart` / `AgentBuiltinTool` | `NativeToolCallPart` / `NativeToolReturnPart` / `AgentNativeTool` |
| `MCPServerStdio` / `SSE` / `StreamableHTTP` / `HTTP` / `FastMCPToolset` | `mcp.MCPToolset` / `mcp.load_mcp_toolsets` |
| `Agent.run_mcp_servers()` | `async with agent:` |
| `output.DeferredToolCalls` | `DeferredToolRequests` |
| `toolsets.external.DeferredToolset` | `ExternalToolset` |
| `native_tools.UrlContextTool` | `native_tools.WebFetchTool` |
| `Agent.sequential_tool_calls()` | `agent.parallel_tool_call_execution_mode('sequential')` |

**Verbrauch und Ergebnisse**

| v1 | v2 |
|---|---|
| `request_tokens` / `response_tokens` | `input_tokens` / `output_tokens` |
| `Usage` | `RunUsage` |
| `UsageLimits(request_tokens_limit=, response_tokens_limit=)` | `UsageLimits(input_tokens_limit=, output_tokens_limit=)` |
| `result.usage()` / `result.timestamp()` (Methoden) | `result.usage` / `result.timestamp` (**Attribute**) |
| `stream.get()` | `stream.response` |
| `ModelResponse.vendor_details` | `provider_details` |
| `vendor_id` / `provider_request_id` | `provider_response_id` |
| `FunctionToolCallEvent.call_id` | `.tool_call_id` |

**Streaming**

| v1 | v2 |
|---|---|
| `StreamedRunResult.stream` | `stream_output` |
| `.stream_structured` | `stream_response` |
| `.validate_structured_output` | `validate_response_output` |
| `stream_responses()` (Plural) | `stream_response()` (Singular) |

**Graph**

| v1 | v2 |
|---|---|
| das gesamte Paket `pydantic_graph.persistence` | **entfernt, kein Äquivalent** |
| `pydantic_graph.mermaid` / `graph.mermaid_code()` | `Graph.render()` |
| `from pydantic_graph.beta import ...` | `from pydantic_graph import GraphBuilder` (auf die oberste Ebene gehoben) |

**Weitere Entfernungen**

| Entfernt | Ersatzlösung |
|---|---|
| `Agent.to_a2a()` + eingebautes fasta2a | `fasta2a[pydantic-ai]>=0.6.1` installieren, `agent_to_a2a` verwenden |
| `Agent.to_ag_ui()` / `AGUIApp` / `pydantic_ai.ag_ui` | `pydantic_ai.ui.ag_ui.AGUIAdapter` |
| `pydantic_ai.ext.aci` | kein Ersatz, mit `Tool.from_schema` selbst umhüllen |
| Outlines-Integration (`models.outlines` usw.) | entfernt |
| `models.cached_async_http_client` | `models.create_async_http_client()` |

### A.4 Weitere zu beachtende Änderungen bei Standardwerten

- **Die Extras der nackten Installation `pip install pydantic-ai` sind schlanker geworden**: `bedrock` / `groq` / `mistral` sind **nicht mehr standardmäßig enthalten**, wer sie braucht, muss sie explizit installieren.
- **Standard-Instrumentierungsversion → 5**: Der Token-Verbrauch der Run-Span wird jetzt unter `gen_ai.aggregated_usage.*` gemeldet.
- **Standardparameter der Generics `None` → `object`**: Ein nacktes `Agent(...)` wird jetzt als `Agent[object, str]` inferiert. **Betrifft nur die Typprüfung, zur Laufzeit ändert sich nichts.**
- **`ModelProfile` von dataclass zu `TypedDict` geändert**: Die Übergabe von Parametern bleibt gleich, betroffen ist nur das Lesen/Schreiben von Feldern bzw. der Aufruf von `.update()`.
- **Prepare-Callbacks, die `None` zurückgeben, werfen jetzt `TypeError`**: Wer ausdrücken will „in dieser Runde keine Tools", muss `[]` zurückgeben, nicht `None`.
- **`FunctionToolset.tool()` meldet jetzt einen Fehler, wenn der erste Parameter kein `RunContext` ist**: Ohne Context muss `tool_plain()` verwendet werden.

### A.5 Der offiziell empfohlene Upgrade-Pfad

Offiziell wird ein Vorgehen in drei Schritten empfohlen:

1. **Zuerst auf die neueste V1 aktualisieren** (≥ v1.100.0); dabei treten sämtliche Deprecation-Warnungen zutage
2. **Alle Warnungen Punkt für Punkt beseitigen**
3. **Dann auf V2 aktualisieren**; übrig bleiben nur die Verhaltensänderungen, die von keiner Warnung abgedeckt sind und manuell beurteilt werden müssen

Kompatibilitätszusage: Ein mit `ModelMessagesTypeAdapter` unter V1 serialisierter Nachrichtenverlauf lässt sich unter V2 weiterhin deserialisieren.

> 👉 **CEO-Perspektive**: Diesen Pfad „erst die Warnungen abräumen, dann upgraden" sollten Sie sich merken – **er zerlegt eine risikoreiche Großmigration in einen Haufen kleiner Änderungen mit klaren Hinweisen**. Wenn Sie künftig den Aufwand für ein Major-Upgrade einschätzen müssen, ist das ein übertragbarer Denkansatz: Fragen Sie die Entwickler zuerst, „gibt es eine Zwischenversion, die die Probleme vorab sichtbar macht?".

---

## Anhang B: Schnellübersicht häufiger Fallstricke

Nach Häufigkeit sortiert; alle sind entweder in der offiziellen Dokumentation ausdrücklich vermerkt oder im Test selbst erlebt worden.

### B.1 Die Pydantic-Ebene

| Fallstrick | Beschreibung | Richtiges Vorgehen |
|---|---|---|
| **Serialisierung von Subklassen verliert Felder** | Pydantic serialisiert nach dem **deklarierten Typ**, nicht nach dem Laufzeittyp. Ist ein Feld als `Base` deklariert und steckt eine `Sub1`-Instanz darin, gibt `model_dump()` nur die Felder von `Base` aus | Discriminated Union oder Generics verwenden |
| **`Annotated` an der falschen Stelle** | `Annotated[int, Field(deprecated=True)] \| None` – Metadaten auf Feldebene müssen sich auf die gesamte Union beziehen | Als `Annotated[int \| None, Field(deprecated=True)]` schreiben |
| **Missbrauch der Union `int \| str`** | Wenn es nur darum geht, „einen String in eine Zahl umzuwandeln", ist die Union falsch – Pydantic konvertiert standardmäßig ohnehin automatisch | Einfach `int` schreiben, es akzeptiert `'123'` |
| **Abstrakte Sammlungstypen verwenden** | `Sequence[str]` nur, um „list und tuple gleichzeitig zu akzeptieren", ist ineffizient | Einfach `list[str]` schreiben, es akzeptiert tuple ohnehin |
| **Validator schreiben, wo eine eingebaute Beschränkung genügt** | Eigene Validatoren sind langsamer und umständlicher als eingebaute Beschränkungen | Bevorzugt `Field(gt=1)` / `annotated_types.Gt(1)` |

### B.2 Die Pydantic-AI-Ebene

| Fallstrick | Beschreibung |
|---|---|
| **`@agent.tool` braucht zwingend `ctx`, `@agent.tool_plain` darf es keinesfalls haben** | Wer das vertauscht, bekommt direkt einen Laufzeitfehler |
| **Der Modell-String muss das Anbieter-Präfix enthalten** | `'openai:gpt-5.2'` ✅ ／ `'gpt-5.2'` ❌ wirft `UserError` |
| **Ein `str` im `output_type` ist eine offene Hintertür** | Enthält die Union ein `str`, kann das Modell wählen, „das Formular nicht auszufüllen und stattdessen mit einem Satz Klartext davonzukommen". Wer das Ausfüllen erzwingen will, mischt kein `str` bei |
| **`TestModel` muss mit `agent.override()` kombiniert werden** | Ändern Sie nicht direkt `agent.model`; verwenden Sie `with agent.override(model=TestModel()):` |
| **Tools mit `native=True` umgehen CodeMode** | Native Tools laufen serverseitig, das `run_code` in der Sandbox bekommt sie gar nicht zu sehen |
| **Die Sandbox reguliert Code, nicht Tool-Rechte** | Die Sandbox von CodeMode beschränkt nur „das von der KI geschriebene Skript"; die im Skript aufgerufenen Tools **behalten weiterhin ihre vollen ursprünglichen Rechte**. Gefährliche Tools müssen selbst eine Validierung bekommen |
| 🔴 **`protected_patterns` von `FileSystem` blockiert nur Schreiben, nicht Lesen** | Der Name "protected" verleitet leicht zu der Annahme „vollständig abgeschirmt", tatsächlich ist es **nur schreibgeschützt**. Legen Sie `.env` in `protected_patterns`, kann die KI die darin enthaltenen Schlüssel trotzdem auslesen und in den Modellkontext befördern. **Für echte Abschirmung muss `denied_patterns` verwendet werden.** (Getestet: unter `protected` las die KI `API_KEY=sk-...` aus; unter `denied` kam die Meldung `Path '.env' is denied by pattern '.env'.`) |
| **Bei `Shell` mit Whitelist muss die Blacklist explizit geleert werden** | Intuitiv sollte `Shell(cwd=..., allowed_commands=['ls'])` genügen, aber es wirft **beim Laden der Tools durch den Agent** (nicht bei der Konstruktion) ein `ValueError: Specify allowed_commands or denied_commands, not both.` – denn `denied_commands` bringt eine eigene Standard-Blacklist mit, es sind also „beide angegeben". Korrekte Schreibweise: `Shell(cwd=..., allowed_commands=['ls'], denied_commands=[])` (getestet: nur allowed ❌／allowed + leeres denied ✅／allowed + nicht leeres denied ❌) |
| **Ein nacktes `async for node in agent_run` löst keine Node-Hooks aus** | Damit Hooks einer Capability wie `before_node_run` ausgelöst werden, muss `agent_run.next(node)` oder direkt `agent.run()` verwendet werden |

### B.3 Die Pydantic-Graph-Ebene

| Fallstrick | Beschreibung |
|---|---|
| **Die meisten Tutorials im Netz sind veraltet** | 2.17 ist die auf Builder-Architektur neu geschriebene Version; `Graph(nodes=[...])`, `mermaid_code()` und `persistence` existieren nicht mehr |
| **`run_sync` darf nicht in einer async-Umgebung aufgerufen werden** | Intern läuft es über `loop.run_until_complete` und fliegt auf die Nase, wenn bereits ein Event-Loop existiert. In async `await graph.run()` verwenden |
| **Sämtliche Parameter von `Graph.run()` sind keyword-only** | Es muss `graph.run(inputs=..., state=..., deps=...)` heißen, positionale Übergabe ist nicht möglich |
| **Die Zweigreihenfolge bei `.broadcast()` ist unbestimmt** | Echte parallele Ausführung, die Reihenfolge der Ergebnisse ist nicht garantiert. Wer auf die Reihenfolge angewiesen ist, verzichtet auf broadcast |
| **Diese Version kennt keine Persistenz** | Für Unterbrechen und Fortsetzen muss man sich auf Basis von `iter()` + `override_next()` selbst etwas bauen |

### B.4 Die Ebene von Versionen und Dokumentation

| Fallstrick | Beschreibung |
|---|---|
| **Die Versionsnummer des Skills ≠ die Version der Bibliothek** | Das offiziell mit dem Paket ausgelieferte Lern-Skill trägt `1.1.1`, das ist **die Versionsnummer des Dokuments selbst**; die Bibliothek steht bei 2.17.0 |
| **Im offiziellen Skill stecken noch v1-Formulierungen** | Es erwähnt, `history_processors` "will be removed in v2", tatsächlich ist dieser Parameter in v2.17 **bereits verschwunden**. Maßgeblich ist die tatsächliche Signatur |
| **Ein über `marketplace` installiertes Plugin aktualisiert den Inhalt nicht** | Das Plugin-Paket `ai@pydantic-skills` enthält dasselbe Skill in derselben Version; die Installation bringt keine Aktualisierung |
| **Harness ist Alpha** | 0.10.0, auf PyPI als Development Status 3 gekennzeichnet, offiziell heißt es ausdrücklich: **schon Minor-Releases im 0.x-Bereich können Breaking Changes enthalten** |

> 👉 **CEO-Perspektive**: Die letzte Zeile verdient eine eigene Erwähnung. **Harness stammt zwar aus offizieller Hand und ist funktional sehr umfassend, befindet sich aber erklärtermaßen in einem frühen Stadium** – und genau die Fähigkeiten, die „einen Coding-Agent wirklich stabil machen" (automatische Verifikationsschleifen, Zugriffskontrolle, Freigabeprozesse, Deadlock-Schutz), sind in der offiziellen README **größtenteils noch mit 🚧 im Bau markiert**. Die Einordnung sollte daher lauten: **Für Prototypen und interne Tools kein Problem; für Kernsysteme in Produktion muss man API-Schwankungen in Kauf nehmen und selbst nachhärten.** Dieses Risiko muss bei der Aufwandsschätzung klar benannt werden.

---

## Anhang C: Die Schnellübersicht auf einer Seite

### C.1 Die drei Bibliotheken in je einem Satz

| Bibliothek | In einem Satz | Kernobjekt |
|---|---|---|
| `pydantic` | Eine Tabelle mit Validierungsregeln | `BaseModel` |
| `pydantic-ai` | Die Tabelle als Vertrag an das LLM reichen | `Agent` + `capabilities` |
| `pydantic-graph` | Den Ablauf explizit als Graph zeichnen | `GraphBuilder` → `Graph` |

### C.2 Das Agent-Set (beim Bauen eines Agents immer mitzudenken)

```python
agent = Agent(
    'anthropic:claude-sonnet-4-6',   # ① Welches Gehirn (Anbieter:Modell, Präfix ist Pflicht)
    name='my_agent',                 # ② Wie es heißt (für Observability)
    instructions='...',              # ③ Welche Regeln gelten (Rolle/Verhaltenskodex)
    output_type=MyModel,             # ④ In welchem Format geliefert wird (der Knackpunkt)
    deps_type=MyDeps,                # ⑤ Welche privaten Daten benötigt werden
    capabilities=[...],              # ⑥ Welche Capability-Karten gesteckt werden
)
```

### C.3 Vier „Kontrollpunkte", an denen validiert werden kann

| Kontrollpunkt | Wessen Daten | Womit | Wer korrigiert im Fehlerfall |
|---|---|---|---|
| Eingabeparameter | Mensch/System | `Field` / `model_validator` | Der Mensch |
| Tool-Parameter | LLM | Typen / `args_validator` | **Die KI selbst** (`ModelRetry`) |
| Ausgabe | LLM | `output_type` | **Die KI selbst** (Framework wiederholt automatisch) |
| Ein- und ausgehende Inhalte | Beide Richtungen | `guardrails` | Abfangen/maskieren/zurückweisen |

### C.4 Entscheidungsbaum für die Technologiewahl

```text
Soll die KI-Ausgabe direkt ins System laufen können?
  └─ Ja → mit output_type ein BaseModel definieren

Soll die KI selbst tätig werden (Daten abfragen, APIs aufrufen)?
  └─ Ja → Tools hinzufügen
       └─ Braucht das Tool den aktuellen Nutzer/Schlüssel? → @agent.tool + deps
       └─ Keinerlei private Informationen nötig?           → @agent.tool_plain

Sollen verschiedene Nutzer verschiedene Fähigkeiten bekommen?
  └─ Ja → DynamicCapability + ctx.deps für dynamische Zuteilung

Hat der Ablauf mehrere Schritte, Parallelität, Verzweigungen?
  └─ Einfach sequenziell     → die Agent-Schleife genügt
  └─ Komplexe Orchestrierung → Pydantic Graph einsetzen

Soll die KI Dateien/die Kommandozeile bedienen?
  └─ Nur Dateien lesen/schreiben → harness FileSystem
  └─ Befehle ausführen           → harness Shell (mit Whitelist)
  └─ Riskante/unsichere Aktionen → harness ModalSandbox (einmalige Cloud-Umgebung)
```

---

## Schlusswort

Wenn dieses Buch Sie nur drei Sätze behalten lässt, dann hoffentlich diese drei:

**Erstens: Die Kernphilosophie des Pydantic-Stacks lautet „Vertrag zuerst".** Sie deklarieren zuerst, „was als gültig gilt", und das Framework hält Nicht-Konformes schon in dem Moment ab, in dem die Daten zur Tür hereinkommen – statt erst nach dem Problem aufzuräumen. Das ist dasselbe, wie wenn Sie im PRD die Abnahmekriterien festlegen.

**Zweitens: Der Kern von v2 sind die „Capability-Karten".** Jede höherwertige Fähigkeit, die Sie einem Agent geben – Websuche, Nachdenken, Gedächtnis, Telemetrie, Sandbox –, konvergiert auf dieselbe Handlung: eine Karte bauen und in `capabilities=[...]` stecken. Sie müssen sich keine Dutzenden APIs merken, sondern nur: „die passende Karte finden und einstecken".

**Drittens: Fähigkeitsgrenzen müssen vom Framework physisch getrennt werden, nicht durch die Selbstdisziplin von Prompts.** Free-Nutzer sehen das Rückerstattungs-Tool nicht, weil es ihnen schlicht nie zugeteilt wurde; sensible Werte laufen über `deps`, weil das Modell diesen Kanal nicht berühren kann. **„Nicht zeigen" ist immer zuverlässiger als „ermahnen, es nicht zu benutzen".** Dieses Urteil werden Sie beim Rechtekonzept jedes einzelnen KI-Produkts brauchen.

---

*Sämtlicher Code dieses Buches wurde auf pydantic 2.13.4 / pydantic-ai 2.17.0 / pydantic-graph 2.17.0 / pydantic-ai-harness 0.10.0 praktisch getestet und verifiziert.*
