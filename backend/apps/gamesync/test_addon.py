# ruff: noqa: E501 — les chaînes Lua des scénarios sont longues par nature
"""
L'addon Lua tourne hors du jeu grâce à lupa (Lua 5.1, comme le client) et un environnement WoW simulé.
On vérifie que tous les fichiers chargent, qu'une session produit un code d'export que le site décode et importe,
et que les briques pures (JSON, base64, journal) sont justes.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

import pytest
from lupa.lua51 import LuaRuntime

from apps.gamedata.models import Profession, Recipe
from apps.gamedata.seed import seed

from . import services
from .format import decode_export

ADDON_DIR = Path(__file__).resolve().parents[3] / "addon" / "WoWForeverGuilde"
STUB = Path(__file__).with_name("wow_stub.lua")


def toc_files() -> list[str]:
    lines = (ADDON_DIR / "WoWForeverGuilde.toc").read_text(encoding="utf-8").splitlines()
    return [line.strip().replace("\\", "/") for line in lines if line.strip() and not line.startswith("#")]


def toc_version() -> str:
    text = (ADDON_DIR / "WoWForeverGuilde.toc").read_text(encoding="utf-8")
    return re.search(r"^## Version: (.+)$", text, re.M).group(1).strip()


def boot(files: list[str] | None = None) -> LuaRuntime:
    lua = LuaRuntime(unpack_returned_tuples=True, encoding="utf-8")
    lua.execute(STUB.read_text(encoding="utf-8"))
    lua.globals()._ADDON_VERSION = toc_version()
    load = lua.globals()._LOAD
    for rel in files or toc_files():
        if rel.startswith("Libs/HereBeDragons/"):
            continue  # exige la carte du client (C_Map, WorldMapFrame) ; MapUI reçoit un faux module de pins
        load(rel, (ADDON_DIR / rel).read_text(encoding="utf-8"))
    return lua


def login(lua: LuaRuntime) -> None:
    g = lua.globals()
    g._FIRE("ADDON_LOADED", "WoWForeverGuilde")
    g._FIRE("PLAYER_LOGIN")
    g._ADVANCE(5)  # FullScan (3 s) et canal des morts (5 s)
    g._ADVANCE(2)  # lectures regroupées (1 s)


def logout_code(lua: LuaRuntime) -> str:
    g = lua.globals()
    g._FIRE("PLAYER_LOGOUT")
    return g.WoWForeverGuildeDB.export


def addon_sent(g) -> list:
    """Messages addon envoyés, sans la demande de tableau Wanted (« W », 8 s après la connexion)."""
    return [s for s in g._ADDON_SENT.values() if not s.text.startswith("W\t")]


def wanted_sent(g, kind: str) -> list[str]:
    """Textes des messages Wanted envoyés d'un type donné (« K » kill, « W » poignée de main)."""
    return [s.text for s in g._ADDON_SENT.values() if s.text.startswith(kind + "\t")]


class TestLoading:
    def test_every_lua_file_is_listed_in_the_toc_and_loads(self):
        listed = set(toc_files())
        on_disk = {p.relative_to(ADDON_DIR).as_posix() for p in ADDON_DIR.rglob("*.lua")}
        assert on_disk == listed
        lua = boot()
        ns = lua.globals()._NS
        names = sorted(ns.collectors[i].name for i in range(1, len(ns.collectors) + 1))
        assert names == sorted(
            ["identity", "gear", "talents", "professions", "reputation", "attunements", "lockouts", "pvp", "pve", "kills", "gathering", "quests", "deaths", "positions", "wanted", "mapui"]
        )  # fmt: skip
        assert lua.globals().SlashCmdList.WOWFOREVERGUILDE is not None
        # Icône de la guilde (portrait de Samwise, « Temp ») sur les fenêtres et dans la liste des addons.
        assert (ADDON_DIR / "Samwise.blp").read_bytes()[:4] == b"BLP2"
        assert "## IconTexture: Interface\\AddOns\\WoWForeverGuilde\\Samwise" in (
            ADDON_DIR / "WoWForeverGuilde.toc"
        ).read_text(encoding="utf-8")
        login(lua)
        lua.globals().SlashCmdList.WOWFOREVERGUILDE("")
        assert (
            lua.globals().WoWForeverGuildeFrame.icon.texture == "Interface\\AddOns\\WoWForeverGuilde\\Samwise"
        )

    def test_login_registers_events_and_welcomes(self):
        lua = boot()
        login(lua)
        g = lua.globals()
        db = g.WoWForeverGuildeDB
        char = db.characters["Player-1-000ABC01"]
        assert (char.name, char.surname, char.realm, char["class"], char.level) == (
            "Thrall",
            "Fils-de-Durotan",
            "Forever",
            "SHAMAN",
            60,
        )
        assert any("Bienvenue" in m for m in list(g._CHAT.values()))
        # Autre forme vue sur Forever : « Prénom Nom » d'un seul tenant, suivi du royaume.
        joined = boot()
        joined.execute("_NAME_SHAPE = 'joined'")
        login(joined)
        other = joined.globals().WoWForeverGuildeDB.characters["Player-1-000ABC01"]
        assert (other.name, other.surname) == ("Thrall", "Fils-de-Durotan")
        assert char.gear.head.id == 16842 and char.gear.head.ench == 2583 and char.gear.mainhand.ench is None
        # Chaque pièce est décrite pour le site : nom de base, qualité, niveaux, type ; à défaut le nom du lien.
        head, mainhand = char.gear.head, char.gear.mainhand
        assert (head.name, head.q, head.ilvl, head.req, head.cls, head.sub, head.inv) == (
            "Couronne de rage du ciel",
            4,
            66,
            60,
            4,
            3,
            1,
        )
        assert (mainhand.name, mainhand.q, mainhand.inv) == ("Sulfuras", None, None)
        assert char.spec_tab == 2 and char.talents.points["2-1"] == 5
        assert char.professions["186"].skill == 300 and char.professions["186"].recipes is None
        assert char.reputations["609"].v == 9800
        assert char.attunements["molten-core"] is True and char.attunements["onyxia"] is False
        assert char.lockouts[1].killed == 7
        assert char.pvp.hk_lifetime == 2340
        assert char.played == 123456
        assert len(list(db.errors.values())) == 0, list(db.errors.values())


