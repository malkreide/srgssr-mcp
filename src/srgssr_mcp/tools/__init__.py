"""SRG SSR MCP tools, resources and prompts.

Importing this package executes the @mcp.tool/@mcp.resource/@mcp.prompt
decorators on the shared :data:`srgssr_mcp._app.mcp` instance, so listing
or calling primitives through that instance reflects everything below.

**Was `ctx` hier darf und was nicht.** Jedes Tool nimmt weiterhin ein
optionales ``ctx: Context | None`` — das ist die Einspritzstelle des SDK und
die Bedingung dafuer, dass ein Tool ueberhaupt etwas an den Client melden
kann. Benutzt wird davon genau eine Sache: ``ctx.report_progress`` in
``srgssr_daily_briefing``, wo zwei Quellen parallel laufen.

Die Logging-Haelfte ist weg, und zwar aus drei Gruenden, die einzeln schon
reichen wuerden:

1. **Sie lief nicht.** ``ctx.info("... invoked", business_unit=bu)`` ist die
   Signatur von FastMCP 1.x. Auf ``mcp`` 2.x heisst sie
   ``info(data, *, logger_name=None)`` und nimmt keine freien Schluesselwoerter
   mehr; jeder dieser 14 Aufrufe endete in
   ``TypeError: Context.info() got an unexpected keyword argument`` und damit
   in einem ``isError``-Resultat. Gemessen am 17.9.2026 ueber die ASGI-App,
   siehe ``tests/test_spec_2026_07_28.py``.
2. **Spec 2026-07-28 setzt die Logging-Capability ab (SEP-2577).** Das SDK
   markiert ``Context.log`` und die vier Bequemlichkeits-Methoden darum als
   deprecated. Ab dieser Revision ist die Zustellung ausserdem ein Opt-in pro
   Anfrage (``io.modelcontextprotocol/logLevel`` im ``_meta``); fehlt der
   Schluessel, **darf** der Server nicht senden. Eine native Umsetzung baut
   nicht auf einem Kanal, den die Zielrevision gerade zurueckzieht.
3. **Der Server hat die Capability nie deklariert.** Gemessen im
   Handshake: ``capabilities`` traegt ``prompts``, ``resources``, ``tools``
   und ``experimental`` — kein ``logging``. Ein ``notifications/message``
   ohne deklarierte Capability haette auch in der alten Aera nicht gesendet
   werden duerfen.

Verloren geht dabei nichts: jedes Tool bindet seine Felder direkt davor an
structlog (``log = logger.bind(...)``; ``log.info("tool_invoked")``), also auf
dem Kanal, den der Betreiber liest. ``ctx.info`` war eine zweite Kopie
derselben Zeile auf einem Kanal, der beim Empfaenger nie ankam.

Warum das trotz gruener Suite einen Monat lag: Audit-Finding SDK-003 hat die
Aufrufe eingefuehrt und als Nachweis einen grep vorgeschlagen
(«``await ctx.(info|report_progress)`` muss min. 15 Treffer liefern»). Ein
grep kann eine Signatur nicht aufrufen. Der einzige Test, der ueberhaupt ein
``ctx`` durchgab, brachte sein eigenes ``_StubCtx`` mit — mit ``**extra`` in
der Signatur, also genau der Annahme, die zu widerlegen war. Im
Coverage-Bericht standen die 14 Zeilen die ganze Zeit als nicht ausgefuehrt.

**Der Anzeigename steht jetzt in `title`, nicht nur in `annotations`.** Alle
15 Tools trugen ihn ausschliesslich als ``annotations={"title": ...}``. Das
ist in Spec 2026-07-28 die falsche Stelle: ``ToolAnnotations`` ist dort
ausdruecklich als Satz von *Hinweisen* beschrieben, «including descriptive
properties like `title`», mit dem Zusatz, Clients sollten auf Annotationen
eines nicht vertrauenswuerdigen Servers keine Entscheidung stuetzen. Der
Anzeigename gehoert in ``title`` aus ``BaseMetadata`` — dasselbe Feld, das
Resources und Prompts in diesem Repo laengst benutzen. Gemessen ging
``tools/list`` ohne ``title`` hinaus, waehrend ``prompts/list`` und
``resources/templates/list`` eines trugen; ein Client, der sich an die Spec
haelt, zeigte fuer Tools also ``srgssr_epg_get_programs`` und fuer Prompts
den Klartext.

``annotations["title"]`` bleibt daneben stehen, gleichlautend: Clients auf
2025-06-18 und aelter lesen nur dort. Das ist der einzige Grund — faellt die
Handshake-Aera eines Tages weg, faellt die Kopie mit ihr.
"""

from srgssr_mcp.tools import (  # noqa: F401  (import for side-effect: registration)
    aggregation,
    audio,
    epg,
    polis,
    prompts,
    resources,
    video,
    weather,
)
