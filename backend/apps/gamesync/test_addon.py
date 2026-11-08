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


class TestLoading:
    def test_every_lua_file_is_listed_in_the_toc_and_loads(self):
        listed = set(toc_files())
        on_disk = {p.relative_to(ADDON_DIR).as_posix() for p in ADDON_DIR.rglob("*.lua")}
        assert on_disk == listed
        lua = boot()
        ns = lua.globals()._NS
        names = sorted(ns.collectors[i].name for i in range(1, len(ns.collectors) + 1))
        assert names == sorted(
            ["identity", "gear", "talents", "professions", "reputation", "attunements", "lockouts", "pvp", "pve", "kills", "gathering", "quests", "deaths", "positions", "mapui"]
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
        assert char.gear.head.id == 16842 and char.gear.head.ench == 2583 and char.gear.mainhand.ench is None
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
        g._FIRE("PLAYER_DEAD")
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
        g._FIRE("PLAYER_DEAD")
        g._ADVANCE(1)
        assert list(g._ADDON_SENT.values()) == []
        lua.execute("_GUILD = true")
        # Le tueur est la cible hostile au moment de mourir (pas de journal de combat sur Forever).
        lua.execute("_TARGET = { name = 'Sanglier des Tarides', hostile = true }")
        g._FIRE("PLAYER_DEAD")
        lua.execute("_TARGET = nil")
        g._ADVANCE(1)
        (sent,) = list(g._ADDON_SENT.values())
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
        assert toast.footer.text == "Niveau 60 · Chaman"
        assert len(list(g._SOUNDS.values())) == 1
        # Ancienne version en face : nom de classe affiché au lieu du jeton, accepté tel quel.
        g._FIRE(
            "CHAT_MSG_ADDON", "WFG", sent.text.replace("\tSHAMAN\t", "\tChaman\t"), "GUILD", "Thrall-Forever"
        )
        assert toast.footer.text == "Niveau 60 · Chaman" and len(list(g._SOUNDS.values())) == 2
        # Chuchoté par n'importe qui : ignoré.
        toast.shown = False
        g._FIRE("CHAT_MSG_ADDON", "WFG", sent.text, "WHISPER", "Inconnu-Forever")
        assert toast.shown is False
        # Son coupé → le popup reste, sans son.
        lua.execute("WoWForeverGuildeDB.settings.soundDeaths = false")
        g._FIRE("CHAT_MSG_ADDON", "WFG", sent.text, "GUILD", "Thrall-Forever")
        assert toast.shown is True and len(list(g._SOUNDS.values())) == 2
        # Désactivé → rien n'est envoyé.
        lua.execute("WoWForeverGuildeDB.settings.announceDeaths = false")
        g._FIRE("PLAYER_DEAD")
        g._ADVANCE(1)
        assert len([s for s in g._ADDON_SENT.values() if s.text.startswith("D\t")]) == 1

    def test_death_is_still_announced_when_the_game_hides_values_in_combat(self):
        # Valeurs « secrètes » (zone, nom de la cible) au moment de mourir : rien ne doit faire sauter l'annonce.
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute("_GUILD = true; _ZONE = _SECRET; _TARGET = { name = _SECRET, hostile = true }")
        g._FIRE("PLAYER_DEAD")
        lua.execute("_ZONE = nil; _TARGET = nil")
        g._ADVANCE(1)
        (sent,) = list(g._ADDON_SENT.values())
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
        g._FIRE("PLAYER_DEAD")
        g._ADVANCE(1)
        deaths = [s.text for s in g._ADDON_SENT.values() if s.text.startswith("D\t")]
        assert len(deaths) == 1 and "\tLoup des Tarides\t" in deaths[0]
        assert g._NS.DeathSource() == "tueur d'après mémoire (récap absent)"
        # Un souvenir trop vieux, sans combat entre-temps, ne compte pas ; une cible amicale n'est jamais retenue.
        lua.execute("_ADDON_SENT = {}; _TARGET = { name = 'Kobold', hostile = true }")
        g._FIRE("PLAYER_TARGET_CHANGED")
        lua.execute("_TARGET = nil")
        g._ADVANCE(61)
        lua.execute("_TARGET = { name = 'Jaina', hostile = false }")
        g._FIRE("PLAYER_TARGET_CHANGED")
        lua.execute("_TARGET = nil")
        g._FIRE("PLAYER_DEAD")
        g._ADVANCE(1)
        deaths = [s.text for s in g._ADDON_SENT.values() if s.text.startswith("D\t")]
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
        g._FIRE("PLAYER_DEAD")  # première mort de la session : récap n° 1, qui prime sur la cible
        g._ADVANCE(1)
        g._FIRE("PLAYER_DEAD")  # deuxième : une chute
        g._ADVANCE(1)
        deaths = [s.text for s in g._ADDON_SENT.values() if s.text.startswith("D\t")]
        assert "\tMajordome Executus\t" in deaths[0] and "\tune chute\t" in deaths[1]
        events = g._NS.char.events
        assert events[1].killer == "Majordome Executus" and events[1].env is None
        assert events[2].env == "Falling" and events[2].killer is None
        assert g._NS.DeathSource() == "tueur d'après récap (récap présent)"
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
        g._FIRE("PLAYER_DEAD")
        day1 = g.date("%Y-%m-%d")
        g._ADVANCE(3 * 3600)  # 01:00 le lendemain : le ticker a tourné
        day2 = g.date("%Y-%m-%d")
        assert day1 != day2
        g._FIRE("PLAYER_DEAD")
        char = g.WoWForeverGuildeDB.characters["Player-1-000ABC01"]
        assert char.journal[day1].deaths == 1 and char.counters.deaths == 2
        g._FIRE("PLAYER_LOGOUT")
        assert char.journal[day2].deaths == 2

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
        assert g._POPUP.which == "WFG_TRANSFER" and "Thrall" in g._POPUP.text
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
        g.SlashCmdList.WOWFOREVERGUILDE("")
        # La ligne de statut dit combien de recettes sont connues.
        assert "Alchimie 290 · 1 recettes" in g.WoWForeverGuildeFrame.statusLines.professions.text

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
        g._FIRE("PLAYER_DEAD")
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


class TestPositions:
    """Partage de position : émission, réception sur la carte, infobulle, menu, règle symétrique."""

    def test_position_is_broadcast_at_login_then_on_move_zone_change_and_heartbeat(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        assert g._PREFIXES["WFG"] is True
        # Sans guilde : rien ne part, le client moderne interdit les canaux de chat aux addons.
        assert list(g._ADDON_SENT.values()) == []
        lua.execute("_GUILD = true")
        g._ADVANCE(10)
        (first,) = list(g._ADDON_SENT.values())
        # Nom complet, classe, niveau, carte, coordonnées, zone, talents, sur le canal de guilde.
        assert (first.prefix, first.kind) == ("WFG", "GUILD")
        assert (
            first.text
            == "P\t1\tPlayer-1-000ABC01\tThrall Fils-de-Durotan\tSHAMAN\t60\t1429\t0.5000\t0.5000\tForêt d'Elwynn\t\tAmélioration 0/8/1\t"
        )
        # Immobile : rien de plus à la lecture suivante.
        g._ADVANCE(10)
        assert len(list(g._ADDON_SENT.values())) == 1
        # Déplacé : nouvel envoi.
        lua.execute("_MAP.x = 0.52")
        g._ADVANCE(10)
        second = list(g._ADDON_SENT.values())[-1]
        assert second.kind == "GUILD" and "\t0.5200\t" in second.text
        # Changement de zone : envoi 2 s plus tard, même en combat.
        lua.execute("_COMBAT = true; _ZONE = 'Marais des Chagrins'")
        g._FIRE("ZONE_CHANGED_NEW_AREA")
        g._FIRE("ZONE_CHANGED")
        g._ADVANCE(2)
        assert (
            len(list(g._ADDON_SENT.values())) == 3
            and "Marais des Chagrins" in list(g._ADDON_SENT.values())[-1].text
        )
        lua.execute("_COMBAT = false")
        # Immobile : battement de cœur au bout de 60 s.
        g._ADVANCE(50)
        assert len(list(g._ADDON_SENT.values())) == 3
        g._ADVANCE(10)
        assert len(list(g._ADDON_SENT.values())) == 4
        # En instance (pas de coordonnées) : carte seule.
        lua.execute("_MAP.x = nil; _INSTANCE = 'party'")
        g._ADVANCE(10)
        assert list(g._ADDON_SENT.values())[-1].text.split("\t")[6:9] == ["1429", "", ""]
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
        assert list(g._ADDON_SENT.values())[-1].text == "L\t1\tPlayer-1-000ABC01"
        assert list(g._NS.Positions.peers.items()) == [] and list(g._PINS.added.items()) == []
        assert any("Position masquée" in m for m in list(g._CHAT.values()))
        receive(lua, JAINA)
        g._ADVANCE(60)
        assert list(g._NS.Positions.peers.items()) == [] and len(list(g._ADDON_SENT.values())) == 2
        g._NS.Positions.SetSharing(True)
        assert list(g._ADDON_SENT.values())[-1].text.startswith("P\t1\tPlayer-1-000ABC01\t")
        # Déconnexion : on prévient les autres.
        g._FIRE("PLAYER_LOGOUT")
        assert list(g._ADDON_SENT.values())[-1].text == "L\t1\tPlayer-1-000ABC01"

    def test_lfg_flag_travels_with_the_position_and_shows_in_tooltip_and_list(self):
        lua = boot()
        g = lua.globals()
        lua.execute("_GUILD = true")  # les messages addon passent par le canal de guilde
        login(lua)
        lua.execute(FAKE_PINS)
        g.SlashCmdList.WOWFOREVERGUILDE("lfg Gnomeregan ce soir")
        assert list(g._ADDON_SENT.values())[-1].text.endswith("\tAmélioration 0/8/1\tGnomeregan ce soir")
        assert any("Gnomeregan ce soir" in m for m in list(g._CHAT.values()))
        receive(lua, JAINA + "\tStratholme")
        peer = g._NS.Positions.peers["Player-1-00000JAI"]
        assert peer.lfg == "Stratholme"
        g._NS.MapUI.ShowTooltip(peer, None)
        assert "cherche groupe : Stratholme" in list(g.GameTooltip.lines.values())
        g.SlashCmdList.WOWFOREVERGUILDE("lfg")
        assert g._NS.Positions.lfg is None and list(g._ADDON_SENT.values())[-1].text.endswith(
            "\tAmélioration 0/8/1\t"
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
        sent_before = len(list(g._ADDON_SENT.values()))
        # Un joueur hostile me frappe hors instance : rien ne part tout seul (ça spammerait en zone contestée).
        lua.execute(
            "_CLEU = { 0, 'SWING_DAMAGE', false, 'Player-1-00000EVIL', 'Garrosh', 0x548, 0, 'Player-1-000ABC01', 'Thrall', 0x511, 0, 120 }"
        )
        g._FIRE("COMBAT_LOG_EVENT_UNFILTERED")
        assert len(list(g._ADDON_SENT.values())) == sent_before
        # /mf sos avec un joueur ciblé : appel avec son nom et sa classe.
        lua.execute("_TARGET = { name = 'Garrosh', class = 'WARRIOR', player = true }")
        g.SlashCmdList.WOWFOREVERGUILDE("sos")
        sent = list(g._ADDON_SENT.values())
        assert len(sent) == sent_before + 1
        assert (
            sent[-1].text
            == "G\t1\tPlayer-1-000ABC01\tThrall Fils-de-Durotan\tSHAMAN\t60\t1429\t0.5000\t0.5000\tForêt d'Elwynn\t\tGarrosh\tWARRIOR"
        )
        assert any("Appel à l'aide envoyé" in m for m in list(g._CHAT.values()))
        # Un seul appel par minute : le second est refusé avec le délai restant.
        g._ADVANCE(10)
        g.SlashCmdList.WOWFOREVERGUILDE("sos")
        assert len(list(g._ADDON_SENT.values())) == len(sent)
        assert any("réessaie dans 50 s" in m for m in list(g._CHAT.values()))
        # Cible monstre ou pas de cible : appel sans agresseur. Le bouton fait la même chose que la commande.
        g._ADVANCE(51)
        lua.execute("_TARGET = { name = 'Sanglier', class = nil, player = false }")
        g._NS.Positions.SOS()
        assert list(g._ADDON_SENT.values())[-1].text.endswith("\tForêt d'Elwynn\t\t\t")
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