class TestSession:
    def test_full_session_round_trips_into_the_site(self, db, member):
        seed()
        alchemy = Profession.objects.get(slug="alchemy")
        Recipe.objects.create(id=17580, profession=alchemy, name="Potion de mana majeure", min_skill=295)
        Recipe.objects.create(id=11448, profession=alchemy, name="Potion de mana supérieure", min_skill=205)
        lua = boot()
        g = lua.globals()
        login(lua)
        # Fenêtre d'alchimie ouverte : recettes lues.
        lua.execute(
            "_OPEN_TRADESKILL = { professionID = 171, professionName = 'Alchimie', skillLevel = 290, maxSkillLevel = 300, recipes = { 17580, 11448, 99999 } }"
        )
        g._FIRE("TRADE_SKILL_SHOW")
        g._ADVANCE(2)
        # Un boss, un minerai, une mort, une quête, un BG gagné.
        lua.execute("_INSTANCE = 'raid'; _INSTANCE_NAME = 'Cœur du Magma'; _INSTANCE_ID = 409")
        g._FIRE("PLAYER_ENTERING_WORLD")
        g._FIRE("ENCOUNTER_END", 672, "Ragnaros", 9, 40, 1)
        g._FIRE("UNIT_SPELLCAST_SUCCEEDED", "player", "cast-1", 2575)
        g._FIRE(
            "CHAT_MSG_LOOT",
            "Vous recevez un butin : |cffffffff|Hitem:2770:0:0|h[Minerai de cuivre]|h|rx3.",
            "",
            "",
            "",
            "",
        )
        g._FIRE("UNIT_SPELLCAST_SUCCEEDED", "player", "cast-2", 17580)  # recette connue → fabrication
        lua.execute("_TARGET = { name = 'Sanglier des Tarides', hostile = true }")
        g._DIE()
        lua.execute("_TARGET = nil")
        g._ADVANCE(1)  # le tueur est résolu et annoncé une seconde après la mort
        # Un loup tué : message d'expérience (le journal de combat est interdit aux addons sur Forever).
        g._FIRE("CHAT_MSG_COMBAT_XP_GAIN", "Loup des Tarides meurt, vous gagnez 45 points d'expérience.")
        g._FIRE("QUEST_TURNED_IN", 1234)
        g._FIRE("PVP_MATCH_COMPLETE", 0, 900)
        g._FIRE("PLAYER_LEVEL_UP", 60)

        code = logout_code(lua)
        assert code.startswith("WFG1:")
        payload = decode_export(code)
        (character,) = payload["characters"]
        assert (
            character["name"] == "Thrall"
            and character["surname"] == "Fils-de-Durotan"
            and character["class"] == "SHAMAN"
        )
        assert character["spec_tab"] == 2
        professions = {p["id"]: p for p in character["professions"]}
        assert professions[171]["recipes"] == [11448, 17580] and professions[186].get("recipes") is None
        counters = character["counters"]
        assert counters["boss_kills"] == 1 and counters["raids_done"] == 1 and counters["raids_entered"] == 1
        assert counters["bosses"]["672"]["n"] == 1 and counters["gathering"]["mining"] == 3
        assert counters["gathered_items"]["2770"] == 3 and counters["crafted"]["17580"] == 1
        assert counters["kills"] == 1 and character["mobs"] == {
            "Loup des Tarides": {"n": 1, "name": "Loup des Tarides", "first": g.time(), "last": g.time()}
        }
        assert (
            counters["deaths"] == 1
            and counters["quests"] == 1
            and counters["bg_played"] == 1
            and counters["bg_won"] == 1
        )
        kinds = [e["k"] for e in character["events"]]
        assert kinds == ["enter", "boss", "clear", "death", "bg", "level"]
        death = next(e for e in character["events"] if e["k"] == "death")
        assert death["killer"] == "Sanglier des Tarides" and death["zone"] == "Forêt d'Elwynn"
        assert "played" not in character  # temps de jeu opt-in
        assert list(character["journal"].keys()) == [g.date("%Y-%m-%d")]
        assert character["journal"][g.date("%Y-%m-%d")]["deaths"] == 1
        assert character["journal"][g.date("%Y-%m-%d")]["kills"] == 1
        assert character["journal"][g.date("%Y-%m-%d")]["mobs"] == {"Loup des Tarides": 1} == counters["mobs"]

        # Et le site l'importe tel quel.
        batch = services.import_code(member, code, source="paste")
        assert batch.summary["created"] == 1 and batch.summary["new_recipes"] == 2
        created = member.characters.get()
        assert (created.name, created.surname, created.level, created.main_role) == (
            "Thrall",
            "Fils-de-Durotan",
            60,
            "dps",
        )
        assert sorted(created.professions.values_list("profession__slug", "skill")) == [
            ("alchemy", 290),
            ("mining", 300),
        ]
        assert set(created.known_recipes.values_list("recipe_id", flat=True)) == {17580, 11448}
        assert created.snapshots.get().data["mobs"]["Loup des Tarides"]["n"] == 1

    def test_dungeons_and_raids_count_as_done_on_their_final_boss(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        char = g.WoWForeverGuildeDB.characters["Player-1-000ABC01"]
        lua.execute("_INSTANCE = 'party'; _INSTANCE_NAME = 'Les Mortemines'; _INSTANCE_ID = 36")
        g._FIRE("PLAYER_ENTERING_WORLD")
        g._FIRE("ENCOUNTER_END", 2741, "Rhahk'Zor", 1, 5, 1)  # premier boss : rien de terminé
        assert char.counters.boss_kills == 1 and char.counters.dungeons_done is None
        g._FIRE("ENCOUNTER_END", 2747, "Edwin Van Cleef", 1, 5, 1)
        assert char.counters.dungeons_done == 1 and char.counters.dungeons_entered == 1
        # Le Monastère compte une fois par aile ; un boss raté ne compte pas.
        g._FIRE("ENCOUNTER_END", 448, "Herod", 1, 5, 1)
        g._FIRE("ENCOUNTER_END", 450, "Grande Inquisitrice Blanchetête", 1, 5, 0)
        g._FIRE("ENCOUNTER_END", 450, "Grande Inquisitrice Blanchetête", 1, 5, 1)
        assert char.counters.dungeons_done == 3
        # Raids : Hakkar (793) et Kel'Thuzad (1114) selon le client Forever.
        g._FIRE("ENCOUNTER_END", 793, "Hakkar", 9, 20, 1)
        g._FIRE("ENCOUNTER_END", 1114, "Kel'Thuzad", 9, 40, 1)
        assert char.counters.raids_done == 2 and char.counters.boss_kills == 6
        clears = [e.instance for e in dict(char.events).values() if e.k == "clear"]
        assert sorted(clears) == [
            "deadmines",
            "naxxramas",
            "scarlet-monastery",
            "scarlet-monastery",
            "zul-gurub",
        ]

    def test_creature_kills_come_from_experience_messages(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        for text in (
            "Loup meurt, vous gagnez 45 points d'expérience.",
            "Loup meurt, vous gagnez 45 points d'expérience. (+9 bonus de groupe)",
            "Kobold mineur meurt, vous gagnez 30 points d'expérience.",
            "Vous gagnez 120 points d'expérience.",  # quête rendue : pas une créature
        ):
            g._FIRE("CHAT_MSG_COMBAT_XP_GAIN", text)
        char = g.WoWForeverGuildeDB.characters["Player-1-000ABC01"]
        assert char.counters.kills == 3 and dict(char.counters.mobs) == {"Loup": 2, "Kobold mineur": 1}
        assert {k: (m.n, m.name) for k, m in dict(char.mobs).items()} == {
            "Loup": (2, "Loup"),
            "Kobold mineur": (1, "Kobold mineur"),
        }
        status = next(d for d in dict(g._NS.collectors).values() if d.name == "kills").status(char)
        assert status == "3 créatures tuées · 2 espèces"
        # Le motif est construit depuis la chaîne du jeu : « %s » devient le nom, le reste est protégé.
        assert g._NS.XpPattern() == "^(.-) meurt, vous gagnez "

    def test_death_is_announced_by_guild_addon_message_and_shown_as_toast(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        # Sans guilde : rien ne part (le client moderne interdit les canaux de chat aux addons).
        g._DIE()
        g._ADVANCE(1)
        assert addon_sent(g) == []
        lua.execute("_GUILD = true")
        # Le tueur est la cible hostile au moment de mourir (pas de journal de combat sur Forever).
        lua.execute("_TARGET = { name = 'Sanglier des Tarides', hostile = true }")
        g._DIE()
        lua.execute("_TARGET = nil")
        g._ADVANCE(1)
        (sent,) = addon_sent(g)
        assert (sent.prefix, sent.kind) == ("WFG", "GUILD")
        assert sent.text.startswith(
            "D\t1\tPlayer-1-000ABC01\tThrall\tFils-de-Durotan\tSHAMAN\t60\tSanglier des Tarides\tForêt d'Elwynn\t"
        )
        # Réception par un autre addon, sur le canal de guilde : popup + son, nom coloré par classe, classe traduite.
        g._FIRE("CHAT_MSG_ADDON", "WFG", sent.text, "GUILD", "Thrall-Forever")
        toast = g.WoWForeverGuildeDeath
        assert (
            toast.shown is True
            and "|cff0070ddThrall|r" in toast.text.text
            and "Sanglier des Tarides" in toast.text.text
        )
        assert toast.footer.text == "Niveau 60 · Chaman · Forêt d'Elwynn"
        assert len(list(g._SOUNDS.values())) == 1
        # Ancienne version en face : nom de classe affiché au lieu du jeton, accepté tel quel (une autre mort,
        # plus d'une minute après : dans la minute, une seconde annonce du même personnage est un doublon).
        g._ADVANCE(60)
        g._FIRE(
            "CHAT_MSG_ADDON", "WFG", sent.text.replace("\tSHAMAN\t", "\tChaman\t"), "GUILD", "Thrall-Forever"
        )
        assert (
            toast.footer.text == "Niveau 60 · Chaman · Forêt d'Elwynn" and len(list(g._SOUNDS.values())) == 2
        )
        # Chuchoté par n'importe qui : ignoré.
        toast.shown = False
        g._FIRE("CHAT_MSG_ADDON", "WFG", sent.text, "WHISPER", "Inconnu-Forever")
        assert toast.shown is False
        # Son coupé → le popup reste, sans son.
        lua.execute("WoWForeverGuildeDB.settings.soundDeaths = false")
        g._ADVANCE(60)
        g._FIRE("CHAT_MSG_ADDON", "WFG", sent.text, "GUILD", "Thrall-Forever")
        assert toast.shown is True and len(list(g._SOUNDS.values())) == 2
        # Désactivé → rien n'est envoyé.
        lua.execute("WoWForeverGuildeDB.settings.announceDeaths = false")
        g._DIE()
        g._ADVANCE(1)
        assert len([s for s in addon_sent(g) if s.text.startswith("D\t")]) == 1

    def test_death_is_still_announced_when_the_game_hides_values_in_combat(self):
        # Valeurs « secrètes » (zone, nom de la cible) au moment de mourir : rien ne doit faire sauter l'annonce.
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute("_GUILD = true; _ZONE = _SECRET; _TARGET = { name = _SECRET, hostile = true }")
        g._DIE()
        lua.execute("_ZONE = nil; _TARGET = nil")
        g._ADVANCE(1)
        (sent,) = addon_sent(g)
        assert sent.text.startswith(
            "D\t1\tPlayer-1-000ABC01\tThrall\tFils-de-Durotan\tSHAMAN\t60\tquelque chose\t\t\t"
        )
        assert list(g.WoWForeverGuildeDB.errors.values()) == []
        assert g._NS.char.counters.deaths == 1
        payload = decode_export(logout_code(lua))  # l'export n'embarque aucune valeur secrète
        death = next(e for e in payload["characters"][0]["events"] if e["k"] == "death")
        assert death["zone"] == "" and "killer" not in death

    def test_killer_is_remembered_from_the_last_readable_hostile_target(self):
        # À la mort le client vide la cible et, en combat, les noms sont secrets : on retient la dernière cible
        # hostile lisible, ciblée pendant le combat ou dans la minute qui le précède.
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute("_GUILD = true; _TARGET = { name = 'Loup des Tarides', hostile = true }")
        g._FIRE("PLAYER_TARGET_CHANGED")
        # Reciblé en combat : nom illisible, on garde le loup.
        lua.execute("_TARGET = { name = _SECRET, hostile = true }")
        g._FIRE("PLAYER_REGEN_DISABLED")
        g._ADVANCE(90)  # long combat
        lua.execute("_TARGET = nil")  # le client vide la cible à la mort
        g._DIE()
        g._ADVANCE(1)
        deaths = [s.text for s in addon_sent(g) if s.text.startswith("D\t")]
        assert len(deaths) == 1 and "\tLoup des Tarides\t" in deaths[0]
        assert g._NS.DeathSource() == "tueur d'après mémoire (récap absent), joueur non d'après mémoire"
        # Un souvenir trop vieux, sans combat entre-temps, ne compte pas ; une cible amicale n'est jamais retenue.
        lua.execute("_ADDON_SENT = {}; _TARGET = { name = 'Kobold', hostile = true }")
        g._FIRE("PLAYER_TARGET_CHANGED")
        lua.execute("_TARGET = nil")
        g._ADVANCE(61)
        lua.execute("_TARGET = { name = 'Jaina', hostile = false }")
        g._FIRE("PLAYER_TARGET_CHANGED")
        lua.execute("_TARGET = nil")
        g._DIE()
        g._ADVANCE(1)
        deaths = [s.text for s in addon_sent(g) if s.text.startswith("D\t")]
        assert len(deaths) == 1 and "\tquelque chose\t" in deaths[0]
        assert list(g.WoWForeverGuildeDB.errors.values()) == []

    def test_death_recap_names_the_killing_blow_or_the_environment(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute("""
          _GUILD = true
          _RECAPS = {
            [1] = { { sourceName = 'Ragnaros', amount = 3000 }, { sourceName = 'Majordome Executus', amount = 9000 } },
            [2] = { { sourceName = 'Ragnaros' }, { environmentalDamageType = 'Falling', amount = 500 } },
          }
          C_DeathInfo = { GetDeathRecapEvents = function(id) return _RECAPS[id] end }
          _TARGET = { name = 'Sanglier des Tarides', hostile = true }
        """)
        g._DIE()  # première mort de la session : récap n° 1, qui prime sur la cible
        g._ADVANCE(1)
        g._DIE()  # deuxième : une chute
        g._ADVANCE(1)
        deaths = [s.text for s in addon_sent(g) if s.text.startswith("D\t")]
        assert "\tMajordome Executus\t" in deaths[0] and "\tune chute\t" in deaths[1]
        events = g._NS.char.events
        assert events[1].killer == "Majordome Executus" and events[1].env is None
        assert events[2].env == "Falling" and events[2].killer is None
        assert g._NS.DeathSource() == "tueur d'après récap (récap présent), joueur sans objet"  # une chute
        assert g._NS.char.counters.deaths == 2

    def test_collector_errors_are_listed_by_slash_command_and_recalled_at_login(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        g.SlashCmdList.WOWFOREVERGUILDE("erreurs")
        assert any("Aucune erreur" in m for m in list(g._CHAT.values()))
        # Un collecteur qui plante : l'erreur est gardée, listée, et rappelée à la prochaine connexion.
        g._NS.Safe("pve.onEvent", lua.eval("function() error('PvE.lua:63: attempt to index nil') end"))
        g.SlashCmdList.WOWFOREVERGUILDE("erreurs")
        chat = list(g._CHAT.values())
        assert any("1 erreur(s) enregistrée(s)" in m for m in chat)
        assert any("pve.onEvent" in m and "attempt to index nil" in m for m in chat)
        lua.execute("_CHAT = {}")
        g._FIRE("PLAYER_LOGIN")
        assert any("1 erreur(s)" in m and "/mf erreurs" in m for m in list(g._CHAT.values()))

    def test_protected_call_refused_by_the_game_is_recorded_and_exported(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute("_NS.Risky('RequestRaidInfo', function() end)")
        g._FIRE("ADDON_ACTION_FORBIDDEN", "WoWForeverGuilde", "JoinChannelByName()")
        g._FIRE("ADDON_ACTION_BLOCKED", "AutreAddon", "CastSpellByName()")  # pas le nôtre : ignoré
        assert any("Appel refusé" in m and "JoinChannelByName()" in m for m in list(g._CHAT.values()))
        errors = list(g.WoWForeverGuildeDB.errors.values())
        assert len(errors) == 1 and errors[0].where == "protected"
        expected = "ADDON_ACTION_FORBIDDEN : JoinChannelByName() (dernier appel sensible : RequestRaidInfo, il y a 0 s)"
        assert errors[0].error == expected
        payload = decode_export(logout_code(lua))
        assert payload["errors"][0]["error"] == expected

    def test_midnight_rollover_splits_days_in_memory(self):
        lua = boot()
        g = lua.globals()
        lua.execute("_CLOCK.now = os.time({year=2026, month=12, day=21, hour=22, min=0})")
        login(lua)
        g._DIE()
        day1 = g.date("%Y-%m-%d")
        g._ADVANCE(3 * 3600)  # 01:00 le lendemain : le ticker a tourné
        day2 = g.date("%Y-%m-%d")
        assert day1 != day2
        g._DIE()
        char = g.WoWForeverGuildeDB.characters["Player-1-000ABC01"]
        assert char.journal[day1].deaths == 1 and char.counters.deaths == 2
        g._FIRE("PLAYER_LOGOUT")
        assert char.journal[day2].deaths == 2

    def test_one_window_with_a_tab_per_screen(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        mf = g.SlashCmdList.WOWFOREVERGUILDE
        settings = g.WoWForeverGuildeDB.settings

        def tab(label):
            (button,) = [
                f
                for f in list(g._FRAMES.values())
                if f.kind == "Button" and f.scripts.OnClick and getattr(f.text, "text", None) == label
            ]
            return button

        # /mf : la fenêtre, sur son premier onglet ; un panneau n'existe qu'une fois ouvert.
        mf("")
        window = g.WoWForeverGuildeFrame
        assert window.shown is True and g.WoWForeverGuildeRoster.shown is True
        assert g.WoWForeverGuildeWanted is None and settings.windowTab == "roster"
        assert window.version.text == "v" + toc_version()
        # /mf wanted change d'onglet dans la même fenêtre ; redit, il la ferme ; /mf la rouvre où on l'a laissée.
        mf("wanted")
        assert window.shown is True and g.WoWForeverGuildeWanted.shown is True
        assert g.WoWForeverGuildeRoster.shown is False and settings.windowTab == "wanted"
        assert g._NS.UI.Shown("wanted") is True and g._NS.UI.Shown("roster") is False
        mf("wanted")
        assert window.shown is False and g._NS.UI.Shown("wanted") is False
        mf("")
        assert window.shown is True and g.WoWForeverGuildeWanted.shown is True
        # Les onglets se cliquent. Collecte : personnages du compte et état de la collecte.
        collect = tab("Collecte")
        collect.scripts.OnClick(collect)
        panel = g.WoWForeverGuildeCollect
        assert panel.shown is True and g.WoWForeverGuildeWanted.shown is False
        assert panel.status.shown is True and "Thrall" in panel.status.charLines[1].text
        # L'export est une vue de cet onglet : /mf export (ou le bouton) montre le code, régénéré à chaque fois ;
        # « Retour » ou rouvrir l'onglet revient à l'état.
        assert g.WoWForeverGuildeExport is None
        mf("export")
        export = g.WoWForeverGuildeExport
        assert panel.shown is True and export.shown is True and panel.status.shown is False
        assert decode_export(export.box.text)["characters"][0]["name"] == "Thrall"
        mf("collecte")
        assert window.shown is False  # redite sur son onglet, la commande ferme
        mf("collecte")
        assert panel.status.shown is True and export.shown is False
        panel.status.exportButton.scripts.OnClick(panel.status.exportButton)
        assert export.shown is True and panel.status.shown is False
        # Six onglets, un bouton chacun ; l'en-tête garde la sauvegarde à portée, quel que soit l'onglet.
        labels = ("Guilde en jeu", "Wanted", "Collecte", "Réglages", "Nouveautés", "Diagnostic")
        assert all(tab(label) for label in labels)
        assert "sans sauvegarde" in window.session.text
        window.save.scripts.OnClick(window.save)
        assert g._RELOADED is True
        # La fenêtre lâchée ailleurs retient sa place.
        lua.execute('WoWForeverGuildeFrame.point = { "TOPLEFT", UIParent, "TOPLEFT", 40, -60 }')
        window.scripts.OnDragStop(window)
        assert list(settings.windowPoint.values()) == ["TOPLEFT", "TOPLEFT", 40, -60]
        assert list(g.WoWForeverGuildeDB.errors.values()) == []

    def test_settings_tab_groups_every_checkbox(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        settings = g.WoWForeverGuildeDB.settings
        g.SlashCmdList.WOWFOREVERGUILDE("reglages")
        panel = g.WoWForeverGuildeSettings
        assert panel.shown is True
        checks = dict(panel.checks)
        assert sorted(checks) == sorted(
            [
                "sharePosition", "minimapDots", "minimapButton", "gankAlerts",
                "showDeaths", "soundDeaths", "announceDeaths", "wantedAlerts",
                "send", "sharePlaytime", "reloadReminder",
            ]
        )  # fmt: skip

        def click(key, on):
            checks[key].checked = on
            checks[key].scripts.OnClick(checks[key])

        # Une case écrit son réglage ; celles qui ont un effet immédiat passent par leur fonction.
        click("soundDeaths", False)
        click("sharePlaytime", True)
        assert (settings.soundDeaths, settings.sharePlaytime) == (False, True)
        click("sharePosition", False)
        assert settings.sharePosition is False
        click("wantedAlerts", False)
        assert settings.wantedAlerts is False
        # Le rappel de sauvegarde se recoche ici (le dialogue ne savait que le couper).
        g.StaticPopupDialogs.WFG_RELOAD.OnAlt()
        assert settings.reloadReminder is False
        click("reloadReminder", True)
        assert settings.reloadReminder is True
        # « Envoyer ce personnage » vaut pour le personnage connecté seulement.
        guid = g._NS.char.guid
        click("send", False)
        assert settings.excluded[guid] is True and checks["send"].get() is False
        click("send", True)
        assert settings.excluded[guid] is None and checks["send"].get() is True
        assert list(g.WoWForeverGuildeDB.errors.values()) == []

    def test_news_tab_shows_release_notes_and_flags_the_unread_ones(self):
        def tab(g, label):
            (button,) = [
                f
                for f in list(g._FRAMES.values())
                if f.kind == "Button" and f.scripts.OnClick and getattr(f.text, "text", None) == label
            ]
            return button

        # Chaque version du code a ses notes : sans elles, rien ne serait annoncé à la mise à jour.
        lua = boot()
        g = lua.globals()
        login(lua)
        assert g._NS.UI.NewsUnseen() == toc_version()
        notes = [dict(entry) for entry in g._NS.CHANGELOG.values()]
        assert all(entry["version"] and len(list(entry["notes"].values())) >= 1 for entry in notes)
        versions = [entry["version"] for entry in notes]
        assert all(
            g._NS.VersionNewer(a, b) for a, b in zip(versions, versions[1:], strict=False)
        )  # la plus récente d'abord

        # En 0.6.13, jamais rien lu : une ligne à la connexion, l'onglet en vert, les notes de la 0.6.13 et d'avant.
        lua = boot()
        g = lua.globals()
        g._NS.VERSION = "0.6.13"
        login(lua)
        assert any("Version 0.6.13 : ce qui change" in m for m in list(g._CHAT.values()))
        mf = g.SlashCmdList.WOWFOREVERGUILDE
        mf("qui")
        assert tab(g, "Nouveautés").fresh is True
        mf("nouveautes")
        text = g.WoWForeverGuildeNews.text.text
        assert "0.6.13|r  |cff5ad15anouveau|r" in text and "Popups relus" in text and "0.6.12" in text
        assert (
            "0.7.0" not in text and text.count("nouveau|r") == 1
        )  # ni une version à venir, ni tout l'historique
        # Lues : plus rien à signaler, ni sur l'onglet ni au prochain passage.
        assert g.WoWForeverGuildeDB.settings.changelogSeen == "0.6.13" and g._NS.UI.NewsUnseen() is None
        mf("qui")
        assert tab(g, "Nouveautés").fresh is False
        mf("nouveautes")
        assert "nouveau|r" not in g.WoWForeverGuildeNews.text.text

        # Après la mise à jour en 0.7.0 : ses notes apparaissent, seules marquées nouvelles.
        lua = boot()
        g = lua.globals()
        g._NS.VERSION = "0.7.0"
        g.WoWForeverGuildeDB = lua.table(settings=lua.table(changelogSeen="0.6.13"))
        login(lua)
        assert any("Version 0.7.0 : ce qui change" in m for m in list(g._CHAT.values()))
        g.SlashCmdList.WOWFOREVERGUILDE("nouveautes")
        text = g.WoWForeverGuildeNews.text.text
        assert text.startswith("|cffffd1000.7.0|r  |cff5ad15anouveau|r") and text.count("nouveau|r") == 1
        assert "Une seule fenêtre /mf" in text and "0.6.13|r\n" in text
        # Relancé sans rien de neuf : silence.
        lua2 = boot()
        g2 = lua2.globals()
        g2._NS.VERSION = "0.7.0"
        g2.WoWForeverGuildeDB = lua2.table(settings=lua2.table(changelogSeen="0.7.0"))
        login(lua2)
        assert not any("ce qui change" in m for m in list(g2._CHAT.values()))
        assert list(g.WoWForeverGuildeDB.errors.values()) == []

    def test_diagnostic_tab_gives_a_report_to_copy(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        chat_before = len(list(g._CHAT.values()))
        g.SlashCmdList.WOWFOREVERGUILDE("diag")
        panel = g.WoWForeverGuildeDiag
        report = panel.box.text
        # Le rapport : version du code et .toc lu par le jeu, les lignes de /mf api, puis les erreurs.
        assert panel.shown is True and report.startswith(
            f"Manuel Feralas {toc_version()} · .toc chargé par le jeu : "
        )
        assert "lecture · talents" in report and "popups · " in report and "Aucune erreur" in report
        # Ouvrir l'onglet n'écrit rien dans le chat et ne note rien : c'est le bouton qui envoie au site.
        assert len(list(g._CHAT.values())) == chat_before and list(g.WoWForeverGuildeDB.errors.values()) == []
        panel.send.scripts.OnClick(panel.send)
        assert any("Diagnostic noté" in m for m in list(g._CHAT.values()))
        (noted,) = [dict(e) for e in g.WoWForeverGuildeDB.errors.values()]
        assert noted["where"] == "diagnostic" and "lecture · talents" in noted["error"]
        # « Relire » reprend l'état du moment : l'erreur notée y figure ; la zone est en lecture seule.
        panel.refresh.scripts.OnClick(panel.refresh)
        assert "1 erreur(s) enregistrée(s)" in panel.box.text and "diagnostic" in panel.box.text
        report = panel.box.text
        panel.box.text = "effacé par mégarde"
        panel.box.scripts.OnTextChanged(panel.box, True)
        assert panel.box.text == report
        # La trace se lance d'ici aussi.
        panel.trace.scripts.OnClick(panel.trace)
        assert g._NS.traceUntil > g._CLOCK.now and any(
            "Trace des messages" in m for m in list(g._CHAT.values())
        )

    def test_minimap_button_opens_the_window_and_can_be_moved_or_hidden(self):
        # Sans minimap sur ce client : pas de bouton, pas d'erreur.
        lua = boot()
        g = lua.globals()
        login(lua)
        assert g.WoWForeverGuildeMinimapButton is None and list(g.WoWForeverGuildeDB.errors.values()) == []

        lua = boot()
        g = lua.globals()
        lua.execute("""
          Minimap = CreateFrame("Frame", "Minimap")
          function Minimap:GetWidth() return 140 end
          function Minimap:GetCenter() return 500, 400 end
          function Minimap:GetEffectiveScale() return 1 end
          function GetCursorPosition() return 500, 500 end  -- juste au-dessus du centre de la minimap
        """)
        login(lua)
        button = g.WoWForeverGuildeMinimapButton
        settings = g.WoWForeverGuildeDB.settings
        assert button.shown is True and settings.minimapButton is True
        assert button.icon.texture == "Interface\\AddOns\\WoWForeverGuilde\\Samwise"
        # Posé à 215° par défaut, au bord de la minimap (rayon 76).
        x, y = button.point[4], button.point[5]
        assert (button.point[1], round(x), round(y)) == ("CENTER", -62, -44)
        # Clic : la fenêtre ; clic droit : les réglages.
        button.scripts.OnClick(button, "LeftButton")
        assert g.WoWForeverGuildeFrame.shown is True
        button.scripts.OnClick(button, "LeftButton")
        assert g.WoWForeverGuildeFrame.shown is False
        button.scripts.OnClick(button, "RightButton")
        assert g.WoWForeverGuildeFrame.shown is True and g.WoWForeverGuildeSettings.shown is True
        # Survol : le nom, le mode d'emploi, et les nouveautés tant qu'elles ne sont pas lues.
        button.scripts.OnEnter(button)
        lines = list(g.GameTooltip.lines.values())
        assert "Manuel Feralas" in lines[0] and "glisser" in lines[1] and "ce qui change" in lines[2]
        # Glissé : il suit le curseur autour de la minimap, l'angle est retenu.
        button.scripts.OnDragStart(button)
        button.scripts.OnUpdate(button)
        button.scripts.OnDragStop(button)
        assert round(settings.minimapButtonAngle) == 90 and button.scripts.OnUpdate is None
        assert (round(button.point[4]), round(button.point[5])) == (0, 76)
        # La case des réglages le retire et le remet, à la même place.
        check = g.WoWForeverGuildeSettings.checks.minimapButton
        check.checked = False
        check.scripts.OnClick(check)
        assert button.shown is False and settings.minimapButton is False
        check.checked = True
        check.scripts.OnClick(check)
        assert button.shown is True and round(button.point[5]) == 76
        assert list(g.WoWForeverGuildeDB.errors.values()) == []

    def test_window_reopens_where_it_was_left(self):
        lua = boot()
        g = lua.globals()
        lua.execute(
            'WoWForeverGuildeDB = { settings = { windowTab = "wanted", windowPoint = { "TOPLEFT", "TOPLEFT", 40, -60 } } }'
        )
        login(lua)
        g.SlashCmdList.WOWFOREVERGUILDE("")
        window = g.WoWForeverGuildeFrame
        assert (
            window.shown is True
            and g.WoWForeverGuildeWanted.shown is True
            and g.WoWForeverGuildeRoster is None
        )
        assert (window.point[1], window.point[3], window.point[4], window.point[5]) == (
            "TOPLEFT",
            "TOPLEFT",
            40,
            -60,
        )
        # Un onglet disparu d'une version à l'autre : le premier, sans erreur.
        g.WoWForeverGuildeDB.settings.windowTab = "disparu"
        window.shown = False
        g._NS.UI.Open("disparu")
        assert g.WoWForeverGuildeRoster.shown is True
        assert list(g.WoWForeverGuildeDB.errors.values()) == []

    def test_reload_reminder_after_three_hours_in_calm(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        g._ADVANCE(2 * 3600)
        assert g._POPUP is None
        g._ADVANCE(3600 + 60)
        assert g._POPUP.which == "WFG_RELOAD" and "3 h" in g._POPUP.text
        g._POPUP = None
        g._ADVANCE(3600)
        assert g._POPUP is None  # une seule fois par session

    def test_transfer_detection_merges_counters(self):
        lua = boot()
        g = lua.globals()
        lua.execute("""
          WoWForeverGuildeDB = { version = 1, characters = { ["Player-1-OLD"] = { guid = "Player-1-OLD", name = "Thrall", class = "SHAMAN", race = "Orc", level = 58,
            counters = { deaths = 9, kills = 4 }, mobs = { ["299"] = { n = 4, name = "Loup", first = 1, last = 2 } }, journal = {}, events = {}, previous_guids = {}, created_at = 1, updated_at = 2, counting_since = 1 } } }
        """)
        login(lua)
        assert g._POPUP.which == "WFG_TRANSFER" and "Thrall (Chaman, niveau 58)" in g._POPUP.text
        ns = g._NS
        ns.char.mobs["299"] = lua.table(n=1, name="Loup", first=5, last=6)
        ns.Store.Merge(ns.char, g.WoWForeverGuildeDB.characters["Player-1-OLD"])
        char = g.WoWForeverGuildeDB.characters["Player-1-000ABC01"]
        assert char.counters.deaths == 9 and char.previous_guids[1] == "Player-1-OLD"
        assert (char.mobs["299"].n, char.mobs["299"].first, char.mobs["299"].last) == (5, 1, 6)
        assert g.WoWForeverGuildeDB.characters["Player-1-OLD"] is None
        assert char.counting_since == 1

    def test_professions_with_gaps_are_all_collected(self):
        # Sans deuxième métier principal ni archéologie : pêche et cuisine restent lues malgré les nil.
        lua = boot()
        lua.execute("""
          _PROFESSIONS[4] = { name = "Pêche", skill = 150, max = 225, line = 356 }
          _PROFESSIONS[5] = { name = "Cuisine", skill = 75, max = 150, line = 185 }
          _PROFESSION_SLOTS = { 1, nil, nil, 4, 5, nil }
        """)
        login(lua)
        payload = decode_export(logout_code(lua))
        (character,) = payload["characters"]
        assert sorted(p["id"] for p in character["professions"]) == [185, 186, 356]
        assert {p["id"]: p["skill"] for p in character["professions"]} == {185: 75, 186: 300, 356: 150}

    def test_talents_are_keyed_by_tree_row_and_column_with_the_classic_api(self):
        lua = boot()
        login(lua)
        payload = decode_export(logout_code(lua))
        (character,) = payload["characters"]
        talents = character["talents"]
        # L'index 1 d'un arbre est en (rangée 1, colonne 1), l'index 2 en (1, 2) dans le simulateur.
        assert talents["api"] == "classic" and talents["tabs"] == [0, 8, 1]
        assert talents["grid"] == {"2-1-1": 5, "2-1-2": 3, "3-1-1": 1}
        assert talents["points"] == {"2-1": 5, "2-2": 3, "3-1": 1}
        assert character["spec_tab"] == 2
        assert lua.globals()._NS.TalentSummary() == "Amélioration 0/8/1"

    def test_talents_fall_back_on_modern_traits_as_ranks_per_spell(self):
        lua = boot()
        lua.execute("GetNumTalentTabs, GetNumTalents, GetTalentInfo, GetTalentTabInfo = nil, nil, nil, nil")
        lua.execute("_TRAITS = { [16035] = 5, [17364] = 1 }")  # Convection 5/5, Frappe-tempête 1/1
        login(lua)
        payload = decode_export(logout_code(lua))
        (character,) = payload["characters"]
        assert character["talents"] == {"api": "traits", "spells": {"16035": 5, "17364": 1}}
        assert "spec_tab" not in character
        assert lua.globals()._NS.TalentSummary() == ""  # pas d'arbres : pas de résumé dans la position

    def test_no_talent_api_is_reported_once_and_shown_as_unavailable(self):
        lua = boot()
        lua.execute("GetNumTalentTabs, GetNumTalents, GetTalentInfo, GetTalentTabInfo = nil, nil, nil, nil")
        lua.execute("C_ClassTalents, C_Traits = nil, nil")
        login(lua)
        g = lua.globals()
        g._FIRE("CHARACTER_POINTS_CHANGED")
        g._ADVANCE(2)
        errors = list(g.WoWForeverGuildeDB.errors.values())
        assert [e.where for e in errors] == ["talents.scan"]
        assert "aucune API de talents" in errors[0].error and "/mf api" in errors[0].error
        statuses = {d.name: d.status(g._NS.char) for d in g._NS.collectors.values() if d.name == "talents"}
        assert "Indisponible" in statuses["talents"]
        assert decode_export(logout_code(lua))["characters"][0].get("talents") in (None, {})

    def test_traits_without_a_talent_config_are_not_an_error(self):
        # L'API des traits existe mais le personnage n'a pas (encore) de configuration : rien à lire, rien à noter.
        lua = boot()
        lua.execute("GetNumTalentTabs, GetNumTalents, GetTalentInfo, GetTalentTabInfo = nil, nil, nil, nil")
        login(lua)
        g = lua.globals()
        g._FIRE("CHARACTER_POINTS_CHANGED")
        g._ADVANCE(2)
        assert list(g.WoWForeverGuildeDB.errors.values()) == []
        statuses = {d.name: d.status(g._NS.char) for d in g._NS.collectors.values() if d.name == "talents"}
        assert "Indisponible" not in statuses["talents"]

    def test_empty_fishing_window_is_not_an_error(self):
        lua = boot()
        lua.execute(
            "_PROFESSIONS[4] = { name = 'Pêche', skill = 150, max = 225, line = 356 }; _PROFESSION_SLOTS[4] = 4"
        )
        login(lua)
        g = lua.globals()
        lua.execute(
            "_OPEN_TRADESKILL = { professionID = 356, professionName = 'Pêche', skillLevel = 150,"
            " maxSkillLevel = 225, recipes = {} }"
        )
        g._FIRE("TRADE_SKILL_SHOW")
        g._ADVANCE(2)
        assert list(g.WoWForeverGuildeDB.errors.values()) == []

    def test_professions_are_reported_under_their_parent_skill_line(self):
        lua = boot()
        # Base moderne : l'alchimie est lue comme « Alchimie Classic » (2485), fille de 171 ; la mère dit 0, la
        # compétence est celle de la ligne lue.
        lua.execute(
            "_PROFESSIONS[2] = { name = 'Alchimie', skill = 0, max = 0, line = 2485 };"
            "_SKILL_PARENTS[2485] = 171; _SKILL_INFO[2485] = { skillLevel = 292, maxSkillLevel = 300 }"
        )
        login(lua)
        before = decode_export(logout_code(lua))["characters"][0]
        assert {p["id"]: p["skill"] for p in before["professions"]} == {171: 292, 186: 300}
        g = lua.globals()
        g._FIRE("PLAYER_LOGIN")
        g._ADVANCE(5)
        lua.execute(
            "_OPEN_TRADESKILL = { professionID = 171, professionName = 'Alchimie', skillLevel = 0, maxSkillLevel = 0, parentProfessionID = 0, recipes = { 17580 } };"
            "_OPEN_CHILD = { professionID = 2485, professionName = 'Alchimie Classic', skillLevel = 295, maxSkillLevel = 300, parentProfessionID = 171 }"
        )
        g._FIRE("TRADE_SKILL_SHOW")
        g._ADVANCE(2)
        lua.execute("_SKILL_INFO[2485] = { skillLevel = 295, maxSkillLevel = 300 }")  # la fenêtre a dit 295
        payload = decode_export(logout_code(lua))
        (character,) = payload["characters"]
        professions = {p["id"]: p for p in character["professions"]}
        assert set(professions) == {171, 186}
        assert professions[171]["line"] == 2485 and professions[171]["skill"] == 295
        assert professions[171]["max"] == 300 and professions[171]["recipes"] == [17580]
        assert professions[186]["line"] == 186 and professions[186]["skill"] == 300

    def test_crafts_count_from_the_recipe_sheet_even_before_the_window_was_read(self):
        # Recette apprise mais fenêtre jamais lue par l'addon (autre PC, macro) : la fiche de recette du client
        # suffit. Un sort quelconque n'est pas une fabrication ; en combat on ne cherche pas.
        lua = boot()
        login(lua)
        g = lua.globals()
        g._FIRE("UNIT_SPELLCAST_SUCCEEDED", "player", "cast-1", 17580)
        g._FIRE("UNIT_SPELLCAST_SUCCEEDED", "player", "cast-2", 4321)
        lua.execute("_COMBAT = true")
        g._FIRE("UNIT_SPELLCAST_SUCCEEDED", "player", "cast-3", 11448)
        lua.execute("_COMBAT = nil")
        counters = decode_export(logout_code(lua))["characters"][0]["counters"]
        assert counters["crafted_total"] == 1 and counters["crafted"] == {"17580": 1}

    def test_crafted_result_event_counts_once_with_the_spell_cast(self):
        # Base moderne : le sort réussi puis le résultat de fabrication arrivent pour la même recette ; une seule
        # fabrication. Le résultat seul (recette inconnue de l'addon) compte aussi.
        lua = boot()
        login(lua)
        g = lua.globals()
        g._FIRE("UNIT_SPELLCAST_SUCCEEDED", "player", "cast-1", 17580)
        g._FIRE("TRADE_SKILL_ITEM_CRAFTED_RESULT", lua.eval("{ recipeID = 17580, quantity = 1 }"))
        g._FIRE("TRADE_SKILL_ITEM_CRAFTED_RESULT", lua.eval("{ recipeID = 2538, quantity = 1 }"))
        g._ADVANCE(2)
        g._FIRE("TRADE_SKILL_ITEM_CRAFTED_RESULT", lua.eval("{ recipeID = 2538, quantity = 1 }"))
        counters = decode_export(logout_code(lua))["characters"][0]["counters"]
        assert counters["crafted_total"] == 3 and counters["crafted"] == {"17580": 1, "2538": 2}

    def test_classic_trade_skill_window_lists_recipes_and_their_crafts_count(self):
        # Client sans C_TradeSkillUI.GetAllRecipeIDs : la cuisine se lit par GetTradeSkillInfo / RecipeLink, en
        # sautant les en-têtes ; la ligne se retrouve par son nom parmi les métiers connus.
        lua = boot()
        lua.execute(
            "_PROFESSIONS[5] = { name = 'Cuisine', skill = 150, max = 225, line = 185 }; _PROFESSION_SLOTS[5] = 5;"
            "C_TradeSkillUI.GetAllRecipeIDs = nil; C_TradeSkillUI.GetRecipeInfo = nil;"
            "C_TradeSkillUI.GetBaseProfessionInfo = nil; C_TradeSkillUI.GetChildProfessionInfo = nil;"
            "C_TradeSkillUI.GetTradeSkillLine = nil"
        )
        login(lua)
        g = lua.globals()
        lua.execute(
            "_CLASSIC_TRADESKILL = { name = 'Cuisine', skill = 150, max = 225,"
            " { name = 'Plats', type = 'header' },"
            " { name = 'Pain', type = 'trivial', link = '|cffffd000|Henchant:2538|h[Pain]|h|r' },"
            " { name = 'Ragoût', type = 'optimal', link = '|cffffd000|Henchant:3370|h[Ragoût]|h|r' } }"
        )
        g._FIRE("TRADE_SKILL_SHOW")
        g._FIRE("TRADE_SKILL_UPDATE")
        g._ADVANCE(2)
        g._FIRE("UNIT_SPELLCAST_SUCCEEDED", "player", "cast-1", 3370)
        character = decode_export(logout_code(lua))["characters"][0]
        professions = {p["id"]: p for p in character["professions"]}
        assert professions[185]["recipes"] == [2538, 3370] and professions[185]["skill"] == 150
        assert character["counters"]["crafted"] == {"3370": 1}
        assert list(g.WoWForeverGuildeDB.errors.values()) == []

    def test_empty_recipe_read_keeps_known_recipes_and_is_reported_once(self):
        lua = boot()
        login(lua)
        g = lua.globals()
        lua.execute(
            "_OPEN_TRADESKILL = { professionID = 171, professionName = 'Alchimie', skillLevel = 290, maxSkillLevel = 300, recipes = { 17580 } }"
        )
        g._FIRE("TRADE_SKILL_SHOW")
        g._ADVANCE(2)
        lua.execute("_OPEN_TRADESKILL.recipes = {}")
        g._FIRE("TRADE_SKILL_SHOW")
        g._ADVANCE(2)
        g._FIRE("TRADE_SKILL_SHOW")
        g._ADVANCE(2)
        character = decode_export(logout_code(lua))["characters"][0]
        assert {p["id"]: p.get("recipes") for p in character["professions"]}[171] == [17580]
        errors = [dict(e) for e in g.WoWForeverGuildeDB.errors.values()]
        assert len(errors) == 1 and "0 recette lue par C_TradeSkillUI" in errors[0]["error"]
        g.SlashCmdList.WOWFOREVERGUILDE("collecte")
        # La ligne de statut dit combien de recettes sont connues.
        assert "Alchimie 290 · 1 recettes" in g.WoWForeverGuildeCollect.status.statusLines.professions.text

    def test_api_diagnostic_is_printed_and_travels_with_the_errors(self):
        lua = boot()
        login(lua)
        g = lua.globals()
        lua.execute("_GUILD = true")
        g.SlashCmdList.WOWFOREVERGUILDE("api")
        chat = list(g._CHAT.values())
        assert any(
            "talents · présent : GetNumTalentTabs" in m and "absent : C_SpecializationInfo" in m for m in chat
        )
        assert any(
            "métiers · présent : GetProfessions" in m and "absent : GetNumSkillLines" in m for m in chat
        )
        assert any(
            "lecture · talents : classic (arbres)" in m
            and "guilde : oui" in m
            and "carte 1429 (0.50, 0.50)" in m
            for m in chat
        )
        assert any(
            "Alchimie (171→171) 290" in m and "Minage (186→186) 300" in m for m in chat
        )  # ligne lue → mère
        assert any("Diagnostic noté" in m for m in chat)
        errors = decode_export(logout_code(lua))["errors"]
        assert len(errors) == 1 and errors[0]["where"] == "diagnostic"
        assert (
            errors[0]["error"].startswith("talents · présent")
            and "client 1.60.1 (12345, 16001)" in errors[0]["error"]
        )

    @pytest.mark.parametrize("modern", [False, True], ids=["battlefield_winner", "pvp_match_complete"])
    def test_two_consecutive_battlegrounds_on_the_same_map_are_both_counted(self, modern):
        lua = boot()
        g = lua.globals()
        login(lua)

        def play_one(winner: int) -> None:
            lua.execute("_INSTANCE = 'pvp'; _INSTANCE_NAME = 'Goulet des Chanteguerres'")
            lua.execute("_BG = { status = 'active', map = 'Goulet des Chanteguerres' }")
            g._FIRE("PLAYER_ENTERING_WORLD")
            g._FIRE("UPDATE_BATTLEFIELD_STATUS", 1)
            if modern:
                g._FIRE("PVP_MATCH_COMPLETE", winner, 900)
            else:
                lua.execute(f"_BG.winner = {winner}")
                g._FIRE("UPDATE_BATTLEFIELD_STATUS", 1)
                g._FIRE("UPDATE_BATTLEFIELD_STATUS", 1)  # l'écran des scores rafraîchit plusieurs fois
            # Sortie du BG.
            lua.execute("_INSTANCE = nil; _INSTANCE_NAME = nil; _BG = { status = 'none' }")
            g._FIRE("UPDATE_BATTLEFIELD_STATUS", 1)
            g._FIRE("PLAYER_ENTERING_WORLD")

        play_one(0)  # Horde gagne
        play_one(1)  # Alliance gagne
        char = g.WoWForeverGuildeDB.characters["Player-1-000ABC01"]
        assert char.counters.bg_played == 2 and char.counters.bg_won == 1
        bucket = char.pvp.bg["Goulet des Chanteguerres"]
        assert bucket.played == 2 and bucket.won == 1
        assert [e.k for e in char.events.values()] == ["bg", "bg"]

    def test_excluded_character_is_not_exported(self):
        lua = boot()
        login(lua)
        lua.execute("WoWForeverGuildeDB.settings.excluded['Player-1-000ABC01'] = true")
        payload = decode_export(logout_code(lua))
        assert payload["characters"] == [] and payload["addon"] == toc_version()

    def test_export_embeds_game_client_identity(self):
        # Le site refuse les exports venant de Retail ou Classic : seul Forever (interface 16001) passe.
        lua = boot()
        login(lua)
        payload = decode_export(logout_code(lua))
        assert payload["client"] == {"version": "1.60.1", "build": "12345", "toc": 16001, "project": 1}
        assert set(payload) == {"v", "addon", "install", "exported_at", "client", "characters", "errors"}

    def test_export_omits_client_when_build_info_is_unavailable(self):
        lua = boot()
        login(lua)
        lua.execute("GetBuildInfo = nil")
        assert "client" not in decode_export(logout_code(lua))


class TestDurability:
    """Les lectures en bloc (connexion, déconnexion, API pas prête) ne détruisent jamais ce que l'addon savait :
    le site n'a pas de mémoire au-delà du dernier instantané, un export creux l'effacerait."""

    def test_empty_reads_at_logout_keep_everything_known(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        char = g.WoWForeverGuildeDB.characters["Player-1-000ABC01"]
        assert char.counters.hk == 2340 and char.pvp.hk_lifetime == 2340
        # À la déconnexion le client ne répond plus : zéro victoire honorable, aucun objet porté, aucun métier,
        # aucun point de talent, aucune quête terminée, aucun verrou.
        lua.execute("""
          GetPVPLifetimeStats = function() return 0, 0 end
          _GEAR = {}
          _PROFESSION_SLOTS = {}
          _TALENTS.ranks = {}
          _QUESTS_DONE = {}
          GetNumSavedInstances = function() return 0 end
        """)
        payload = decode_export(logout_code(lua))
        (character,) = payload["characters"]
        assert character["counters"]["hk"] == 2340 and character["pvp"]["hk_lifetime"] == 2340
        assert character["journal"][g.date("%Y-%m-%d")]["hk"] == 2340
        assert character["gear"]["head"]["id"] == 16842
        assert {p["id"] for p in character["professions"]} == {171, 186}
        assert character["talents"]["grid"]["2-1-1"] == 5 and character["spec_tab"] == 2
        assert character["attunements"]["molten-core"] is True
        assert character["lockouts"][0]["killed"] == 7
        assert list(g.WoWForeverGuildeDB.errors.values()) == []

    def test_level_up_counts_even_when_the_client_still_reports_the_old_level(self):
        """Vu sur Forever le 8 novembre : montée au 24 annoncée à 9h54, UnitLevel répondait encore 23 à la sortie
        du jeu à 10h18, et le site est resté au 23. L'événement de montée fait foi, la relecture ne redescend pas."""
        lua = boot()
        g = lua.globals()
        lua.execute("_PLAYER.level = 23")
        login(lua)
        char = g.WoWForeverGuildeDB.characters["Player-1-000ABC01"]
        assert char.level == 23
        g._FIRE("PLAYER_LEVEL_UP", 24)  # le client, lui, continue de répondre 23
        g._ADVANCE(2)  # relecture différée de l'identité
        assert char.level == 24
        (character,) = decode_export(logout_code(lua))["characters"]
        assert character["level"] == 24
        assert [e["level"] for e in character["events"] if e["k"] == "level"] == [24]

    def test_gathering_window_fits_fishing_and_slow_looting_but_not_the_next_kill(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        char = g.WoWForeverGuildeDB.characters["Player-1-000ABC01"]
        fish = "Vous recevez un butin : |cffffffff|Hitem:6291:0:0|h[Poisson cru]|h|rx2."
        ore = "Vous recevez un butin : |cffffffff|Hitem:2770:0:0|h[Minerai de cuivre]|h|r."
        # Pêche : le bouchon mord 20 s après le lancer, le butin compte quand même.
        g._FIRE("UNIT_SPELLCAST_SUCCEEDED", "player", "cast-f", 7620)
        g._ADVANCE(20)
        g._FIRE("CHAT_MSG_LOOT", fish, "", "", "", "")
        assert char.counters.gathering.fishing == 2
        # Filon ramassé à la main 8 s après le sort : compte ; 11 s : trop tard.
        g._FIRE("UNIT_SPELLCAST_SUCCEEDED", "player", "cast-m1", 2575)
        g._ADVANCE(8)
        g._FIRE("CHAT_MSG_LOOT", ore, "", "", "", "")
        g._FIRE("UNIT_SPELLCAST_SUCCEEDED", "player", "cast-m2", 2575)
        g._ADVANCE(11)
        g._FIRE("CHAT_MSG_LOOT", ore, "", "", "", "")
        assert char.counters.gathering.mining == 1
        # Fenêtre de butin refermée : le message qui suit d'un instant compte, celui d'un monstre 5 s après non.
        g._FIRE("UNIT_SPELLCAST_SUCCEEDED", "player", "cast-m3", 2575)
        g._FIRE("LOOT_CLOSED")
        g._FIRE("CHAT_MSG_LOOT", ore, "", "", "", "")
        g._ADVANCE(5)
        g._FIRE("CHAT_MSG_LOOT", ore, "", "", "", "")
        assert char.counters.gathering.mining == 2

    def test_fishing_is_read_from_the_channel_and_the_spell_name(self):
        # La pêche est canalisée : le client peut n'émettre que CHANNEL_START, avec un identifiant inconnu de la table
        # et un nom lu par l'API Classic ; le bouchon cliqué (CHANNEL_STOP) rouvre 10 s pour le butin tardif.
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute(
            "C_Spell = nil; function GetSpellInfo(id) if id == 99001 then return 'Pêche (Apprenti)' end return 'Sort' end"
        )
        char = g.WoWForeverGuildeDB.characters["Player-1-000ABC01"]
        fish = "Vous recevez un butin : |cffffffff|Hitem:6291:0:0|h[Poisson cru]|h|rx2."
        g._FIRE("UNIT_SPELLCAST_CHANNEL_START", "player", "c1", 99001)
        assert g._NS.GatherSource().startswith(
            "dernier sort 99001 « Pêche (Apprenti) » (UNIT_SPELLCAST_CHANNEL_START) → fishing"
        )
        g._ADVANCE(28)  # le bouchon mord tard
        g._FIRE("UNIT_SPELLCAST_CHANNEL_STOP", "player", "c1", 99001)
        g._ADVANCE(6)  # 34 s après le lancer : au-delà des 30 s, mais dans les 10 s de la fin de canalisation
        g._FIRE("CHAT_MSG_LOOT", fish, "", "", "", "")
        assert char.counters.gathering.fishing == 2
        # SUCCEEDED puis CHANNEL_START pour le même lancer : une seule fenêtre, pas raccourcie.
        g._FIRE("UNIT_SPELLCAST_SUCCEEDED", "player", "c2", 7620)
        g._ADVANCE(5)
        g._FIRE("UNIT_SPELLCAST_CHANNEL_START", "player", "c2", 7620)
        g._ADVANCE(20)
        g._FIRE("CHAT_MSG_LOOT", fish, "", "", "", "")
        assert char.counters.gathering.fishing == 4
        # Fenêtre passée, un sort qui n'est pas une récolte n'arme rien : le butin qui suit n'est pas compté.
        g._ADVANCE(15)
        g._FIRE("UNIT_SPELLCAST_CHANNEL_START", "player", "c3", 12345)
        g._ADVANCE(2)
        g._FIRE("CHAT_MSG_LOOT", fish, "", "", "", "")
        assert char.counters.gathering.fishing == 4 and "pas une récolte" in g._NS.GatherSource()
        # /mf api montre la lecture de la récolte.
        g.SlashCmdList.WOWFOREVERGUILDE("api")
        assert any(
            m.startswith("|cffffd100[MF]|r récolte · dernier sort 12345") for m in list(g._CHAT.values())
        )
        assert list(g.WoWForeverGuildeDB.errors.values())[-1].where == "diagnostic"

    def test_companion_seed_mark_is_kept_and_exported(self):
        # Le compagnon a complété le fichier depuis le site et y a posé sa marque : l'addon la ressort telle quelle.
        lua = boot()
        g = lua.globals()
        g._FIRE("ADDON_LOADED", "WoWForeverGuilde")
        lua.execute("""
          WoWForeverGuildeDB.characters['Player-1-000ABC01'] = {
            guid = 'Player-1-000ABC01', name = 'Thrall', counting_since = 1700000000,
            counters = { deaths = 14, kills = 120 }, journal = { ['2026-09-20'] = { deaths = 10 } },
            seed = { at = 1764000100, bases = { ['pc-fixe'] = 1763999000 } },
          }
        """)
        g._FIRE("PLAYER_LOGIN")
        g._ADVANCE(7)
        g._DIE()
        g._ADVANCE(1)
        (character,) = decode_export(logout_code(lua))["characters"]
        assert character["seed"] == {"at": 1764000100, "bases": {"pc-fixe": 1763999000}}
        assert character["counters"]["deaths"] == 15 and character["counting_since"] == 1700000000

    def test_expired_lockouts_still_disappear_when_the_read_is_empty(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute("GetNumSavedInstances = function() return 0 end")
        g._ADVANCE(300001)  # le verrou connu (réinitialisation dans 300 000 s) est passé
        payload = decode_export(logout_code(lua))
        assert payload["characters"][0]["lockouts"] == []

    def test_honorable_kills_never_decrease_and_are_counted_without_the_game_total(self):
        lua = boot()
        g = lua.globals()
        # Total du jeu pas encore chargé à la connexion.
        lua.execute("GetPVPLifetimeStats = function() return 0, 0 end")
        g._FIRE("ADDON_LOADED", "WoWForeverGuilde")
        g._FIRE("PLAYER_LOGIN")
        g._FIRE("PLAYER_PVP_KILLS_CHANGED")  # bruit de la connexion, avant la première lecture : ignoré
        g._ADVANCE(7)
        char = g.WoWForeverGuildeDB.characters["Player-1-000ABC01"]
        assert char.counters.hk is None and char.pvp.hk_lifetime is None
        # Sans total du jeu, l'addon compte lui-même.
        g._FIRE("PLAYER_PVP_KILLS_CHANGED")
        g._ADVANCE(2)
        assert char.counters.hk == 1
        # Le total du jeu répond : il fait foi.
        lua.execute("GetPVPLifetimeStats = function() return 2341, 0 end")
        g._FIRE("PLAYER_PVP_KILLS_CHANGED")
        g._ADVANCE(2)
        assert char.counters.hk == 2341 and char.pvp.hk_lifetime == 2341
        # Il retombe à zéro (déconnexion) : rien ne bouge, et on ne recompte pas par-dessus un total connu.
        lua.execute("GetPVPLifetimeStats = function() return 0, 0 end")
        g._FIRE("PLAYER_PVP_KILLS_CHANGED")
        g._ADVANCE(2)
        assert char.counters.hk == 2341
        assert decode_export(logout_code(lua))["characters"][0]["counters"]["hk"] == 2341

    def test_an_abandoned_profession_or_a_respec_still_updates(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        char = g.WoWForeverGuildeDB.characters["Player-1-000ABC01"]
        # Un métier sur deux abandonné : la lecture dit encore quelque chose, le métier disparaît bien.
        lua.execute("_PROFESSION_SLOTS = { 1 }")
        g._FIRE("SKILL_LINES_CHANGED")
        g._ADVANCE(2)
        assert list(dict(char.professions).keys()) == ["186"]
        # Points déplacés : la nouvelle répartition remplace l'ancienne.
        lua.execute("_TALENTS.ranks = { ['1-1'] = 4 }")
        g._FIRE("PLAYER_TALENT_UPDATE")
        g._ADVANCE(2)
        assert char.spec_tab == 1 and char.talents.grid["1-1-1"] == 4 and char.talents.grid["2-1-1"] is None
        # Nouvelle pièce : l'équipement suit.
        lua.execute("_GEAR = { [1] = '|Hitem:16843:0:0|h[Épaulières]|h' }")
        g._FIRE("PLAYER_EQUIPMENT_CHANGED")
        g._ADVANCE(2)
        assert char.gear.head.id == 16843 and char.gear.mainhand is None


FAKE_PINS = """
_PINS = { added = {}, removed = {} }
_NS.MapUI.UsePins({
  AddWorldMapIconMap = function(self, ref, icon, map, x, y, flag) _PINS.added[icon] = { map = map, x = x, y = y, flag = flag, icon = icon } return true end,
  RemoveWorldMapIcon = function(self, ref, icon) _PINS.added[icon] = nil table.insert(_PINS.removed, icon) end,
})
"""

JAINA = "P\t1\tPlayer-1-00000JAI\tJaina Portvaillant\tMAGE\t60\t1429\t0.6100\t0.4200\tForêt d'Elwynn\tHurlevent\tGivre 0/31/20"


def receive(lua: LuaRuntime, line: str, sender: str = "Jaina-Forever") -> None:
    lua.globals()._FIRE("CHAT_MSG_ADDON", "WFG", line, "GUILD", sender)


def garrosh_strikes_again(lua: LuaRuntime) -> None:
    """Garrosh tue Uther maintenant : une prime encaissée retombe à zéro, il lui faut une nouvelle victime."""
    now = lua.globals()._CLOCK.now
    receive(
        lua,
        f"D\t1\tPlayer-1-00000UTH\tUther\tLumière\tPALADIN\t60\tGarrosh Hurlenfer\tDurotar\t\t{now}"
        "\t1\tWARRIOR\t1411\t0.4000\t0.6000",
        "Uther-Forever",
    )


class TestPositions:
    """Partage de position : émission, réception sur la carte, infobulle, menu, règle symétrique."""

    def test_position_is_broadcast_at_login_then_on_move_zone_change_and_heartbeat(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        assert g._PREFIXES["WFG"] is True
        # Sans guilde : rien ne part, le client moderne interdit les canaux de chat aux addons.
        assert addon_sent(g) == []
        lua.execute("_GUILD = true")
        g._ADVANCE(10)
        (first,) = addon_sent(g)
        # Nom complet, classe, niveau, carte, coordonnées, zone, talents, sur le canal de guilde.
        assert (first.prefix, first.kind) == ("WFG", "GUILD")
        assert (
            first.text
            == f"P\t1\tPlayer-1-000ABC01\tThrall Fils-de-Durotan\tSHAMAN\t60\t1429\t0.5000\t0.5000\tForêt d'Elwynn\t\tAmélioration 0/8/1\t\t{toc_version()}"
        )
        # Immobile : rien de plus à la lecture suivante.
        g._ADVANCE(10)
        assert len(addon_sent(g)) == 1
        # Déplacé : nouvel envoi.
        lua.execute("_MAP.x = 0.52")
        g._ADVANCE(10)
        second = addon_sent(g)[-1]
        assert second.kind == "GUILD" and "\t0.5200\t" in second.text
        # Changement de zone : envoi 2 s plus tard, même en combat.
        lua.execute("_COMBAT = true; _ZONE = 'Marais des Chagrins'")
        g._FIRE("ZONE_CHANGED_NEW_AREA")
        g._FIRE("ZONE_CHANGED")
        g._ADVANCE(2)
        assert len(addon_sent(g)) == 3 and "Marais des Chagrins" in addon_sent(g)[-1].text
        lua.execute("_COMBAT = false")
        # Immobile : battement de cœur au bout de 60 s.
        g._ADVANCE(50)
        assert len(addon_sent(g)) == 3
        g._ADVANCE(10)
        assert len(addon_sent(g)) == 4
        # En instance (pas de coordonnées) : carte seule.
        lua.execute("_MAP.x = nil; _INSTANCE = 'party'")
        g._ADVANCE(10)
        assert addon_sent(g)[-1].text.split("\t")[6:9] == ["1429", "", ""]
        assert len(list(g.WoWForeverGuildeDB.errors.values())) == 0, list(
            g.WoWForeverGuildeDB.errors.values()
        )

    def test_received_position_becomes_a_class_colored_pin_with_tooltip_and_menu(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute(FAKE_PINS)
        receive(lua, JAINA)
        peer = g._NS.Positions.peers["Player-1-00000JAI"]
        assert (peer.name, peer["class"], peer.level, peer.sender, peer.spec) == (
            "Jaina Portvaillant",
            "MAGE",
            60,
            "Jaina-Forever",
            "Givre 0/31/20",
        )
        ((icon, pin),) = list(g._PINS.added.items())
        assert (pin.map, pin.x, pin.y, pin.flag) == (1429, 0.61, 0.42, 3)
        assert list(icon.dot.color.values()) == [0.41, 0.8, 0.94]
        # Survol : nom coloré, niveau, zone · sous-zone, talents, âge.
        g._NS.MapUI.ShowTooltip(peer, icon)
        lines = list(g.GameTooltip.lines.values())
        assert lines[0] == "|cff69ccf0Jaina Portvaillant|r  niveau 60"
        assert lines[1:4] == ["Forêt d'Elwynn · Hurlevent", "Givre 0/31/20", "à l'instant"]
        # Clic : menu Inviter / Chuchoter.
        g._NS.MapUI.OpenMenu(peer)
        menu = g.WoWForeverGuildeMenu
        row = menu.rows[1]
        assert menu.shown is True and row.invite.text == "Inviter" and row.whisper.text == "Chuchoter"
        row.invite.scripts.OnClick(row.invite)
        assert list(g._INVITED.values()) == ["Jaina-Forever"] and menu.shown is False
        g._NS.MapUI.OpenMenu(peer)
        row.whisper.scripts.OnClick(row.whisper)
        assert g._OPEN_CHAT == "/w Jaina-Forever "
        # Membre d'un groupe sans en être le chef : on suggère ; chef : on invite ; déjà ensemble : grisé.
        lua.execute("_IN_GROUP = true")
        g._NS.MapUI.OpenMenu(peer)
        assert row.invite.text == "Suggérer l'invitation" and row.invite.enabled is True
        lua.execute("_LEADER = true")
        g._NS.MapUI.OpenMenu(peer)
        assert row.invite.text == "Inviter"
        lua.execute("_PARTY['Jaina-Forever'] = true")
        g._NS.MapUI.OpenMenu(peer)
        assert row.invite.text == "Déjà dans le groupe" and row.invite.enabled is False

    def test_a_pin_created_in_combat_waits_for_the_end_of_combat_to_pass_right_clicks(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute(FAKE_PINS)
        # Une position arrive en plein combat : le point est posé, l'appel réservé attend (rien de refusé par le jeu).
        lua.execute("_COMBAT = true")
        receive(lua, JAINA)
        ((icon, _pin),) = list(g._PINS.added.items())
        assert g._BLOCKED is None and icon.passThrough is None
        lua.execute("_COMBAT = false")
        g._FIRE("PLAYER_REGEN_ENABLED")
        assert g._BLOCKED is None and icon.passThrough == "RightButton"
        # Hors combat : tout de suite. La tête de mort d'un recherché suit la même règle.
        receive(
            lua,
            f"D\t1\tPlayer-1-00000JAI\tJaina\tPortvaillant\tMAGE\t60\tGarrosh Hurlenfer\tDurotar\t\t{g._CLOCK.now}\t1\tWARRIOR\t1411\t0.4000\t0.6000",
        )
        skull = g._NS.MapUI.WantedIcons()["garrosh hurlenfer"].map
        assert skull.passThrough == "RightButton" and g._BLOCKED is None
        assert list(g.WoWForeverGuildeDB.errors.values()) == []

    def test_group_members_have_no_pin_because_the_game_already_shows_them(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute(FAKE_PINS)
        receive(lua, JAINA)
        assert len(list(g._PINS.added.items())) == 1
        # Jaina rejoint mon groupe : son point disparaît, sa position reste connue (liste « Guilde en jeu »).
        lua.execute("_PARTY['Jaina-Forever'] = true")
        g._FIRE("GROUP_ROSTER_UPDATE")
        g._FIRE("GROUP_ROSTER_UPDATE")  # en rafale : un seul rafraîchissement
        g._ADVANCE(1)
        assert list(g._PINS.added.items()) == []
        assert g._NS.Positions.peers["Player-1-00000JAI"].name == "Jaina Portvaillant"
        # Une position reçue pendant qu'on est ensemble ne repose pas de point.
        receive(lua, JAINA.replace("0.6100", "0.6200"))
        assert list(g._PINS.added.items()) == []
        # Elle quitte le groupe : le point revient, à sa dernière position.
        lua.execute("_PARTY = {}")
        g._FIRE("GROUP_ROSTER_UPDATE")
        g._ADVANCE(1)
        ((_, pin),) = list(g._PINS.added.items())
        assert pin.x == 0.62

    def test_stacked_members_share_tooltip_and_menu_rows(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute(FAKE_PINS)
        receive(lua, JAINA)
        receive(
            lua,
            JAINA.replace("Player-1-00000JAI", "Player-1-00000ART")
            .replace("Jaina Portvaillant", "Arthas Menethil")
            .replace("MAGE", "PALADIN")
            .replace("0.6100", "0.6150"),
            "Arthas-Forever",
        )
        receive(
            lua,
            JAINA.replace("Player-1-00000JAI", "Player-1-00000FAR")
            .replace("Jaina Portvaillant", "Loin Ailleurs")
            .replace("0.6100", "0.9000"),
            "Loin-Forever",
        )
        jaina = g._NS.Positions.peers["Player-1-00000JAI"]
        stacked = list(g._NS.MapUI.Stacked(jaina).values())
        assert [p.name for p in stacked] == ["Arthas Menethil", "Jaina Portvaillant"]
        g._NS.MapUI.OpenMenu(jaina)
        menu = g.WoWForeverGuildeMenu
        assert (menu.rows[1].invite.peer.name, menu.rows[2].invite.peer.name) == (
            "Arthas Menethil",
            "Jaina Portvaillant",
        )
        assert menu.rows[3].invite.shown is False

    def test_leave_message_and_silence_remove_the_pin(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute(FAKE_PINS)
        receive(lua, JAINA)
        receive(lua, "L\t1\tPlayer-1-00000JAI")
        assert g._NS.Positions.peers["Player-1-00000JAI"] is None and list(g._PINS.added.items()) == []
        receive(lua, JAINA)
        g._ADVANCE(170)
        assert g._NS.Positions.peers["Player-1-00000JAI"] is not None
        g._ADVANCE(20)
        assert g._NS.Positions.peers["Player-1-00000JAI"] is None and list(g._PINS.added.items()) == []
        # Message d'un autre préfixe ou mal formé : ignoré sans erreur.
        g._FIRE("CHAT_MSG_ADDON", "AUTRE", JAINA, "GUILD", "Jaina-Forever")
        receive(lua, "P\t2\tnope")
        receive(lua, "P\t1\t\t")
        assert list(g._NS.Positions.peers.items()) == []
        assert len(list(g.WoWForeverGuildeDB.errors.values())) == 0, list(
            g.WoWForeverGuildeDB.errors.values()
        )

    def test_not_sharing_means_not_seeing(self):
        lua = boot()
        g = lua.globals()
        lua.execute("_GUILD = true")  # les messages addon passent par le canal de guilde
        login(lua)
        lua.execute(FAKE_PINS)
        receive(lua, JAINA)
        g._NS.Positions.SetSharing(False)
        assert g.WoWForeverGuildeDB.settings.sharePosition is False
        assert addon_sent(g)[-1].text == "L\t1\tPlayer-1-000ABC01"
        assert list(g._NS.Positions.peers.items()) == [] and list(g._PINS.added.items()) == []
        assert any("Position masquée" in m for m in list(g._CHAT.values()))
        receive(lua, JAINA)
        g._ADVANCE(60)
        assert list(g._NS.Positions.peers.items()) == [] and len(addon_sent(g)) == 2
        g._NS.Positions.SetSharing(True)
        assert addon_sent(g)[-1].text.startswith("P\t1\tPlayer-1-000ABC01\t")
        # Déconnexion : on prévient les autres.
        g._FIRE("PLAYER_LOGOUT")
        assert addon_sent(g)[-1].text == "L\t1\tPlayer-1-000ABC01"

    def test_lfg_flag_travels_with_the_position_and_shows_in_tooltip_and_list(self):
        lua = boot()
        g = lua.globals()
        lua.execute("_GUILD = true")  # les messages addon passent par le canal de guilde
        login(lua)
        lua.execute(FAKE_PINS)
        g.SlashCmdList.WOWFOREVERGUILDE("lfg Gnomeregan ce soir")
        assert addon_sent(g)[-1].text.endswith("\tAmélioration 0/8/1\tGnomeregan ce soir\t" + toc_version())
        assert any("Gnomeregan ce soir" in m for m in list(g._CHAT.values()))
        receive(lua, JAINA + "\tStratholme")
        peer = g._NS.Positions.peers["Player-1-00000JAI"]
        assert peer.lfg == "Stratholme"
        g._NS.MapUI.ShowTooltip(peer, None)
        assert "cherche groupe : Stratholme" in list(g.GameTooltip.lines.values())
        g.SlashCmdList.WOWFOREVERGUILDE("lfg")
        assert g._NS.Positions.lfg is None and addon_sent(g)[-1].text.endswith(
            "\tAmélioration 0/8/1\t\t" + toc_version()
        )
        # Liste : section « Cherchent un groupe » en tête, puis les zones (la mienne d'abord), sans les hors-ligne ni moi.
        g.SlashCmdList.WOWFOREVERGUILDE("qui")
        frame = g.WoWForeverGuildeRoster
        assert frame.shown is True and g._ROSTER_REQUESTED == 1
        lines = [line.text for line in list(g._NS.RosterUI.Lines().values())]
        assert lines[0].startswith("|cffffd100Cherchent un groupe|r")
        assert "Jaina Portvaillant" in lines[1] and "Stratholme" in lines[1]
        assert lines[2].startswith("|cffffd100Forêt d'Elwynn|r |cff9a9a9a(1)|r")
        assert "Hurlevent" in lines[3] and "Givre 0/31/20" in lines[3]
        assert lines[4].startswith("|cffffd100Marais des Chagrins|r") and "Uther" in lines[5]
        assert len(lines) == 6 and not any("Absent" in line or "Thrall" in line for line in lines)
        # En colonnes : nom, niveau, sous-zone, puis ce que la position partagée ajoute ; un titre de groupe n'a
        # que son texte.
        entries = list(g._NS.RosterUI.Lines().values())
        assert entries[0].cells is None and entries[2].cells is None
        name, level, place, info = list(entries[3].cells.values())
        assert "Jaina Portvaillant" in name and "60" in level and "Hurlevent" in place
        assert "Givre 0/31/20" in info and "Stratholme" in info
        assert [h.text for h in g.WoWForeverGuildeRoster.columnHeaders.values()] == [
            "Nom",
            "Niv.",
            "Lieu",
            "Talents, groupe, alerte",
        ]
        # Ma zone seulement.
        lua.execute("WoWForeverGuildeDB.settings.rosterMyZone = true")
        lines = [line.text for line in list(g._NS.RosterUI.Lines().values())]
        assert len(lines) == 4 and not any("Uther" in line for line in lines)
        # Clic sur Uther (sans addon) : menu avec son nom de roster pour inviter.
        lua.execute("WoWForeverGuildeDB.settings.rosterMyZone = false")
        g._NS.RosterUI.Render()
        rows = [
            r for r in list(g._FRAMES.values()) if getattr(r, "member", None) and r.member.name == "Uther"
        ]
        assert "Uther" in rows[0].cells[1].text and rows[0].text.text == ""
        rows[0].scripts.OnClick(rows[0])
        menu = g.WoWForeverGuildeMenu
        assert (
            menu.shown is True
            and menu.rows[1].invite.peer.sender == "Uther-Forever"
            and menu.rows[2].invite.shown is False
        )

    def test_sos_is_manual_only_and_alerts_members_nearby(self):
        lua = boot()
        g = lua.globals()
        lua.execute("_GUILD = true")  # les messages addon passent par le canal de guilde
        login(lua)
        lua.execute(FAKE_PINS)
        sent_before = len(addon_sent(g))
        # Un joueur hostile me frappe hors instance : rien ne part tout seul (ça spammerait en zone contestée).
        lua.execute(
            "_CLEU = { 0, 'SWING_DAMAGE', false, 'Player-1-00000EVIL', 'Garrosh', 0x548, 0, 'Player-1-000ABC01', 'Thrall', 0x511, 0, 120 }"
        )
        g._FIRE("COMBAT_LOG_EVENT_UNFILTERED")
        assert len(addon_sent(g)) == sent_before
        # /mf sos avec un joueur ciblé : appel avec son nom et sa classe.
        lua.execute("_TARGET = { name = 'Garrosh', class = 'WARRIOR', player = true }")
        g.SlashCmdList.WOWFOREVERGUILDE("sos")
        sent = addon_sent(g)
        assert len(sent) == sent_before + 1
        assert (
            sent[-1].text
            == "G\t1\tPlayer-1-000ABC01\tThrall Fils-de-Durotan\tSHAMAN\t60\t1429\t0.5000\t0.5000\tForêt d'Elwynn\t\tGarrosh\tWARRIOR"
        )
        assert any("Appel à l'aide envoyé" in m for m in list(g._CHAT.values()))
        # Un seul appel par minute : le second est refusé avec le délai restant.
        g._ADVANCE(10)
        g.SlashCmdList.WOWFOREVERGUILDE("sos")
        assert len(addon_sent(g)) == len(sent)
        assert any("réessaie dans 50 s" in m for m in list(g._CHAT.values()))
        # Cible monstre ou pas de cible : appel sans agresseur. Le bouton fait la même chose que la commande.
        g._ADVANCE(51)
        lua.execute("_TARGET = { name = 'Sanglier', class = nil, player = false }")
        g._NS.Positions.SOS()
        assert addon_sent(g)[-1].text.endswith("\tForêt d'Elwynn\t\t\t")
        # Refusé sans partage de position.
        g._ADVANCE(61)
        g._NS.Positions.SetSharing(False)
        g.SlashCmdList.WOWFOREVERGUILDE("sos")
        assert any("Partager ma position" in m for m in list(g._CHAT.values()))
        g._NS.Positions.SetSharing(True)
        # Réception : même zone → toast + son + anneau rouge ; autre zone → ligne de chat seulement.
        sounds = len(list(g._SOUNDS.values()))
        receive(lua, JAINA.replace("\tGivre 0/31/20", "\tGarrosh\tWARRIOR").replace("P\t1", "G\t1"))
        peer = g._NS.Positions.peers["Player-1-00000JAI"]
        assert peer.alert.attacker == "Garrosh" and peer.alert["class"] == "WARRIOR"
        toast = g.WoWForeverGuildeDeath
        assert (
            toast.shown is True
            and "Jaina" in toast.text.text
            and "Garrosh" in toast.text.text
            and toast.header.text
            == "|TInterface\\Icons\\Ability_DualWield:14|t Appel à l'aide |TInterface\\Icons\\Ability_DualWield:14|t"
        )
        assert len(list(g._SOUNDS.values())) == sounds + 1
        ((icon, _),) = list(g._PINS.added.items())
        assert list(icon.ring.color.values()) == [1, 0.15, 0.15]
        g._NS.MapUI.ShowTooltip(peer, None)
        assert any("attaqué par" in line and "Garrosh" in line for line in list(g.GameTooltip.lines.values()))
        toast.shown = False
        receive(
            lua,
            JAINA.replace("Player-1-00000JAI", "Player-1-00000UTH")
            .replace("1429", "1431")
            .replace("\tGivre 0/31/20", "\t\t")
            .replace("P\t1", "G\t1"),
            "Uther-Forever",
        )
        assert toast.shown is False and any("Jaina" in m and "Garrosh" in m for m in list(g._CHAT.values()))
        assert any("un joueur" in m for m in list(g._CHAT.values()))
        # Alertes désactivées : silence.
        lua.execute("WoWForeverGuildeDB.settings.gankAlerts = false")
        chat = len(list(g._CHAT.values()))
        receive(lua, JAINA.replace("\tGivre 0/31/20", "\tGarrosh\tWARRIOR").replace("P\t1", "G\t1"))
        assert len(list(g._CHAT.values())) == chat
        # L'anneau redevient noir au bout de 2 min.
        g._ADVANCE(130)
        assert list(icon.ring.color.values()) == [0, 0, 0]
        assert len(list(g.WoWForeverGuildeDB.errors.values())) == 0, list(
            g.WoWForeverGuildeDB.errors.values()
        )

    def test_trace_explains_sends_receptions_and_rejections(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute("_GUILD = true")
        g.SlashCmdList.WOWFOREVERGUILDE("trace")
        g.SlashCmdList.WOWFOREVERGUILDE("sos")
        chat = list(g._CHAT.values())
        assert any("Trace des messages addon pendant 120 s" in m for m in chat)
        assert any("trace ·" in m and "envoi G → accepté" in m for m in chat)
        # Réception d'un appel, puis d'un appel ignoré (réglage), puis d'un message chuchoté.
        alert = (
            "G\t1\tPlayer-1-0099\tJaina\tMAGE\t12\t1429\t0.5000\t0.5000\tForêt d'Elwynn\t\tGarrosh\tWARRIOR"
        )
        g._FIRE("CHAT_MSG_ADDON", "WFG", alert, "GUILD", "Jaina-Forever")
        lua.execute("WoWForeverGuildeDB.settings.gankAlerts = false")
        g._FIRE("CHAT_MSG_ADDON", "WFG", alert, "GUILD", "Jaina-Forever")
        g._FIRE("CHAT_MSG_ADDON", "WFG", alert, "WHISPER", "Jaina-Forever")
        chat = list(g._CHAT.values())
        assert any("reçu G de Jaina-Forever (Jaina, carte 1429)" in m for m in chat)
        assert any("appel de Jaina ignoré" in m and "décoché" in m for m in chat)
        assert any("reçu G de Jaina-Forever : ignoré, canal WHISPER" in m for m in chat)
        # Le jeu refuse l'envoi : l'appelant le sait, avec le code.
        lua.execute(
            "C_ChatInfo.SendAddonMessage = function() return 3 end; WoWForeverGuildeDB.settings.gankAlerts = true"
        )
        g._ADVANCE(61)
        g.SlashCmdList.WOWFOREVERGUILDE("sos")
        chat = list(g._CHAT.values())
        assert any("Appel non envoyé" in m and "« 3 »" in m for m in chat)
        assert any("envoi G → 3" in m for m in chat)
        # Après le délai, silence.
        g._ADVANCE(120)
        lua.execute("_CHAT = {}")
        g._FIRE("CHAT_MSG_ADDON", "WFG", alert, "GUILD", "Jaina-Forever")
        assert not any("trace" in m for m in list(g._CHAT.values()))

    def test_minimap_dots_follow_their_setting(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute(FAKE_PINS)
        lua.execute("""
_PINS.mini = {}
local lib = _NS.MapUI
_NS.MapUI.UsePins({
  AddWorldMapIconMap = function(self, ref, icon, map, x, y, flag) _PINS.added[icon] = { map = map, x = x, y = y, flag = flag } return true end,
  RemoveWorldMapIcon = function(self, ref, icon) _PINS.added[icon] = nil end,
  AddMinimapIconMap = function(self, ref, icon, map, x, y, parent, edge) _PINS.mini[icon] = { map = map, x = x, y = y, edge = edge } end,
  RemoveMinimapIcon = function(self, ref, icon) _PINS.mini[icon] = nil end,
})
""")
        receive(lua, JAINA)
        assert len(list(g._PINS.added.items())) == 1 and len(list(g._PINS.mini.items())) == 1
        ((mini, pin),) = list(g._PINS.mini.items())
        assert (pin.map, pin.x, pin.y, pin.edge) == (1429, 0.61, 0.42, True) and list(
            mini.dot.color.values()
        ) == [0.41, 0.8, 0.94]
        g._NS.MapUI.SetMinimap(False)
        assert list(g._PINS.mini.items()) == [] and len(list(g._PINS.added.items())) == 1
        g._NS.MapUI.SetMinimap(True)
        assert len(list(g._PINS.mini.items())) == 1
        g._NS.Positions.SetSharing(False)
        assert list(g._PINS.mini.items()) == [] and list(g._PINS.added.items()) == []

    def test_review_fixes_empty_fields_untrusted_channels_and_library_refusals(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute(FAKE_PINS)
        # Un message chuchoté ou passé par un canal avec le bon préfixe est ignoré ; seule la guilde fait foi.
        g._FIRE("CHAT_MSG_ADDON", "WFG", JAINA, "WHISPER", "Jaina-Forever")
        assert list(g._NS.Positions.peers.items()) == []
        g._FIRE("CHAT_MSG_ADDON", "WFG", JAINA, "CHANNEL", "Jaina-Forever", "", 0, 5, "wfgdeaths")
        assert list(g._NS.Positions.peers.items()) == []
        receive(lua, JAINA)
        assert (
            g._NS.Positions.peers["Player-1-00000JAI"] is not None and len(list(g._PINS.added.items())) == 1
        )
        g._FIRE(
            "CHAT_MSG_ADDON",
            "WFG",
            "L\t1\tPlayer-1-00000JAI",
            "CHANNEL",
            "Jaina-Forever",
            "",
            0,
            7,
            "autrecanal",
        )
        assert g._NS.Positions.peers["Player-1-00000JAI"] is not None
        # Carte sans coordonnées après une position complète : le point disparaît, la zone reste.
        receive(
            lua,
            JAINA.replace("\t0.6100\t0.4200\t", "\t\t\t").replace(
                "Forêt d'Elwynn\tHurlevent", "Gnomeregan\t"
            ),
        )
        peer = g._NS.Positions.peers["Player-1-00000JAI"]
        assert peer.x is None and peer.zone == "Gnomeregan" and list(g._PINS.added.items()) == []
        # La bibliothèque refuse la carte : l'ancien point est retiré.
        receive(lua, JAINA)
        assert len(list(g._PINS.added.items())) == 1
        lua.execute("""
local lib = { AddWorldMapIconMap = function() return false end, RemoveWorldMapIcon = function(self, ref, icon) _PINS.added[icon] = nil end }
_NS.MapUI.UsePins(lib)
""")
        receive(lua, JAINA.replace("1429", "9999"))
        assert list(g._PINS.added.items()) == []
        # Recherche de groupe accentuée : coupée sur une frontière UTF-8, ligne valide et ≤ 255 octets.
        g._NS.Positions.SetLFG("é" * 70)
        assert g._NS.Positions.lfg == "é" * 40
        line = g._NS.Positions.Encode(g._NS.char, 1429, 0.5, 0.5)
        assert len(line.encode("utf-8")) <= 255
        assert g._NS.Positions.Cut("ab" + "é" * 3, 5) == "abé" and g._NS.Positions.Cut("abc", 5) == "abc"
        # Roster sans GUID : rapprochement par prénom seulement si la classe concorde.
        lua.execute("_ROSTER[2].guid = nil")
        receive(
            lua,
            JAINA.replace("Player-1-00000JAI", "Player-1-00000JA2").replace("MAGE", "WARRIOR"),
            "Jaina-Forever",
        )
        members = list(g._NS.Positions.Members().values())
        jainas = [m for m in members if m.name.startswith("Jaina")]
        assert len(jainas) == 2 and sorted(m["class"] for m in jainas) == ["MAGE", "WARRIOR"]
        receive(lua, "L\t1\tPlayer-1-00000JA2")
        members = list(g._NS.Positions.Members().values())
        jainas = [m for m in members if m.name.startswith("Jaina")]
        assert len(jainas) == 1 and jainas[0].peer is not None and jainas[0].sender == "Jaina-Forever"
        assert len(list(g.WoWForeverGuildeDB.errors.values())) == 0, list(
            g.WoWForeverGuildeDB.errors.values()
        )

    def test_newer_addon_version_seen_from_two_guildmates_suggests_a_reload(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute("_GUILD = true")
        uther = JAINA.replace("00000JAI", "00000UTH").replace("Jaina Portvaillant", "Uther Lumière")
        # Version égale, plus ancienne ou absente (ancien addon) : rien.
        receive(lua, JAINA + "\t\t" + toc_version())  # 13e champ : recherche de groupe vide ; 14e : version
        receive(lua, JAINA + "\t\t0.1.0")
        receive(lua, JAINA)
        assert g._POPUP is None and not any("disponible" in m for m in list(g._CHAT.values()))
        # Plus récente chez un seul guildien, même répétée : rien (une version de développement ne dérange personne).
        receive(lua, JAINA + "\t\t9.9.9")
        receive(lua, JAINA + "\t\t9.9.9")
        g._ADVANCE(60)
        assert g._POPUP is None and not any("disponible" in m for m in list(g._CHAT.values()))
        # Un second l'a aussi, mais en combat : ligne de chat tout de suite, popup remis à la sortie du combat.
        lua.execute("_COMBAT = true")
        receive(lua, uther + "\t\t9.9.9", "Uther-Forever")
        assert any("Addon 9.9.9 disponible" in m and toc_version() in m for m in list(g._CHAT.values()))
        assert g._POPUP is None
        lua.execute("_COMBAT = false")
        g._ADVANCE(60)
        assert g._POPUP.which == "WFG_UPGRADE" and "9.9.9" in g._POPUP.text and toc_version() in g._POPUP.text
        # Une seule fois par version et par session ; accepter retient la tentative puis recharge l'interface.
        g._POPUP = None
        receive(lua, JAINA + "\t\t9.9.9")
        g._ADVANCE(60)
        assert g._POPUP is None and g.WoWForeverGuildeDB.upgradeTried is None
        g.StaticPopupDialogs.WFG_UPGRADE.OnAccept()
        assert g._RELOADED is True
        tried = g.WoWForeverGuildeDB.upgradeTried
        assert (tried.version, tried.n, tried.t) == ("9.9.9", 1, g._CLOCK.now)
        assert g._NS.VersionNewer("0.10.0", "0.9.9") and not g._NS.VersionNewer("dev", "0.6.1")
        assert not g._NS.VersionNewer("0.6.1", "0.6.1") and g._NS.VersionNewer("1.0", "0.9.9.9")
        # Deux guildiens à des versions différentes : celle que les deux ont atteinte.
        lua = boot()
        g = lua.globals()
        login(lua)
        receive(lua, JAINA + "\t\t9.9.9")
        receive(lua, uther + "\t\t9.9.8", "Uther-Forever")
        assert any("Addon 9.9.8 disponible" in m for m in list(g._CHAT.values()))
        assert not any("Addon 9.9.9" in m for m in list(g._CHAT.values()))

    def test_reload_that_changed_nothing_does_not_ask_again_forever(self):
        uther = JAINA.replace("00000JAI", "00000UTH").replace("Jaina Portvaillant", "Uther Lumière")

        def session(count, age):
            """Une session qui commence après `count` rechargements restés sans effet, le dernier il y a `age` s."""
            lua = boot()
            g = lua.globals()
            tried = lua.table(version="9.9.9", n=count, t=g._CLOCK.now - age)
            g.WoWForeverGuildeDB = lua.table(upgradeTried=tried)
            login(lua)
            receive(lua, JAINA + "\t\t9.9.9")
            receive(lua, uther + "\t\t9.9.9", "Uther-Forever")
            return lua, g

        # J'ai rechargé pour la 9.9.9 il y a une minute et je suis toujours en retard : pas de popup, une ligne qui
        # dit quoi faire, une seule fois.
        lua, g = session(1, 60)
        receive(lua, JAINA + "\t\t9.9.9")
        missing = [m for m in list(g._CHAT.values()) if "toujours pas sur ce PC" in m]
        assert len(missing) == 1 and "9.9.9" in missing[0] and "Vérifier les mises à jour" in missing[0]
        g._ADVANCE(10 * 60)
        assert g._POPUP is None
        # Un quart d'heure après, le compagnon a pu arriver : une seconde proposition, la dernière.
        g._ADVANCE(6 * 60)
        assert g._POPUP.which == "WFG_UPGRADE" and "9.9.9" in g._POPUP.text
        g.StaticPopupDialogs.WFG_UPGRADE.OnAccept(None, "9.9.9")
        assert g.WoWForeverGuildeDB.upgradeTried.n == 2
        # Deux rechargements sans effet : plus de popup pour cette version, quelle que soit l'attente.
        lua, g = session(2, 10**6)
        g._ADVANCE(3600)
        assert g._POPUP is None and any("toujours pas sur ce PC" in m for m in list(g._CHAT.values()))
        # Une version encore plus récente repart de zéro.
        receive(lua, JAINA + "\t\t10.0.0")
        receive(lua, uther + "\t\t10.0.0", "Uther-Forever")
        g._ADVANCE(60)
        assert g._POPUP.which == "WFG_UPGRADE" and "10.0.0" in g._POPUP.text
        assert list(g.WoWForeverGuildeDB.errors.values()) == []

    def test_version_comes_from_the_code_not_from_the_toc_the_game_loaded(self):
        # Le client ne lit le .toc qu'à son lancement : après une mise à jour copiée jeu ouvert puis /reload, le
        # nouveau code tourne avec l'ancien .toc en mémoire. Le code porte donc sa version, égale à celle du .toc.
        source = (ADDON_DIR / "Core.lua").read_text(encoding="utf-8")
        assert re.search(r'^local CODE_VERSION = "(.+)"$', source, re.M).group(1) == toc_version()
        lua = boot()
        g = lua.globals()
        g._NS.TOC_VERSION = "0.0.1"  # ce que le jeu a lu à son lancement, avant la mise à jour
        g.WoWForeverGuildeDB = lua.table(upgradeTried=lua.table(version=toc_version(), n=1, t=1))
        login(lua)
        assert toc_version() == g._NS.VERSION
        # La version attendue est là : la tentative est oubliée, et l'addon ne se croit pas en retard.
        assert g.WoWForeverGuildeDB.upgradeTried is None
        receive(lua, JAINA + "\t\t" + toc_version())
        receive(
            lua,
            JAINA.replace("00000JAI", "00000UTH").replace("Jaina Portvaillant", "Uther Lumière")
            + "\t\t"
            + toc_version(),
            "Uther-Forever",
        )
        g._ADVANCE(60)
        assert g._POPUP is None and not any("disponible" in m for m in list(g._CHAT.values()))
        # Il dit seulement de relancer le jeu, qui n'a pas relu la liste des fichiers.
        assert any("relance le jeu" in m and "0.0.1" in m for m in list(g._CHAT.values()))
        # Jeu relancé : plus rien à dire.
        lua = boot()
        login(lua)
        assert not any("relance le jeu" in m for m in list(lua.globals()._CHAT.values()))

    def test_position_line_stays_under_255_bytes_and_still_decodes(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute("_SUBZONE = string.rep('Sous-zone interminable ', 12)")
        line = g._NS.Positions.Encode(g._NS.char, 1429, 0.123456, 0.5)
        assert len(line.encode("utf-8")) <= 255
        msg = g._NS.Positions.Decode(line)
        assert (msg.guid, msg.map, msg.x, msg.sub, msg.spec) == (
            "Player-1-000ABC01",
            1429,
            0.1235,
            "",
            "Amélioration 0/8/1",
        )


class TestWanted:
    """Têtes mises à prix : un joueur qui tue un membre prend un point, dernière position sur la carte 5 min."""

    def test_death_by_a_player_never_targeted_is_recognised_from_the_units_around(self):
        # Un voleur sorti de nulle part : jamais ciblé, mais sa plaque de nom est encore là quand on lit le récapitulatif.
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute("""
          _GUILD = true
          _RECAPS = { [1] = { { sourceName = 'Garrosh Hurlenfer', amount = 900 } } }
          C_DeathInfo = { GetDeathRecapEvents = function(id) return _RECAPS[id] end }
          _UNITS = { nameplate3 = { name = 'Garrosh Hurlenfer', class = 'WARRIOR', hostile = true, player = true } }
        """)
        g._DIE()
        g._ADVANCE(1)
        (line,) = [s.text for s in addon_sent(g) if s.text.startswith("D\t")]
        fields = line.split("\t")
        assert fields[7] == "Garrosh Hurlenfer" and fields[11:13] == ["1", "WARRIOR"]
        assert g._NS.DeathSource() == "tueur d'après récap (récap présent), joueur oui d'après autour"
        assert g.WoWForeverGuildeDB.wanted["garrosh hurlenfer"].points == 1
        # Une créature autour qui porte le nom du récapitulatif : pas un joueur, pas de Wanted.
        lua.execute("""
          _RECAPS[2] = { { sourceName = 'Sanglier des Tarides', amount = 300 } }
          _UNITS = { nameplate1 = { name = 'Sanglier des Tarides', hostile = true } }
        """)
        g._DIE()
        g._ADVANCE(1)
        line = [s.text for s in addon_sent(g) if s.text.startswith("D\t")][-1]
        assert line.split("\t")[11:13] == ["0", ""]
        assert g._NS.DeathSource() == "tueur d'après récap (récap présent), joueur non d'après autour"
        assert "sanglier des tarides" not in [k for k in g.WoWForeverGuildeDB.wanted]

    def test_death_by_a_player_seen_before_the_fight_is_wanted_even_if_names_were_secret(self):
        # Sa plaque de nom est passée hors combat (lisible) ; en combat la cible est secrète ; le récapitulatif ne donne
        # que son prénom. Le joueur vu dans les 10 dernières minutes est reconnu.
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute("""
          _GUILD = true
          _UNITS = { nameplate1 = { name = 'Garrosh Hurlenfer', class = 'WARRIOR', hostile = true, player = true } }
        """)
        g._FIRE("NAME_PLATE_UNIT_ADDED", "nameplate1")
        lua.execute("_UNITS = {}; _TARGET = { name = _SECRET, hostile = true }")
        g._FIRE("PLAYER_REGEN_DISABLED")
        g._FIRE("PLAYER_TARGET_CHANGED")
        lua.execute("""
          _RECAPS = { [1] = { { sourceName = 'Garrosh', amount = 900 } } }
          C_DeathInfo = { GetDeathRecapEvents = function(id) return _RECAPS[id] end }
        """)
        g._DIE()
        lua.execute("_TARGET = nil")
        g._ADVANCE(1)
        (line,) = [s.text for s in addon_sent(g) if s.text.startswith("D\t")]
        fields = line.split("\t")
        assert fields[7] == "Garrosh" and fields[11:13] == ["1", "WARRIOR"]
        assert g._NS.DeathSource() == "tueur d'après récap (récap présent), joueur oui d'après joueur vu"
        assert list(g.WoWForeverGuildeDB.errors.values()) == []
        # Vu il y a plus de dix minutes : oublié, le tueur redevient inconnu.
        lua.execute("_RECAPS[2] = _RECAPS[1]")
        g._ADVANCE(601)
        g._DIE()
        g._ADVANCE(1)
        line = [s.text for s in addon_sent(g) if s.text.startswith("D\t")][-1]
        assert line.split("\t")[11:13] == ["0", ""]
        assert g._NS.DeathSource() == "tueur d'après récap (récap présent), joueur inconnu"

    def test_death_keeps_the_remembered_player_when_the_client_clears_the_target(self):
        # Ciblé hors combat, puis le client vide la cible à la mort et il n'y a pas de récapitulatif : le souvenir
        # donne le tueur ET dit que c'est un joueur.
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute(
            "_GUILD = true; _TARGET = { name = 'Garrosh Hurlenfer', class = 'WARRIOR', hostile = true, player = true }"
        )
        g._FIRE("PLAYER_TARGET_CHANGED")
        lua.execute("_TARGET = nil")
        g._DIE()
        g._ADVANCE(1)
        (line,) = [s.text for s in addon_sent(g) if s.text.startswith("D\t")]
        fields = line.split("\t")
        assert fields[7] == "Garrosh Hurlenfer" and fields[11:13] == ["1", "WARRIOR"]
        assert g._NS.DeathSource() == "tueur d'après mémoire (récap absent), joueur oui d'après mémoire"
        assert g.WoWForeverGuildeDB.wanted["garrosh hurlenfer"].points == 1

    def test_one_death_is_announced_once_and_the_pvp_notice_wins(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        now = g._CLOCK.now
        pve = f"D	1	Player-1-00000JAI	Jaina	Portvaillant	MAGE	60	Sanglier des Tarides	Durotar		{now}	0		1411	0.4000	0.6000"
        pvp = f"D	1	Player-1-00000JAI	Jaina	Portvaillant	MAGE	60	Garrosh Hurlenfer	Durotar		{now + 5}	1	MAGE	1411	0.4000	0.6000"
        sounds = lambda: len(list(g._SOUNDS.values()))  # noqa: E731
        # Un ancien addon annonce deux fois la même mort, PvE puis PvP : l'avis WANTED remplace l'autre, un point.
        receive(lua, pve)
        toast = g.WoWForeverGuildeDeath
        assert "WANTED" not in toast.header.text and sounds() == 1
        receive(lua, pvp)
        assert "WANTED" in toast.header.text and sounds() == 2
        assert g.WoWForeverGuildeDB.wanted["garrosh hurlenfer"].points == 1
        # Tout ce qui suit dans la minute est un doublon : ni popup, ni point (PvE comme PvP).
        receive(lua, pve)
        receive(lua, pvp.replace(str(now + 5), str(now + 9)))
        assert "WANTED" in toast.header.text and sounds() == 2
        assert g.WoWForeverGuildeDB.wanted["garrosh hurlenfer"].points == 1
        # Une minute plus tard, c'est une autre mort.
        g._ADVANCE(60)
        receive(lua, pvp.replace(str(now + 5), str(now + 70)))
        assert sounds() == 3 and g.WoWForeverGuildeDB.wanted["garrosh hurlenfer"].points == 2
        # À l'envoi : un second PLAYER_DEAD sans retour à la vie ne compte ni n'annonce rien.
        lua.execute("_GUILD = true")
        char = g._NS.char
        deaths = char.counters.deaths or 0
        g._DIE()
        g._FIRE("PLAYER_DEAD")
        g._ADVANCE(1)
        assert char.counters.deaths == deaths + 1
        assert len([s for s in addon_sent(g) if s.text.startswith("D	")]) == 1
        lua.execute("_UNITS.player = { name = 'Thrall', dead = true }")
        g._FIRE("PLAYER_ALIVE")  # esprit libéré : toujours mort
        g._FIRE("PLAYER_DEAD")
        assert char.counters.deaths == deaths + 1
        lua.execute("_UNITS.player = nil")
        g._FIRE("PLAYER_ALIVE")  # ressuscité sur place : la mort suivante compte
        g._FIRE("PLAYER_DEAD")
        assert char.counters.deaths == deaths + 2

    def test_pvp_death_notice_always_says_wanted_and_colors_the_killer(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute("WoWForeverGuildeDB.settings.wantedAlerts = false")
        now = g._CLOCK.now
        pvp = f"D\t1\tPlayer-1-00000JAI\tJaina\tPortvaillant\tMAGE\t60\tGarrosh Hurlenfer\tDurotar\t\t{now}\t1\tMAGE\t1411\t0.4000\t0.6000"
        receive(lua, pvp)
        toast = g.WoWForeverGuildeDeath
        # Alertes Wanted coupées : l'avis dit quand même WANTED et « mort en PvP », sans la prime ; tueur coloré
        # à sa classe ; la phrase vient du même lot que les morts PvE.
        assert toast.shown is True and "WANTED" in toast.header.text
        assert toast.footer.text == "Niveau 60 · Mage · Durotar · mort en PvP"
        assert "|cff69ccf0Jaina|r" in toast.text.text and "|cff69ccf0Garrosh Hurlenfer|r" in toast.text.text
        assert g.WoWForeverGuildeDB.wanted["garrosh hurlenfer"].points == 1
        assert not any("Wanted :" in m for m in list(g._CHAT.values()))
        # Alertes actives : la prime remplace la mention.
        lua.execute("WoWForeverGuildeDB.settings.wantedAlerts = true")
        toast.shown = False  # le popup précédent a fait son temps
        receive(lua, pvp.replace("00000JAI", "00000JA2"))
        assert "WANTED" in toast.header.text
        assert toast.footer.text == "Niveau 60 · Mage · Durotar · prime de 2 points sur Garrosh Hurlenfer"
        # Mort PvE : ni WANTED ni couleur sur la créature.
        pve = f"D\t1\tPlayer-1-00000JAI\tJaina\tPortvaillant\tMAGE\t60\tSanglier des Tarides\tDurotar\t\t{now}\t0\t\t1411\t0.4000\t0.6000"
        g._ADVANCE(60)  # une autre mort : dans la minute, l'annonce PvE d'un mort PvP serait un doublon
        receive(lua, pve)
        assert "WANTED" not in toast.header.text and toast.footer.text == "Niveau 60 · Mage · Durotar"
        assert "|cff69ccf0Jaina|r" in toast.text.text and "|cffffffffSanglier" not in toast.text.text

    def test_battlegrounds_and_arenas_neither_announce_deaths_nor_count_wanted(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute("""
          _GUILD = true
          _INSTANCE = 'pvp'; _INSTANCE_NAME = 'Goulet des Chanteguerres'
          _TARGET = { name = 'Garrosh Hurlenfer', class = 'WARRIOR', hostile = true, player = true }
        """)
        g._FIRE("PLAYER_TARGET_CHANGED")
        g._DIE()
        g._ADVANCE(1)
        # La mort compte au journal, mais rien ne part, l'événement n'a pas de tueur joueur, le tableau reste vide.
        assert g._NS.char.counters.deaths == 1
        assert [s.text for s in addon_sent(g) if s.text.startswith("D\t")] == []
        death = [e for e in g._NS.char.events.values() if e.k == "death"][-1]
        assert death.player is None and death.kclass is None
        assert g._NS.DeathSource() == "mort en champ de bataille ou en arène : ni annonce, ni Wanted"
        assert list(g.WoWForeverGuildeDB.wanted.keys()) == []
        # Une victoire honorable en champ de bataille : le kill compte (événement marqué `bg`), mais ni prime, ni
        # tableau Wanted, ni message « K ».
        g._FIRE(
            "CHAT_MSG_COMBAT_HONOR_GAIN",
            "Garrosh meurt, victoire honorable Rang : Grunt (Points d'honneur estimés : 198)",
        )
        assert (g._NS.char.counters.pk, g._NS.char.counters.bounty) == (1, None)
        (pk,) = [e for e in g._NS.char.events.values() if e.k == "pk"]
        assert (pk.name, pk.prime, pk.bg) == ("Garrosh", 0, True)
        assert list(g.WoWForeverGuildeDB.wanted.keys()) == []
        assert [s.text for s in addon_sent(g) if s.text.startswith("K\t")] == []
        # De retour dehors, tout reprend (plus tard : deux kills du même nom dans la fenêtre ne comptent qu'une fois).
        lua.execute("_INSTANCE = nil; _INSTANCE_NAME = nil")
        g._ADVANCE(5)
        g._FIRE(
            "CHAT_MSG_COMBAT_HONOR_GAIN",
            "Garrosh meurt, victoire honorable Rang : Grunt (Points d'honneur estimés : 198)",
        )
        assert g._NS.char.counters.pk == 2
        assert [e for e in g._NS.char.events.values() if e.k == "pk"][-1].bg is None
        g._DIE()
        lua.execute("_TARGET = nil")
        g._ADVANCE(1)
        (line,) = [s.text for s in addon_sent(g) if s.text.startswith("D\t")]
        assert line.split("\t")[11:13] == ["1", "WARRIOR"]

    def test_death_by_a_player_marks_him_wanted_with_his_last_position(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute(FAKE_PINS)
        lua.execute("""
          _GUILD = true
          _MAP = { id = 1429, x = 0.25, y = 0.75 }
          _TARGET = { name = 'Garrosh Hurlenfer', class = 'WARRIOR', hostile = true, player = true }
        """)
        g._FIRE("PLAYER_TARGET_CHANGED")
        g._DIE()
        lua.execute("_TARGET = nil")
        g._ADVANCE(1)
        # La ligne « D » porte, après les neuf champs d'origine : tueur joueur, sa classe, carte, x, y du mort.
        (line,) = [s.text for s in addon_sent(g) if s.text.startswith("D\t")]
        fields = line.split("\t")
        assert fields[7:10] == ["Garrosh Hurlenfer", "Forêt d'Elwynn", ""]
        assert fields[11:] == ["1", "WARRIOR", "1429", "0.2500", "0.7500"]
        death = [e for e in g._NS.char.events.values() if e.k == "death"][-1]
        assert (death.player, death.kclass, death.map, death.x, death.y) == (
            True,
            "WARRIOR",
            1429,
            0.25,
            0.75,
        )
        # Ma propre mort nourrit mon tableau tout de suite ; l'écho de mon message est un doublon.
        entry = g.WoWForeverGuildeDB.wanted["garrosh hurlenfer"]
        assert (entry.name, entry["class"], entry.points, entry.kills) == (
            "Garrosh Hurlenfer",
            "WARRIOR",
            1,
            0,
        )
        assert (entry.last.victim, entry.last.map, entry.last.x, entry.last.zone) == (
            "Thrall",
            1429,
            0.25,
            "Forêt d'Elwynn",
        )
        assert any(
            "Wanted :" in m and "Garrosh Hurlenfer" in m and "Prime portée à 1" in m
            for m in list(g._CHAT.values())
        )
        receive(lua, line, "Thrall-Forever")
        assert entry.points == 1 and len(list(entry.victims.values())) == 1
        # L'avis de décès porte la prime : un seul cadre flottant, pas deux.
        toast = g.WoWForeverGuildeDeath
        assert toast.shown is True and "WANTED" in toast.header.text
        assert (
            toast.footer.text
            == "Niveau 60 · Chaman · Forêt d'Elwynn · prime de 1 point sur Garrosh Hurlenfer"
        )
        # Tête de mort rouge sur la carte, là où il a frappé, avec la prime en chiffre.
        ((icon, pin),) = list(g._PINS.added.items())
        assert (pin.map, pin.x, pin.y) == (1429, 0.25, 0.75)
        assert icon.points.text == "1" and icon.alpha > 0.99
        assert icon.skull.texture == "Interface\\TargetingFrame\\UI-RaidTargetingIcons"
        # Il tue Jaina ailleurs : la prime monte (jamais remise à zéro), la tête de mort suit la dernière victime.
        jaina = f"D\t1\tPlayer-1-00000JAI\tJaina\tPortvaillant\tMAGE\t60\tGarrosh Hurlenfer\tDurotar\tOrgrimmar\t{g._CLOCK.now}\t1\tWARRIOR\t1411\t0.4000\t0.6000"
        toast.shown = False  # le popup précédent a fait son temps
        receive(lua, jaina)
        assert entry.points == 2 and len(list(entry.victims.values())) == 2
        assert (entry.last.victim, entry.last.map) == ("Jaina", 1411)
        ((icon, pin),) = list(g._PINS.added.items())
        assert (pin.map, pin.x, pin.y) == (1411, 0.4, 0.6) and icon.points.text == "2"
        assert toast.footer.text == "Niveau 60 · Mage · Durotar · prime de 2 points sur Garrosh Hurlenfer"
        g._NS.MapUI.ShowWantedTooltip(entry, icon)
        lines = list(g.GameTooltip.lines.values())
        assert lines[0] == "|cffffffffGarrosh Hurlenfer|r  WANTED"
        assert lines[1:5] == [
            "WARRIOR · prime de 2 points",
            "a tué |cff69ccf0Jaina|r ici · à l'instant",
            "Durotar · Orgrimmar",
            "Victimes : Jaina, Thrall",
        ]
        # Ancienne version en face (neuf champs) ou créature : avis de décès ordinaire, pas de prime.
        toast.shown = False  # le popup précédent a fait son temps
        receive(
            lua,
            f"D\t1\tPlayer-1-00000UTH\tUther\tLumière\tPALADIN\t58\tGarrosh Hurlenfer\tMarais\t\t{g._CLOCK.now}",
            "Uther-Forever",
        )
        assert (
            entry.points == 2
            and "WANTED" not in toast.header.text
            and toast.footer.text == "Niveau 58 · PALADIN · Marais"
        )
        receive(
            lua,
            f"D\t1\tPlayer-1-00000UTH\tUther\tLumière\tPALADIN\t58\tSanglier\tMarais\t\t{g._CLOCK.now}\t0\t\t1429\t0.1000\t0.1000",
            "Uther-Forever",
        )
        assert "sanglier" not in dict(g.WoWForeverGuildeDB.wanted)
        # Fenêtre /mf wanted : une ligne par ennemi, prime décroissante.
        g.SlashCmdList.WOWFOREVERGUILDE("wanted")
        assert g.WoWForeverGuildeWanted.shown is True
        rows = list(g._NS.WantedUI.Lines().values())
        assert (
            len(rows) == 2
            and "Garrosh Hurlenfer" in rows[1].text
            and "prime de 2 points" in rows[1].text
            and "Jaina" in rows[1].text
        )
        # En colonnes : tête mise à prix, classe, prime, kills de la guilde, dernier fait, âge.
        assert rows[0].cells is None
        name, _, prime, killed, last, when = list(rows[1].cells.values())
        assert "Garrosh Hurlenfer" in name and "2 points" in prime and killed == ""
        assert "a tué" in last and "Jaina" in last and "Durotar" in last and when != ""
        assert [h.text for h in g.WoWForeverGuildeWanted.columnHeaders.values()] == [
            "Tête mise à prix",
            "Classe",
            "Prime",
            "Abattu",
            "Dernier fait",
            "Quand",
        ]
        # Cinq minutes plus tard la tête de mort a disparu ; la prime, elle, reste.
        g._ADVANCE(301)
        assert list(g._PINS.added.items()) == [] and entry.points == 2
        # Alertes Wanted décochées : ni prime dans l'avis, ni tête de mort, mais l'avis dit quand même WANTED (mort
        # PvP) ; recochées : la tête de mort revient si encore fraîche.
        g._NS.Wanted.SetAlerts(False)
        receive(
            lua,
            f"D\t1\tPlayer-1-00000JAI\tJaina\tPortvaillant\tMAGE\t60\tGarrosh Hurlenfer\tDurotar\t\t{g._CLOCK.now}\t1\tWARRIOR\t1411\t0.5000\t0.5000",
        )
        assert entry.points == 3 and list(g._PINS.added.items()) == [] and "WANTED" in toast.header.text
        assert toast.footer.text == "Niveau 60 · Mage · Durotar · mort en PvP"
        g._NS.Wanted.SetAlerts(True)
        assert len(list(g._PINS.added.items())) == 1
        # L'export porte les nouveaux champs de la mort ; le tableau Wanted reste local (le site le recalcule).
        payload = decode_export(logout_code(lua))
        death = next(e for e in payload["characters"][0]["events"] if e["k"] == "death")
        assert (death["player"], death["kclass"], death["map"], death["x"], death["y"]) == (
            True,
            "WARRIOR",
            1429,
            0.25,
            0.75,
        )
        assert "wanted" not in payload and list(g.WoWForeverGuildeDB.errors.values()) == []

    def test_death_line_drops_subzone_then_zone_to_stay_under_255_bytes(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute("""
          _GUILD = true
          _SUBZONE = string.rep('Sous-zone interminable ', 12)
          _TARGET = { name = 'Garrosh Hurlenfer', class = 'WARRIOR', hostile = true, player = true }
        """)
        g._DIE()
        g._ADVANCE(1)
        (line,) = [s.text for s in addon_sent(g) if s.text.startswith("D\t")]
        assert len(line.encode("utf-8")) <= 255
        info = g._NS.ParseDeathLine(line)
        assert (info.zone, info.sub, info.player, info.kclass, info.map) == (
            "Forêt d'Elwynn",
            "",
            True,
            "WARRIOR",
            1429,
        )


class TestWantedKills:
    """Lot 2 : kills par la guilde (message de victoire honorable), message « K », poignée de main « W »."""

    def test_bounty_popup_shows_even_with_wanted_alerts_off(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute("_GUILD = true; WoWForeverGuildeDB.settings.wantedAlerts = false")
        receive(
            lua,
            f"D	1	Player-1-00000JAI	Jaina	Portvaillant	MAGE	60	Garrosh Hurlenfer	Durotar		{g._CLOCK.now}	1	WARRIOR	1411	0.4000	0.6000",
        )
        toast = g.WoWForeverGuildeDeath
        toast.shown = False
        chat_before = len(list(g._CHAT.values()))
        g._FIRE(
            "CHAT_MSG_COMBAT_HONOR_GAIN",
            "Garrosh meurt, victoire honorable Rang : Grunt (Points d'honneur estimés : 198)",
        )
        # Mon kill : popup or « Prime encaissée », sans ligne de chat.
        assert toast.shown is True and "Prime encaissée" in toast.header.text
        assert toast.footer.text.startswith("Prime de 1 point · ")
        assert (
            "|cff0070ddThrall Fils-de-Durotan|r" in toast.text.text and "Garrosh Hurlenfer" in toast.text.text
        )
        assert not any("Prime encaissée :" in m for m in list(g._CHAT.values())[chat_before:])
        # Le « K » d'un guildien pour un autre recherché : popup aussi.
        toast.shown = False
        receive(
            lua,
            f"K	1	Player-1-00000UTH	Uther Lumière	PALADIN	Vol'jin	3	1	{g._CLOCK.now}	1411	0.1000	0.2000	Durotar	Orgrimmar	SHAMAN",
            "Uther-Forever",
        )
        assert toast.shown is True and "Vol'jin" in toast.text.text
        assert toast.footer.text == "Prime de 3 points · Durotar"
        assert list(g.WoWForeverGuildeDB.errors.values()) == []

    def test_honorable_kill_is_read_from_the_retail_strings_links_and_unknown_messages(self):
        # Chaînes du client 12.0 (frFR), nom en lien de joueur, message des points reçus (même événement, pas un kill),
        # message d'une forme inconnue qui nomme un recherché.
        lua = boot()
        g = lua.globals()
        lua.execute("""
          COMBATLOG_HONORGAIN = "%s meurt (victoire honorable : %s). Vous gagnez %d points d’honneur."
          COMBATLOG_HONORGAIN_NO_RANK = "%s meurt (victoire honorable). Vous gagnez %d points d’honneur."
          COMBATLOG_HONORGAIN_EXHAUSTION1 = "%s meurt (victoire honorable : %s). Vous gagnez %d points d’honneur (bonus de %s de %s)."
        """)
        login(lua)
        lua.execute("_GUILD = true")
        receive(
            lua,
            f"D\t1\tPlayer-1-00000JAI\tJaina\tPortvaillant\tMAGE\t60\tGarrosh Hurlenfer\tDurotar\t\t{g._CLOCK.now}\t1\tWARRIOR\t1411\t0.4000\t0.6000",
        )
        entry = g.WoWForeverGuildeDB.wanted["garrosh hurlenfer"]
        char = g._NS.char
        patterns = list(g._NS.Wanted.HonorPatterns().values())
        assert (
            patterns[0] == "^(.-) meurt %(victoire honorable : "
            and patterns[1] == "^(.-) meurt %(victoire honorable%)%. Vous gagnez "
        )
        assert g._NS.Wanted.HonorSource() == "aucun message cette session · victoires honorables lues : 2340"
        g._FIRE(
            "CHAT_MSG_COMBAT_HONOR_GAIN",
            "|Hplayer:Garrosh Hurlenfer|h[Garrosh Hurlenfer]|h meurt (victoire honorable : Grunt). Vous gagnez 15 points d’honneur.",
        )
        assert (entry.kills, char.counters.pk, char.counters.bounty) == (1, 1, 1)
        assert g._NS.Wanted.HonorSource() == (
            "dernier message « Garrosh Hurlenfer meurt (victoire honorable : Grunt). Vous gagnez 15 points d’honneur. »"
            " → Garrosh Hurlenfer (motif) · victoires honorables lues : 2340"
        )
        g._FIRE(
            "CHAT_MSG_COMBAT_HONOR_GAIN",
            "Sylvanas meurt (victoire honorable). Vous gagnez 12 points d’honneur.",
        )
        assert char.counters.pk == 2
        # Les points reçus arrivent par le même événement : pas un kill.
        g._FIRE("CHAT_MSG_COMBAT_HONOR_GAIN", "Vous avez reçu 27 points d’honneur.")
        assert char.counters.pk == 2
        assert g._NS.Wanted.HonorSource().endswith(
            "→ aucun joueur reconnu · victoires honorables lues : 2340"
        )
        # Forme inconnue : le seul recherché nommé compte ; nommé par son prénom aussi ; un inconnu, non.
        g._ADVANCE(61)
        garrosh_strikes_again(lua)
        g._FIRE("CHAT_MSG_COMBAT_HONOR_GAIN", "Honneur : Garrosh Hurlenfer tombe sous vos coups (+14).")
        assert (entry.kills, char.counters.pk) == (2, 3)
        assert g._NS.Wanted.HonorSource().endswith(
            "→ Garrosh Hurlenfer (recherché) · victoires honorables lues : 2340"
        )
        g._FIRE("CHAT_MSG_COMBAT_HONOR_GAIN", "Honneur : Sylvanas tombe sous vos coups (+14).")
        assert char.counters.pk == 3
        # Message secret : rien, mais /mf api le dit.
        lua.execute("_FIRE('CHAT_MSG_COMBAT_HONOR_GAIN', _SECRET)")
        assert char.counters.pk == 3 and g._NS.Wanted.HonorSource().startswith("dernier message « (secret) »")
        assert list(g.WoWForeverGuildeDB.errors.values()) == []

    def test_kill_counter_is_a_safety_net_when_the_honor_message_is_missing(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute("_GUILD = true")
        receive(
            lua,
            f"D\t1\tPlayer-1-00000JAI\tJaina\tPortvaillant\tMAGE\t60\tGarrosh Hurlenfer\tDurotar\t\t{g._CLOCK.now}\t1\tWARRIOR\t1411\t0.4000\t0.6000",
        )
        entry = g.WoWForeverGuildeDB.wanted["garrosh hurlenfer"]
        char = g._NS.char
        # Le compteur bouge, aucun message : après le délai, le kill compte, nommé d'après la cible morte.
        lua.execute(
            "_TARGET = { name = 'Garrosh Hurlenfer', class = 'WARRIOR', hostile = true, player = true, dead = true }; _HK = 2341"
        )
        g._FIRE("PLAYER_PVP_KILLS_CHANGED")
        lua.execute("_TARGET = nil")
        assert (char.counters.pk or 0) == 0
        g._ADVANCE(3)
        assert (entry.kills, char.counters.pk, char.counters.bounty) == (1, 1, 1)
        assert [e for e in char.events.values() if e.k == "pk"][-1].name == "Garrosh Hurlenfer"
        assert len(wanted_sent(g, "K")) == 1
        assert g._NS.Wanted.HonorSource() == (
            "dernier message « (aucun message), victoires honorables 2340 → 2341 » → Garrosh Hurlenfer (compteur)"
            " · victoires honorables lues : 2341"
        )
        # Message et compteur pour le même kill : une fois, dans les deux ordres.
        g._ADVANCE(61)
        garrosh_strikes_again(lua)
        g._FIRE(
            "CHAT_MSG_COMBAT_HONOR_GAIN",
            "Garrosh meurt, victoire honorable Rang : Grunt (Points d'honneur estimés : 198)",
        )
        lua.execute("_HK = 2342")
        g._FIRE("PLAYER_PVP_KILLS_CHANGED")
        g._ADVANCE(3)
        assert (entry.kills, char.counters.pk) == (2, 2)
        g._ADVANCE(61)
        garrosh_strikes_again(lua)
        lua.execute("_HK = 2343")
        g._FIRE("PLAYER_PVP_KILLS_CHANGED")
        g._ADVANCE(1)
        g._FIRE(
            "CHAT_MSG_COMBAT_HONOR_GAIN",
            "Garrosh meurt, victoire honorable Rang : Grunt (Points d'honneur estimés : 198)",
        )
        g._ADVANCE(3)
        assert (entry.kills, char.counters.pk) == (3, 3)
        # Un message d'une forme inconnue qui ne nomme personne, puis le compteur : le kill compte, sans nom (pas de Wanted).
        g._ADVANCE(61)
        g._FIRE("CHAT_MSG_COMBAT_HONOR_GAIN", "Vous avez vaincu un adversaire.")
        lua.execute("_HK = 2344")
        g._FIRE("PLAYER_PVP_KILLS_CHANGED")
        g._ADVANCE(3)
        assert (entry.kills, char.counters.pk) == (3, 4)
        last = [e for e in char.events.values() if e.k == "pk"][-1]
        assert (last.name, last.prime) == ("", 0)
        assert g._NS.Wanted.HonorSource().startswith(
            "dernier message « Vous avez vaincu un adversaire., victoires honorables 2343 → 2344 » → aucun joueur reconnu"
        )
        # Une cible morte alliée ne nomme pas le kill.
        g._ADVANCE(61)
        lua.execute(
            "_TARGET = { name = 'Uther Lumière', class = 'PALADIN', hostile = false, player = true, dead = true }; _HK = 2345"
        )
        g._FIRE("PLAYER_PVP_KILLS_CHANGED")
        g._ADVANCE(3)
        assert char.counters.pk == 5 and [e for e in char.events.values() if e.k == "pk"][-1].name == ""
        # Le compteur qui ne bouge pas, ou illisible : rien.
        g._FIRE("PLAYER_PVP_KILLS_CHANGED")
        g._ADVANCE(3)
        assert char.counters.pk == 5
        assert list(g.WoWForeverGuildeDB.errors.values()) == []

    def test_dead_target_counts_the_kill_when_neither_message_nor_counter_spoke(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute("_GUILD = true")
        receive(
            lua,
            f"D	1	Player-1-00000JAI	Jaina	Portvaillant	MAGE	60	Garrosh Hurlenfer	Durotar		{g._CLOCK.now}	1	WARRIOR	1411	0.4000	0.6000",
        )
        entry = g.WoWForeverGuildeDB.wanted["garrosh hurlenfer"]
        char = g._NS.char
        toast = g.WoWForeverGuildeDeath
        toast.shown = False
        # Ciblé vivant, combat, puis son cadavre sous ma cible : rien ne parle, le kill compte après la fenêtre.
        lua.execute(
            "_TARGET = { name = 'Garrosh Hurlenfer', class = 'WARRIOR', hostile = true, player = true }"
        )
        g._FIRE("PLAYER_TARGET_CHANGED")
        g._FIRE("PLAYER_REGEN_DISABLED")
        lua.execute("_TARGET.dead = true")
        g._FIRE("UNIT_HEALTH", "target")
        assert (char.counters.pk or 0) == 0
        g._ADVANCE(3)
        assert (entry.kills, char.counters.pk, char.counters.bounty) == (1, 1, 1)
        assert toast.shown is True and "Prime encaissée" in toast.header.text
        assert g._NS.Wanted.HonorSource().startswith(
            "dernier message « (cadavre de Garrosh Hurlenfer ciblé, ni message ni compteur) » → Garrosh Hurlenfer (cadavre)"
        )
        # Le même cadavre, re-ciblé ou à la fin du combat : une seule fois.
        g._FIRE("PLAYER_TARGET_CHANGED")
        g._FIRE("PLAYER_REGEN_ENABLED")
        g._ADVANCE(3)
        assert (entry.kills, char.counters.pk) == (1, 1)
        # Le message de victoire honorable qui arrive juste après ne compte pas deux fois.
        g._FIRE(
            "CHAT_MSG_COMBAT_HONOR_GAIN",
            "Garrosh meurt, victoire honorable Rang : Grunt (Points d'honneur estimés : 198)",
        )
        assert (entry.kills, char.counters.pk) == (1, 1)
        # Message pendant la fenêtre du cadavre : le message compte, le cadavre se tait.
        g._ADVANCE(120)
        garrosh_strikes_again(lua)
        lua.execute(
            "_TARGET = { name = 'Garrosh Hurlenfer', class = 'WARRIOR', hostile = true, player = true }"
        )
        g._FIRE("PLAYER_TARGET_CHANGED")
        lua.execute("_TARGET.dead = true")
        g._FIRE("UNIT_HEALTH", "target")
        g._ADVANCE(1)
        g._FIRE(
            "CHAT_MSG_COMBAT_HONOR_GAIN",
            "Garrosh meurt, victoire honorable Rang : Grunt (Points d'honneur estimés : 198)",
        )
        g._ADVANCE(3)
        assert (entry.kills, char.counters.pk) == (2, 2)
        assert [e for e in char.events.values() if e.k == "pk"][-1].name == "Garrosh"
        # Un cadavre jamais ciblé vivant, ou allié, ne compte pas.
        g._ADVANCE(120)
        lua.execute(
            "_TARGET = { name = 'Sylvanas', class = 'HUNTER', hostile = true, player = true, dead = true }"
        )
        g._FIRE("PLAYER_TARGET_CHANGED")
        g._ADVANCE(3)
        lua.execute("_TARGET = { name = 'Uther Lumière', class = 'PALADIN', hostile = false, player = true }")
        g._FIRE("PLAYER_TARGET_CHANGED")
        lua.execute("_TARGET.dead = true")
        g._FIRE("UNIT_HEALTH", "target")
        g._ADVANCE(3)
        assert char.counters.pk == 2
        assert list(g.WoWForeverGuildeDB.errors.values()) == []

    def test_mf_prime_rehearses_the_popup_without_recording(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        g.SlashCmdList.WOWFOREVERGUILDE("prime Garrosh")
        assert g.WoWForeverGuildeDeath is None  # aucun popup : le cadre n'a même pas été construit
        assert any("n'est pas au tableau (0 recherchés : aucun)" in m for m in list(g._CHAT.values()))
        receive(
            lua,
            f"D	1	Player-1-00000JAI	Jaina	Portvaillant	MAGE	60	Garrosh Hurlenfer	Durotar		{g._CLOCK.now}	1	WARRIOR	1411	0.4000	0.6000",
        )
        g.WoWForeverGuildeDeath.shown = False  # l'avis de décès a fait son temps
        g.SlashCmdList.WOWFOREVERGUILDE("prime garrosh")
        toast = g.WoWForeverGuildeDeath
        assert toast.shown is True and "Prime encaissée" in toast.header.text
        assert "Garrosh Hurlenfer" in toast.text.text and toast.footer.text.startswith("Prime de 1 point · ")
        assert any("Essai : popup pour" in m and "(prime de 1 point)" in m for m in list(g._CHAT.values()))
        char = g._NS.char
        assert (char.counters.pk or 0) == 0 and wanted_sent(g, "K") == []
        assert g.WoWForeverGuildeDB.wanted["garrosh hurlenfer"].kills == 0
        g.SlashCmdList.WOWFOREVERGUILDE("prime")
        assert any("/mf prime <nom>" in m for m in list(g._CHAT.values()))
        assert list(g.WoWForeverGuildeDB.errors.values()) == []

    def test_popup_phrases_agree_with_whoever_fills_them(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        fill = g._NS.Phrases.Fill
        # « de » et « à » se contractent ou s'élident selon le nom : une cause de mort porte son article.
        template = "Sur recommandation {de_tueur}, face {a_tueur}."
        assert [
            fill(template, lua.table(tueur=killer)) for killer in ("le feu", "une chute", "Arthas", "Hogger")
        ] == [
            "Sur recommandation du feu, face au feu.",
            "Sur recommandation d'une chute, face à une chute.",
            "Sur recommandation d'Arthas, face à Arthas.",
            "Sur recommandation de Hogger, face à Hogger.",
        ]
        # Majuscule en tête de chaque phrase, même quand un nom commun l'ouvre.
        roles = lua.table(personnage="Thrall", tueur="une chute")
        assert fill("{personnage} a tenté un truc. {tueur} a dit non.", roles) == (
            "Thrall a tenté un truc. Une chute a dit non."
        )
        # Kill à plusieurs : le verbe suit.
        template = "{tueur} {a|ont} livré."
        assert fill(template, lua.table(tueur="Thrall")) == "Thrall a livré."
        assert fill(template, lua.table(tueur="Thrall et Jaina"), True) == "Thrall et Jaina ont livré."
        # Un nom coloré s'élide d'après son nom nu.
        colored = lua.table(tueur=lua.table(plain="Uther", shown="|cfff58cbaUther|r"))
        assert fill("Victoire {de_tueur}.", colored) == "Victoire d'|cfff58cbaUther|r."
        # Tous les lots, avec chaque sorte de tueur : aucune variable oubliée, aucune faute de contraction.
        text = lua.eval("""(function()
          local ns, out = _NS, {}
          for _, killer in ipairs({ "le feu", "une chute", "l'épuisement", "quelque chose", "Sanglier des Tarides", "Arthas" }) do
            for _, t in ipairs(ns.PHRASES) do
              out[#out + 1] = ns.Phrases.Fill(t, { personnage = "un adversaire", tueur = killer })
            end
          end
          for _, plural in ipairs({ false, true }) do
            for _, t in ipairs(ns.KILL_PHRASES) do
              local hunters = plural and "Thrall et Uther" or "Uther"
              out[#out + 1] = ns.Phrases.Fill(t, { personnage = "un adversaire", tueur = hunters }, plural)
            end
          end
          for _, t in ipairs(ns.BOUNTY_PHRASES) do
            out[#out + 1] = ns.Phrases.Fill(t, { chasseur = "Uther", ennemi = "Arthas" })
          end
          return table.concat(out, "\\n")
        end)()""")
        lines = text.split("\n")
        assert len(lines) == 6 * 20 + 2 * 12 + 10
        for line in lines:
            assert line[0].isupper() and line[-1] in ".?!", line
            for wrong in (
                "{",
                "}",
                " de le feu",
                " à le feu",
                " de un",
                " de Arthas",
                " de Uther",
                ". u",
                ". l",
                ". q",
            ):
                assert wrong not in line, line
        assert not any("Thrall et Uther a " in line or "Thrall et Uther vient" in line for line in lines)
        # Les avis de décès ont leur source à la racine du dépôt : les deux listes restent identiques.
        source = (ADDON_DIR.parents[1] / "templates-morts").read_text(encoding="utf-8").splitlines()
        assert source == list(g._NS.PHRASES.values())

    def test_every_honorable_kill_outside_battlegrounds_is_announced(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute("_GUILD = true; _MAP = { id = 1429, x = 0.3, y = 0.3 }")
        honor = "Sylvanas meurt, victoire honorable (Points d'honneur estimés : 50)"
        g._FIRE("CHAT_MSG_COMBAT_HONOR_GAIN", honor)
        toast = g.WoWForeverGuildeDeath
        # Une phrase du lot des victoires honorables, chasseur et victime dedans ; le pied dit où.
        assert toast.shown is True and "Victoire honorable" in toast.header.text
        assert "Sylvanas" in toast.text.text and "{" not in toast.text.text
        assert "|cff0070ddThrall Fils-de-Durotan|r" in toast.text.text
        assert toast.footer.text == "Forêt d'Elwynn"
        (h,) = wanted_sent(g, "H")
        assert h.split("	")[:8] == [
            "H",
            "1",
            "Player-1-000ABC01",
            "Thrall Fils-de-Durotan",
            "SHAMAN",
            "Sylvanas",
            str(g._CLOCK.now),
            "Forêt d'Elwynn",
        ]
        assert wanted_sent(g, "K") == [] and "sylvanas" not in dict(g.WoWForeverGuildeDB.wanted)
        # Mon écho ne refait pas de popup. Crédit de groupe : le « H » d'un coéquipier pour la même victime n'en
        # fait pas un second, il ajoute son nom au mien (même phrase, accordée au pluriel) ; sa répétition ne
        # change rien.
        toast.shown = False
        receive(lua, h, "Thrall-Forever")
        assert toast.shown is False
        toast.shown = True
        mate = f"H	1	Player-1-00000JAI	Jaina Portvaillant	MAGE	Sylvanas	{g._CLOCK.now}	Durotar		"
        receive(lua, mate)
        assert toast.footer.text == "Forêt d'Elwynn"
        assert "|cff0070ddThrall Fils-de-Durotan|r et |cff69ccf0Jaina Portvaillant|r" in toast.text.text
        toast.shown = False
        receive(lua, mate)
        assert toast.shown is False and len(wanted_sent(g, "H")) == 1
        g._ADVANCE(20)
        # Le kill d'un guildien sur un autre joueur : popup chez moi, chasseur et victime à leur couleur de classe.
        receive(
            lua,
            f"H	1	Player-1-00000JAI	Jaina Portvaillant	MAGE	Nazgrel	{g._CLOCK.now}	Durotar	Tranchecolline	SHAMAN",
        )
        assert toast.shown is True and "Victoire honorable" in toast.header.text
        assert toast.footer.text == "Durotar"
        assert (
            "|cff0070ddNazgrel|r" in toast.text.text and "|cff69ccf0Jaina Portvaillant|r" in toast.text.text
        )
        assert len(wanted_sent(g, "H")) == 1  # je ne relaie rien
        # « Afficher les morts des autres » décoché : pas de popup.
        g.WoWForeverGuildeDB.settings.showDeaths = False
        toast.shown = False
        receive(
            lua,
            f"H	1	Player-1-00000JAI	Jaina Portvaillant	MAGE	Rexxar	{g._CLOCK.now}	Durotar		",
        )
        assert toast.shown is False
        g.WoWForeverGuildeDB.settings.showDeaths = True
        # En champ de bataille : le kill compte, mais ni popup ni message.
        lua.execute('_INSTANCE = "pvp"')
        g._FIRE(
            "CHAT_MSG_COMBAT_HONOR_GAIN", "Saurfang meurt, victoire honorable (Points d'honneur estimés : 50)"
        )
        assert toast.shown is False and len(wanted_sent(g, "H")) == 1
        assert g._NS.char.counters.pk == 2
        assert list(g.WoWForeverGuildeDB.errors.values()) == []

    def test_a_player_killed_again_gets_a_new_popup_and_popups_wait_their_turn(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute("_GUILD = true; _MAP = { id = 1429, x = 0.3, y = 0.3 }")
        honor = "Sylvanas meurt, victoire honorable (Points d'honneur estimés : 50)"
        g._FIRE("CHAT_MSG_COMBAT_HONOR_GAIN", honor)
        toast = g.WoWForeverGuildeDeath
        assert toast.shown is True and len(wanted_sent(g, "H")) == 1
        # Elle revient et je la retue 30 s plus tard : nouveau popup, nouveau « H » (avant : rien pendant 60 s).
        g._ADVANCE(30)
        toast.shown = False
        g._FIRE("CHAT_MSG_COMBAT_HONOR_GAIN", honor)
        assert toast.shown is True and len(wanted_sent(g, "H")) == 2
        # Chez un guildien, pareil : deux kills de Jaina sur Nazgrel à 30 s d'écart font deux popups, mais la
        # répétition du second (même chasseur, même heure de kill), même 40 s après, n'en refait pas.
        g._ADVANCE(30)
        first = f"H	1	Player-1-00000JAI	Jaina Portvaillant	MAGE	Nazgrel	{g._CLOCK.now}	Durotar		"
        toast.shown = False
        receive(lua, first)
        assert toast.shown is True
        g._ADVANCE(30)
        second = f"H	1	Player-1-00000JAI	Jaina Portvaillant	MAGE	Nazgrel	{g._CLOCK.now}	Durotar		"
        toast.shown = False
        receive(lua, second)
        assert toast.shown is True
        g._ADVANCE(40)
        toast.shown = False
        receive(lua, second)
        assert toast.shown is False
        # Le « H » d'un coéquipier pour le même kill (autre chasseur, quelques secondes après) : pas de second
        # popup, son nom s'ajoute à celui déjà affiché ; sa répétition tardive ne refait rien.
        g._ADVANCE(60)
        kill = g._CLOCK.now
        receive(
            lua,
            f"H	1	Player-1-00000JAI	Jaina Portvaillant	MAGE	Rexxar	{kill}	Durotar		",
        )
        assert toast.shown is True and "Rexxar" in toast.text.text
        g._ADVANCE(2)
        mate = f"H	1	Player-1-00000UTH	Uther Lumière	PALADIN	Rexxar	{kill + 1}	Durotar		"
        receive(lua, mate, "Uther-Forever")
        assert toast.footer.text == "Durotar" and "Rexxar" in toast.text.text
        assert "|cff69ccf0Jaina Portvaillant|r et |cffffffffUther Lumière|r" in toast.text.text
        third = f"H	1	Player-1-00000VAR	Varian Wrynn	WARRIOR	Rexxar	{kill + 2}	Durotar		"
        receive(lua, third, "Varian-Forever")
        assert (
            "|cff69ccf0Jaina Portvaillant|r, |cffffffffUther Lumière|r et |cffffffffVarian Wrynn|r"
            in toast.text.text
        )
        g._ADVANCE(30)
        toast.shown = False
        receive(lua, mate, "Uther-Forever")
        assert toast.shown is False
        # Deux popups coup sur coup : le premier reste 4 s à l'écran, le second attend son tour au lieu de l'écraser.
        g._ADVANCE(60)
        receive(
            lua,
            f"H	1	Player-1-00000JAI	Jaina Portvaillant	MAGE	Saurfang	{g._CLOCK.now}	Durotar		",
        )
        g._ADVANCE(1)
        receive(
            lua,
            f"H	1	Player-1-00000UTH	Uther Lumière	PALADIN	Zaela	{g._CLOCK.now}	Durotar		",
            "Uther-Forever",
        )
        assert "Saurfang" in toast.text.text
        g._ADVANCE(2)
        assert "Saurfang" in toast.text.text
        g._ADVANCE(1)
        assert toast.shown is True and "Zaela" in toast.text.text
        # /mf api raconte les derniers popups : affiché, mis en attente, sorti de la file.
        source = g._NS.UI.ToastSource()
        assert "il y a 4 s affiché « Jaina Portvaillant abat Saurfang · Durotar »" in source
        assert "il y a 3 s mis en attente « Uther Lumière abat Zaela · Durotar »" in source
        assert source.endswith(
            "il y a 0 s sorti de la file « Uther Lumière abat Zaela · Durotar » · en attente : 0"
        )
        assert list(g.WoWForeverGuildeDB.errors.values()) == []

    def test_the_kill_log_of_the_session_goes_to_the_site_with_the_errors(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute("_GUILD = true; _MAP = { id = 1429, x = 0.3, y = 0.3 }")
        assert g._NS.Wanted.KillLog() == ""
        # Un kill lu dans le message, un message illisible (valeur secrète en combat), un « H » reçu.
        g._FIRE(
            "CHAT_MSG_COMBAT_HONOR_GAIN", "Sylvanas meurt, victoire honorable (Points d'honneur estimés : 50)"
        )
        lua.execute("_COMBAT = true")
        g._FIRE("CHAT_MSG_COMBAT_HONOR_GAIN", "Vous avez vaincu un adversaire.")
        lua.execute("_COMBAT = false")
        receive(
            lua, f"H\t1\tPlayer-1-00000JAI\tJaina Portvaillant\tMAGE\tNazgrel\t{g._CLOCK.now}\tDurotar\t\t"
        )
        lines = g._NS.Wanted.KillLog().split(" | ")
        assert [line.split(" ", 1)[1] for line in lines] == [
            "message « Sylvanas meurt, victoire honorable (Points d'honne » → Sylvanas (motif)",
            "kill « Sylvanas » : popup, H accepté",
            "combat message « Vous avez vaincu un adversaire. » → aucun nom",
            "reçu H de Jaina Portvaillant : Nazgrel → popup",
        ]
        # Rien dans les erreurs tant qu'on joue ; à la déconnexion, le journal part avec elles (où = « vh »).
        assert list(g.WoWForeverGuildeDB.errors.values()) == []
        g._FIRE("PLAYER_LOGOUT")
        (entry,) = list(g.WoWForeverGuildeDB.errors.values())
        assert entry.where == "vh" and "kill « Sylvanas » : popup, H accepté" in entry.error

    def test_a_kill_the_game_does_not_name_is_announced_and_named_afterwards(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute("_GUILD = true; _MAP = { id = 1429, x = 0.3, y = 0.3 }")
        char = g._NS.char
        # Forever : « Vous avez reçu 5 points d'honneur. », sans nom, et je survole un coéquipier mort dans les
        # cadres de groupe : il n'est pas la victime. Le kill s'annonce quand même, « un adversaire ».
        lua.execute(
            "_UNITS.mouseover = { name = 'Morgul', class = 'MAGE', hostile = false, player = true, dead = true }; _HK = 2341"
        )
        g._FIRE("PLAYER_PVP_KILLS_CHANGED")
        g._FIRE("CHAT_MSG_COMBAT_HONOR_GAIN", "Vous avez reçu 5 points d’honneur.")
        g._ADVANCE(3)
        toast = g.WoWForeverGuildeDeath
        assert toast.shown is True and "Victoire honorable" in toast.header.text
        assert toast.footer.text == "Forêt d'Elwynn" and "n adversaire" in toast.text.text
        assert "Morgul" not in toast.text.text and "{" not in toast.text.text
        (h,) = wanted_sent(g, "H")
        kill = g._CLOCK.now
        assert h.split("\t")[5:7] == ["", str(kill)] and char.counters.pk == 1
        assert "mouseover joueur mort allié" in g._NS.Wanted.KillLog()
        # Après le combat, son cadavre sous ma cible donne le nom : le même kill (pas un second), le popup encore
        # à l'écran se complète et le « H » repart avec le nom et la même heure de kill.
        lua.execute("_UNITS.mouseover = nil")
        lua.execute("_TARGET = { name = 'Garrosh', class = 'WARRIOR', hostile = true, player = true }")
        g._FIRE("PLAYER_TARGET_CHANGED")
        g._ADVANCE(2)
        lua.execute("_TARGET.dead = true")
        g._FIRE("UNIT_HEALTH", "target")
        g._ADVANCE(3)
        assert char.counters.pk == 1
        assert toast.footer.text == "Forêt d'Elwynn"
        assert "Garrosh" in toast.text.text and "n adversaire" not in toast.text.text
        sent = wanted_sent(g, "H")
        assert len(sent) == 2 and sent[1].split("\t")[5:7] == ["Garrosh", str(kill)]
        # Chez un guildien : un « H » sans nom fait un popup ; celui d'un coéquipier du chasseur s'y ajoute ; le nom
        # qui suit (même chasseur, même heure de kill) le complète sans en refaire un.
        g._ADVANCE(120)
        t = g._CLOCK.now
        receive(lua, f"H\t1\tPlayer-1-00000JAI\tJaina Portvaillant\tMAGE\t\t{t}\tDurotar\t\t")
        assert toast.footer.text == "Durotar" and "n adversaire" in toast.text.text
        g._ADVANCE(1)
        receive(
            lua, f"H\t1\tPlayer-1-00000UTH\tUther Lumière\tPALADIN\t\t{t + 1}\tDurotar\t\t", "Uther-Forever"
        )
        assert "n adversaire" in toast.text.text
        assert "|cff69ccf0Jaina Portvaillant|r et |cffffffffUther Lumière|r" in toast.text.text
        g._ADVANCE(5)
        receive(lua, f"H\t1\tPlayer-1-00000JAI\tJaina Portvaillant\tMAGE\tNazgrel\t{t}\tDurotar\t\tSHAMAN")
        assert "|cff0070ddNazgrel|r" in toast.text.text and "n adversaire" not in toast.text.text
        assert "|cff69ccf0Jaina Portvaillant|r et |cffffffffUther Lumière|r" in toast.text.text
        # Le popup a fait son temps : le nom qui arrive trop tard ne le rejoue pas.
        g._ADVANCE(120)
        t = g._CLOCK.now
        receive(lua, f"H\t1\tPlayer-1-00000JAI\tJaina Portvaillant\tMAGE\t\t{t}\tDurotar\t\t")
        g._ADVANCE(20)
        g._ADVANCE(20)
        assert toast.shown is False
        receive(lua, f"H\t1\tPlayer-1-00000JAI\tJaina Portvaillant\tMAGE\tRexxar\t{t}\tDurotar\t\t")
        assert toast.shown is False
        assert list(g.WoWForeverGuildeDB.errors.values()) == []

    def test_a_kill_announcement_is_retried_when_refused_and_repeated_out_of_combat(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute("_GUILD = true; _MAP = { id = 1429, x = 0.3, y = 0.3 }")
        source = g._NS.Wanted.AnnounceSource
        assert source() == "aucun K ni H envoyé cette session · K et H reçus : 0"
        # Le jeu refuse l'envoi (code 3) : mon popup passe, le « H » est retenté toutes les 5 s jusqu'à passer.
        lua.execute(
            "_REAL_SEND = C_ChatInfo.SendAddonMessage; C_ChatInfo.SendAddonMessage = function() return 3 end"
        )
        g._FIRE(
            "CHAT_MSG_COMBAT_HONOR_GAIN", "Sylvanas meurt, victoire honorable (Points d'honneur estimés : 50)"
        )
        assert g.WoWForeverGuildeDeath.shown is True and wanted_sent(g, "H") == []
        g._ADVANCE(5)
        assert source() == "dernier H envoyé : refusé (3) · 2 essais · K et H reçus : 0"
        lua.execute("C_ChatInfo.SendAddonMessage = _REAL_SEND")
        g._ADVANCE(5)
        assert len(wanted_sent(g, "H")) == 1
        assert source() == "dernier H envoyé : accepté · 3 essais · K et H reçus : 0"
        g._ADVANCE(60)
        assert len(wanted_sent(g, "H")) == 1  # parti hors combat : pas de répétition
        # En combat : parti tout de suite, puis une seconde fois à la sortie du combat (un receveur en combat a pu
        # ne pas le lire) ; chez qui l'a déjà lu, la répétition ne refait pas de popup.
        lua.execute("_COMBAT = true")
        g._FIRE(
            "CHAT_MSG_COMBAT_HONOR_GAIN", "Nazgrel meurt, victoire honorable (Points d'honneur estimés : 50)"
        )
        assert len(wanted_sent(g, "H")) == 2
        g._ADVANCE(10)
        assert len(wanted_sent(g, "H")) == 2
        lua.execute("_COMBAT = false")
        g._ADVANCE(5)
        sent = wanted_sent(g, "H")
        assert len(sent) == 3 and sent[1] == sent[2]
        assert source() == "dernier H envoyé : accepté · 2 essais · répété hors combat · K et H reçus : 0"
        g._ADVANCE(60)
        assert len(wanted_sent(g, "H")) == 3
        # Un combat qui dure : plus d'essai 45 s après le kill.
        lua.execute("_COMBAT = true")
        g._FIRE(
            "CHAT_MSG_COMBAT_HONOR_GAIN", "Rexxar meurt, victoire honorable (Points d'honneur estimés : 50)"
        )
        g._ADVANCE(50)
        lua.execute("_COMBAT = false")
        g._ADVANCE(30)
        assert len(wanted_sent(g, "H")) == 4
        # Mon écho et le « H » d'un guildien sont comptés pour /mf api.
        receive(lua, sent[2], "Thrall-Forever")
        assert source().endswith("K et H reçus : 1")
        assert list(g.WoWForeverGuildeDB.errors.values()) == []

    def test_a_guild_kill_on_someone_wanted_here_cashes_the_bounty(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute("_GUILD = true")
        receive(
            lua,
            f"D	1	Player-1-00000JAI	Jaina	Portvaillant	MAGE	60	Garrosh Hurlenfer	Durotar		{g._CLOCK.now}	1	WARRIOR	1411	0.4000	0.6000",
        )
        entry = g.WoWForeverGuildeDB.wanted["garrosh hurlenfer"]
        toast = g.WoWForeverGuildeDeath
        # Le chasseur ne le savait pas recherché (son tableau est en retard) : il annonce une simple victoire.
        g._ADVANCE(120)
        receive(
            lua,
            f"H	1	Player-1-00000UTH	Uther Lumière	PALADIN	Garrosh	{g._CLOCK.now}	Durotar		WARRIOR",
        )
        assert entry.kills == 1 and (entry.last.kind, entry.last.by) == ("kill", "Uther Lumière")
        assert toast.shown is True and "Prime encaissée" in toast.header.text
        # La prime est encaissée : il quitte le tableau, et un second kill n'est plus qu'une victoire honorable.
        assert entry.points == 0 and list(g._NS.Wanted.Sorted().values()) == []
        g._ADVANCE(120)
        receive(
            lua,
            f"H	1	Player-1-00000UTH	Uther Lumière	PALADIN	Garrosh	{g._CLOCK.now}	Durotar		WARRIOR",
        )
        assert entry.kills == 1 and "Victoire honorable" in toast.header.text
        # Il retue un membre : de nouveau recherché, la prime repart de 1. Une mort PvP garde son avis « WANTED ».
        g._ADVANCE(120)
        receive(
            lua,
            f"D	1	Player-1-00000UTH	Uther	Lumière	PALADIN	60	Garrosh Hurlenfer	Durotar		{g._CLOCK.now}	1	WARRIOR	1411	0.4000	0.6000",
        )
        assert "WANTED" in toast.header.text and entry.points == 1
        assert [e.name for e in g._NS.Wanted.Sorted().values()] == ["Garrosh Hurlenfer"]
        assert list(g.WoWForeverGuildeDB.errors.values()) == []

    def test_honorable_kill_of_a_wanted_player_cashes_the_bounty(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute(FAKE_PINS)
        lua.execute("_GUILD = true; _MAP = { id = 1429, x = 0.3, y = 0.3 }")
        # Garrosh a tué Jaina : prime 1.
        receive(
            lua,
            f"D\t1\tPlayer-1-00000JAI\tJaina\tPortvaillant\tMAGE\t60\tGarrosh Hurlenfer\tDurotar\t\t{g._CLOCK.now}\t1\tWARRIOR\t1411\t0.4000\t0.6000",
        )
        entry = g.WoWForeverGuildeDB.wanted["garrosh hurlenfer"]
        # Je l'abats : le message de victoire honorable nomme la victime (le prénom seul suffit s'il est unique).
        g.WoWForeverGuildeDeath.shown = False  # l'avis de décès a fait son temps
        g._FIRE(
            "CHAT_MSG_COMBAT_HONOR_GAIN",
            "Garrosh meurt, victoire honorable Rang : Grunt (Points d'honneur estimés : 198)",
        )
        assert (entry.kills, entry.points, entry.cashed) == (1, 0, g._CLOCK.now)  # encaissée : remise à zéro
        assert (entry.last.kind, entry.last.by, entry.last.map, entry.last.x) == (
            "kill",
            "Thrall Fils-de-Durotan",
            1429,
            0.3,
        )
        char = g._NS.char
        assert (char.counters.pk, char.counters.bounty) == (1, 1)
        pk = [e for e in char.events.values() if e.k == "pk"][-1]
        assert (pk.name, pk.prime, pk.map, pk.zone) == ("Garrosh", 1, 1429, "Forêt d'Elwynn")
        (k,) = wanted_sent(g, "K")
        assert k.split("\t")[:9] == [
            "K",
            "1",
            "Player-1-000ABC01",
            "Thrall Fils-de-Durotan",
            "SHAMAN",
            "Garrosh Hurlenfer",
            "1",
            "1",
            str(g._CLOCK.now),
        ]
        toast = g.WoWForeverGuildeDeath
        assert (
            toast.shown is True
            and "Prime encaissée" in toast.header.text
            and "Garrosh Hurlenfer" in toast.text.text
        )
        assert "|cff0070ddThrall Fils-de-Durotan|r" in toast.text.text
        assert toast.footer.text == "Prime de 1 point · Forêt d'Elwynn"
        assert any(
            "Prime encaissée :" in m and "a abattu" in m and "1 point." in m for m in list(g._CHAT.values())
        )
        # Prime encaissée : sa tête de mort quitte la carte et il quitte le tableau, jusqu'à sa prochaine victime.
        assert list(g._PINS.added.items()) == [] and list(g._NS.Wanted.Sorted().values()) == []
        # Crédit de groupe : l'écho de mon « K » et celui d'un coéquipier pour le même kill ne comptent pas deux fois.
        receive(lua, k, "Thrall-Forever")
        receive(
            lua,
            f"K\t1\tPlayer-1-00000JAI\tJaina Portvaillant\tMAGE\tGarrosh Hurlenfer\t1\t1\t{g._CLOCK.now}\t1429\t0.3000\t0.3000\tForêt d'Elwynn\t\tWARRIOR",
        )
        assert entry.kills == 1
        # Un joueur qui n'est pas recherché : événement pk sans prime, pas de « K », rien au tableau ; un popup
        # « Victoire honorable » (cf. test_every_honorable_kill_outside_battlegrounds_is_announced).
        toast.shown = False
        g._FIRE(
            "CHAT_MSG_COMBAT_HONOR_GAIN", "Sylvanas meurt, victoire honorable (Points d'honneur estimés : 50)"
        )
        assert (char.counters.pk, char.counters.bounty) == (2, 1)
        assert toast.shown is True and "Victoire honorable" in toast.header.text
        assert len(wanted_sent(g, "K")) == 1 and "sylvanas" not in dict(g.WoWForeverGuildeDB.wanted)
        # Un « K » d'un guildien pour un ennemi que je ne connaissais pas : créé, prime annoncée puis encaissée.
        toast.shown = False  # le popup précédent a fait son temps
        receive(
            lua,
            f"K\t1\tPlayer-1-00000UTH\tUther Lumière\tPALADIN\tVol'jin\t3\t1\t{g._CLOCK.now}\t1411\t0.1000\t0.2000\tDurotar\tOrgrimmar\tSHAMAN",
            "Uther-Forever",
        )
        voljin = g.WoWForeverGuildeDB.wanted["vol'jin"]
        assert (voljin.points, voljin.kills, voljin["class"], voljin.last.by) == (
            0,
            1,
            "SHAMAN",
            "Uther Lumière",
        )
        assert toast.shown is True and toast.footer.text == "Prime de 3 points · Durotar"
        # Les motifs viennent des chaînes du jeu (avec et sans rang).
        patterns = list(g._NS.Wanted.HonorPatterns().values())
        assert patterns[0] == "^(.-) meurt, victoire honorable Rang : " and patterns[1].startswith(
            "^(.-) meurt, victoire honorable %("
        )
        assert list(g.WoWForeverGuildeDB.errors.values()) == []
        # L'export porte les événements pk et les compteurs ; le site en fera les chasseurs de primes.
        payload = decode_export(logout_code(lua))
        c = payload["characters"][0]
        assert c["counters"]["pk"] == 2 and c["counters"]["bounty"] == 1
        assert [(e["name"], e["prime"]) for e in c["events"] if e["k"] == "pk"] == [
            ("Garrosh", 1),
            ("Sylvanas", 0),
        ]

    def test_a_cashed_bounty_is_shared_by_the_group_and_not_revived_by_a_late_table(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute("_GUILD = true")
        garrosh_strikes_again(lua)
        entry = g.WoWForeverGuildeDB.wanted["garrosh hurlenfer"]
        char = g._NS.char
        g._ADVANCE(120)
        # Mon coéquipier l'annonce le premier : la prime est encaissée chez moi aussi…
        killed = g._CLOCK.now
        receive(
            lua,
            f"K\t1\tPlayer-1-00000JAI\tJaina Portvaillant\tMAGE\tGarrosh Hurlenfer\t1\t1\t{killed}"
            "\t1429\t0.3000\t0.3000\tForêt d'Elwynn\t\tWARRIOR",
        )
        assert (entry.points, entry.kills, entry.cashed) == (0, 1, killed)
        # … et mon message de victoire honorable pour ce même kill me la crédite (crédit de groupe), sans « K ».
        g._ADVANCE(2)
        g._FIRE(
            "CHAT_MSG_COMBAT_HONOR_GAIN",
            "Garrosh meurt, victoire honorable Rang : Grunt (Points d'honneur estimés : 198)",
        )
        assert (entry.kills, char.counters.pk, char.counters.bounty) == (1, 1, 1)
        assert [e for e in char.events.values() if e.k == "pk"][-1].prime == 1
        assert wanted_sent(g, "K") == []
        # Un tableau en retard (ou un addon d'avant la 0.6.10, sans heure d'encaissement) ne ressuscite pas la prime.
        item = f"Garrosh Hurlenfer|WARRIOR|5|0|{killed}|1411|0.4000|0.6000"
        receive(lua, f"W\t1\t{item}")
        receive(lua, f"W\t1\t{item}|{killed - 3600}")
        assert entry.points == 0 and list(g._NS.Wanted.Sorted().values()) == []
        # Un tableau plus à jour que le mien (encaissé plus tard, deux morts depuis) est suivi.
        receive(lua, f"W\t1\tGarrosh Hurlenfer|WARRIOR|2|2|{killed + 900}|1411|0.4000|0.6000|{killed + 600}")
        assert (entry.points, entry.kills, entry.cashed) == (2, 2, killed + 600)
        # Mon résumé porte l'heure d'encaissement, et les primes encaissées (zéro) pour les autres tableaux.
        receive(lua, f"W\t1\tVol'jin|SHAMAN|0|1|{killed}||||{killed}")
        lines = list(g._NS.Wanted.EncodeDigest().values())
        assert len(lines) == 1 and lines[0].split("\t")[2:] == [
            f"Garrosh Hurlenfer|WARRIOR|2|2|{killed + 900}|1411|0.4000|0.6000|{killed + 600}",
            f"Vol'jin|SHAMAN|0|1|{killed}||||{killed}",
        ]
        assert [e.name for e in g._NS.Wanted.Sorted().values()] == ["Garrosh Hurlenfer"]
        assert list(g.WoWForeverGuildeDB.errors.values()) == []

    def test_handshake_shares_the_table_with_a_member_who_logs_in(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute("_GUILD = true")
        g._ADVANCE(1)  # 8 s après la connexion : je demande le tableau
        assert wanted_sent(g, "W") == ["W\t1"]
        # Je connais deux ennemis ; un membre se connecte et demande : je réponds entre 1 et 6 s, en une ligne.
        receive(
            lua,
            f"D\t1\tPlayer-1-00000JAI\tJaina\tPortvaillant\tMAGE\t60\tGarrosh Hurlenfer\tDurotar\t\t{g._CLOCK.now}\t1\tWARRIOR\t1411\t0.4000\t0.6000",
        )
        receive(
            lua,
            f"D\t1\tPlayer-1-00000UTH\tUther\tLumière\tPALADIN\t58\tVol'jin\tDurotar\t\t{g._CLOCK.now - 100}\t1\tSHAMAN\t1411\t0.1000\t0.2000",
            "Uther-Forever",
        )
        receive(lua, "W\t1")
        g._ADVANCE(7)
        digests = [t for t in wanted_sent(g, "W") if t != "W\t1"]
        assert len(digests) == 1
        items = digests[0].split("\t")[2:]
        assert items[0].startswith("Garrosh Hurlenfer|WARRIOR|1|0|") and items[1].startswith(
            "Vol'jin|SHAMAN|1|0|"
        )
        # Quelqu'un répond avant moi : je me tais ; son résumé relève Garrosh au maximum de chaque valeur.
        lua.execute("_ADDON_SENT = {}")
        receive(lua, "W\t1")
        receive(
            lua, f"W\t1\tGarrosh Hurlenfer|WARRIOR|4|2|{g._CLOCK.now}|1411|0.5000|0.5000", "Uther-Forever"
        )
        g._ADVANCE(7)
        assert wanted_sent(g, "W") == []
        garrosh = g.WoWForeverGuildeDB.wanted["garrosh hurlenfer"]
        assert (garrosh.points, garrosh.kills, garrosh.last.kind, garrosh.last.x) == (4, 2, "seen", 0.5)
        rows = list(g._NS.WantedUI.Lines().values())
        assert (
            "prime de 4 points" in rows[1].text
            and "abattu 2 fois" in rows[1].text
            and "vu pour la dernière fois" in rows[1].text
        )
        # Résumé long : découpé en lignes de 255 octets au plus, toutes décodables.
        lua.execute(
            f"for i = 1, 30 do _NS.Wanted.RecordDeath({{ player = true, killer = 'Ennemi numéro ' .. i, guid = 'G' .. i, name = 'V', t = {g._CLOCK.now} + i }}) end"
        )
        lines = list(g._NS.Wanted.EncodeDigest().values())
        assert len(lines) > 1 and all(len(line.encode("utf-8")) <= 255 for line in lines)
        assert sum(len(list(g._NS.Wanted.DecodeDigest(line)["items"].values())) for line in lines) == 32
        assert list(g.WoWForeverGuildeDB.errors.values()) == []

    def test_an_enemy_is_read_with_surname_and_not_doubled_with_its_first_name(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        now = g._CLOCK.now
        # Le jeu rend « prénom, nom de famille » en deux valeurs : l'ennemi est lu en entier.
        lua.execute("_TARGET = { name = 'Garrosh', surname = 'Hurlenfer', hostile = true, player = true }")
        assert g._NS.UnitDisplayName("target") == "Garrosh Hurlenfer"
        lua.execute("_TARGET = { name = _SECRET, hostile = true, player = true }")
        assert g._NS.UnitDisplayName("target") is None
        lua.execute("_TARGET = nil")

        def death(killer: str, offset: int) -> None:
            lua.execute(
                f"_NS.Wanted.RecordDeath({{ player = true, killer = '{killer}', guid = 'G{offset}',"
                f" name = 'V', t = {now} + {offset} }})"
            )

        # Connu par son prénom (addon d'avant), puis nommé en entier, puis de nouveau par son prénom : un seul.
        death("Garrosh", 1)
        death("Garrosh Hurlenfer", 2)
        death("Garrosh", 3)
        wanted = g.WoWForeverGuildeDB.wanted
        assert sorted(wanted.keys()) == ["garrosh hurlenfer"]
        assert (wanted["garrosh hurlenfer"].name, wanted["garrosh hurlenfer"].points) == (
            "Garrosh Hurlenfer",
            3,
        )
        # Deux ennemis du même prénom : le prénom seul ne tranche pas.
        death("Garrosh Autre", 4)
        death("Garrosh", 5)
        assert sorted(wanted.keys()) == ["garrosh", "garrosh autre", "garrosh hurlenfer"]
        assert list(g.WoWForeverGuildeDB.errors.values()) == []


class TestPureModules:
    @pytest.fixture
    def lua(self):
        return boot(["Locales/frFR.lua", "Data.lua", "Json.lua", "Base64.lua", "Store.lua", "Journal.lua"])

    def test_json_matches_python(self, lua):
        ns = lua.globals()._NS
        encode = ns.Json.encode
        assert json.loads(encode(lua.eval('{ b = 1, a = "é\\"\\n", c = { 1, 2, 3 }, d = { x = true, y = false }, e = 1.5, f = -0 }'))) == {
            "a": 'é"\n', "b": 1, "c": [1, 2, 3], "d": {"x": True, "y": False}, "e": 1.5, "f": 0,
        }  # fmt: skip
        assert encode(lua.eval("{}")) == "{}"
        assert json.loads(encode(ns.Json.array(lua.eval("{}")))) == []
        assert json.loads(encode(lua.eval("{ [1] = 'a', [3] = 'c' }"))) == {
            "1": "a",
            "3": "c",
        }  # trou → objet
        assert json.loads(encode(lua.eval("{ [10] = 1, [2] = 2 }"))) == {"10": 1, "2": 2}
        assert json.loads(encode(lua.eval("{ s = '\\0\\1' }"))) == {"s": "\x00\x01"}
        assert json.loads(encode(lua.eval("{ n = 2^53 * 4 }"))) == {
            "n": 3.6028797018964e16
        }  # trop grand : flottant
        assert encode(lua.eval("0/0")) == "null"

    def test_base64_matches_python(self, lua):
        encode = lua.globals()._NS.Base64.encode
        for raw in [b"", b"f", b"fo", b"foo", b"foob", b"fooba", b"foobar", bytes(range(256))]:
            assert (
                encode(raw.decode("latin-1")).encode("latin-1") == base64.b64encode(raw)
                if raw.isascii()
                else True
            )
        assert encode("foobar") == "Zm9vYmFy" and encode("fo") == "Zm8="

    def test_journal_prunes_old_days_and_caps_events(self, lua):
        g = lua.globals()
        lua.execute("""
          local entry = { counters = { x = 1 }, journal = { ["2020-01-01"] = { x = 0 } }, events = {} }
          _NS.Data.MAX_EVENTS = 3
          for i = 1, 5 do _NS.Journal.Event(entry, "e", { i = i }, i) end
          _NS.Journal.Snapshot(entry, _CLOCK.now)
          _ENTRY = entry
        """)
        entry = g._ENTRY
        assert [entry.events[i].i for i in range(1, 4)] == [3, 4, 5]
        assert entry.journal["2020-01-01"] is None and entry.journal[g.date("%Y-%m-%d")].x == 1


def test_export_format_in_lua_matches_python_decoder():
    lua = boot(
        [
            "Libs/LibStub/LibStub.lua",
            "Libs/LibDeflate/LibDeflate.lua",
            "Locales/frFR.lua",
            "Data.lua",
            "Json.lua",
            "Base64.lua",
            "Store.lua",
            "Journal.lua",
            "Export.lua",
        ]
    )
    code = lua.globals()._NS.Export.Encode(
        lua.eval(
            "{ v = 1, characters = _NS.Json.array({ { guid = 'g', name = 'Nalu', level = 12, exported_at = 1 } }) }"
        )
    )
    assert re.match(r"^WFG1:[0-9a-f]{8}:[A-Za-z0-9+/=]+$", code)
    assert decode_export(code)["characters"][0]["name"] == "Nalu"
