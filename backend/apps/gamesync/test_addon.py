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
        on_disk = {str(p.relative_to(ADDON_DIR)) for p in ADDON_DIR.rglob("*.lua")}
        assert on_disk == listed
        lua = boot()
        ns = lua.globals()._NS
        names = sorted(ns.collectors[i].name for i in range(1, len(ns.collectors) + 1))
        assert names == sorted(
            ["identity", "gear", "talents", "professions", "reputation", "attunements", "lockouts", "pvp", "pve", "gathering", "quests", "deaths"]
        )  # fmt: skip
        assert lua.globals().SlashCmdList.WOWFOREVERGUILDE is not None

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
        lua.execute(
            "_CLEU = { 0, 'SWING_DAMAGE', false, 'Creature-0-1', 'Sanglier des Tarides', 0, 0, 'Player-1-000ABC01', 'Thrall' }"
        )
        g._FIRE("COMBAT_LOG_EVENT_UNFILTERED")
        g._FIRE("PLAYER_DEAD")
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

    def test_death_is_announced_on_hidden_channel_and_shown_as_toast(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute(
            "_CLEU = { 0, 'ENVIRONMENTAL_DAMAGE', false, nil, nil, 0, 0, 'Player-1-000ABC01', 'Thrall', 0, 0, 'Falling' }"
        )
        g._FIRE("COMBAT_LOG_EVENT_UNFILTERED")
        g._FIRE("PLAYER_DEAD")
        (sent,) = list(g._SENT.values())
        assert sent.kind == "CHANNEL" and sent.target == 5
        assert sent.text.startswith(
            "WFG\tDEATH\t1\tPlayer-1-000ABC01\tThrall\tFils-de-Durotan\tChaman\t60\tune chute\tForêt d'Elwynn\t"
        )
        # Réception par un autre addon : popup + son.
        g._FIRE("CHAT_MSG_CHANNEL", sent.text, "Thrall", "", "", "", "", 0, 5, "wfgdeaths")
        toast = g.WoWForeverGuildeDeath
        assert toast.shown is True and "Thrall" in toast.text.text and "une chute" in toast.text.text
        assert len(list(g._SOUNDS.values())) == 1
        # Désactivé → rien n'est envoyé.
        lua.execute("WoWForeverGuildeDB.settings.announceDeaths = false")
        g._FIRE("PLAYER_DEAD")
        assert len(list(g._SENT.values())) == 1

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
            counters = { deaths = 9 }, journal = {}, events = {}, previous_guids = {}, created_at = 1, updated_at = 2, counting_since = 1 } } }
        """)
        login(lua)
        assert g._POPUP.which == "WFG_TRANSFER" and "Thrall" in g._POPUP.text
        ns = g._NS
        ns.Store.Merge(ns.char, g.WoWForeverGuildeDB.characters["Player-1-OLD"])
        char = g.WoWForeverGuildeDB.characters["Player-1-000ABC01"]
        assert char.counters.deaths == 9 and char.previous_guids[1] == "Player-1-OLD"
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
