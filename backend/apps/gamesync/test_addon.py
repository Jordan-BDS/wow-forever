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
        on_disk = {str(p.relative_to(ADDON_DIR)) for p in ADDON_DIR.rglob("*.lua")}
        assert on_disk == listed
        lua = boot()
        ns = lua.globals()._NS
        names = sorted(ns.collectors[i].name for i in range(1, len(ns.collectors) + 1))
        assert names == sorted(
            ["identity", "gear", "talents", "professions", "reputation", "attunements", "lockouts", "pvp", "pve", "gathering", "quests", "deaths", "positions"]
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
        (first,) = list(g._ADDON_SENT.values())
        # Sans guilde encore : canal caché. Nom complet, classe, niveau, carte, coordonnées, zone, talents.
        assert (first.prefix, first.kind, first.target) == ("WFG", "CHANNEL", 5)
        assert (
            first.text
            == "P\t1\tPlayer-1-000ABC01\tThrall Fils-de-Durotan\tSHAMAN\t60\t1429\t0.5000\t0.5000\tForêt d'Elwynn\t\tAmélioration 0/8/1\t"
        )
        # Immobile : rien de plus à la lecture suivante.
        g._ADVANCE(10)
        assert len(list(g._ADDON_SENT.values())) == 1
        # Dans la guilde et déplacé : canal de guilde.
        lua.execute("_GUILD = true; _MAP.x = 0.52")
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

    def test_gank_is_detected_in_the_combat_log_and_alerts_members_nearby(self):
        lua = boot()
        g = lua.globals()
        login(lua)
        lua.execute(FAKE_PINS)
        sent_before = len(list(g._ADDON_SENT.values()))
        # Un joueur hostile me frappe hors instance : appel à l'aide avec sa classe.
        lua.execute(
            "_CLEU = { 0, 'SWING_DAMAGE', false, 'Player-1-00000EVIL', 'Garrosh', 0x548, 0, 'Player-1-000ABC01', 'Thrall', 0x511, 0, 120 }"
        )
        g._FIRE("COMBAT_LOG_EVENT_UNFILTERED")
        sent = list(g._ADDON_SENT.values())
        assert len(sent) == sent_before + 1
        assert (
            sent[-1].text
            == "G\t1\tPlayer-1-000ABC01\tThrall Fils-de-Durotan\tSHAMAN\t60\t1429\t0.5000\t0.5000\tForêt d'Elwynn\t\tGarrosh\tWARRIOR"
        )
        # Un seul appel par minute ; rien en instance, en duel, ni contre un monstre.
        g._FIRE("COMBAT_LOG_EVENT_UNFILTERED")
        g._ADVANCE(61)
        lua.execute("_INSTANCE = 'pvp'")
        g._FIRE("COMBAT_LOG_EVENT_UNFILTERED")
        lua.execute("_INSTANCE = nil")
        g._FIRE("DUEL_REQUESTED")
        g._FIRE("COMBAT_LOG_EVENT_UNFILTERED")
        g._FIRE("DUEL_FINISHED")
        lua.execute("_CLEU[6] = 0xa48")  # un monstre (TYPE_NPC + CONTROL_NPC), pas un joueur
        g._FIRE("COMBAT_LOG_EVENT_UNFILTERED")
        lua.execute("_CLEU[6] = 0x548; _CLEU[2] = 'DAMAGE_SHIELD'")  # Épines : c'est moi qui frappe
        g._FIRE("COMBAT_LOG_EVENT_UNFILTERED")
        lua.execute("_CLEU[2] = 'SPELL_DAMAGE'")
        g.StartDuel("Garrosh")  # lanceur du duel : pas de DUEL_REQUESTED, mais le hook
        g._FIRE("COMBAT_LOG_EVENT_UNFILTERED")
        g._FIRE("DUEL_FINISHED")
        lua.execute("_CLEU[6] = 0xa48")
        g._FIRE("COMBAT_LOG_EVENT_UNFILTERED")
        assert len(list(g._ADDON_SENT.values())) == len(sent) + 1  # le battement de cœur des 60 s seulement
        # Le familier d'un joueur hostile compte (contrôlé par un joueur), même sans classe connue.
        g._ADVANCE(61)
        lua.execute(
            "_CLEU = { 0, 'SWING_DAMAGE', false, 'Pet-0-0000PET', 'Loup', 0x1148, 0, 'Player-1-000ABC01', 'Thrall', 0x511, 0, 40 }"
        )
        g._FIRE("COMBAT_LOG_EVENT_UNFILTERED")
        assert list(g._ADDON_SENT.values())[-1].text.endswith("\tLoup\t")
        # /wfg sos manuel, puis refusé sans partage.
        g._ADVANCE(61)
        g.SlashCmdList.WOWFOREVERGUILDE("sos")
        assert list(g._ADDON_SENT.values())[-1].text.startswith("G\t1\tPlayer-1-000ABC01\t") and any(
            "Appel à l'aide envoyé" in m for m in list(g._CHAT.values())
        )
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
            and toast.header.text == "⚔ Appel à l'aide ⚔"
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
        # Un message chuchoté avec le bon préfixe est ignoré ; le canal caché est accepté.
        g._FIRE("CHAT_MSG_ADDON", "WFG", JAINA, "WHISPER", "Jaina-Forever")
        assert list(g._NS.Positions.peers.items()) == []
        g._FIRE("CHAT_MSG_ADDON", "WFG", JAINA, "CHANNEL", "Jaina-Forever", "", 0, 5, "wfgdeaths")
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
