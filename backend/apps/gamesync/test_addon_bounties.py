# ruff: noqa: E501 — les chaînes Lua des scénarios sont longues par nature
"""Primes posées à la main, côté addon : pose en jeu, diffusion aux guildiens, cible vue, kills, export."""

from __future__ import annotations

from .format import decode_export
from .test_addon import FAKE_PINS, boot, login, logout_code, popup, receive

GARROSH = "{ name = 'Garrosh Hurlenfer', class = 'WARRIOR', player = true, hostile = true }"
ME = "Player-1-000ABC01"
JAINA = "Player-1-00000JAI"


def sent(g, kind: str) -> list[str]:
    return [s.text for s in g._ADDON_SENT.values() if s.text.startswith(kind + "\t")]


def chat(g) -> list[str]:
    return list(g._CHAT.values())


def start():
    lua = boot()
    g = lua.globals()
    lua.execute("_GUILD = true")
    login(lua)
    lua.execute(FAKE_PINS)
    return lua, g, g.SlashCmdList.WOWFOREVERGUILDE


def bounties(g) -> dict:
    return {key: entry for key, entry in g.WoWForeverGuildeDB.bounties.items()}


def jaina_posts(lua, g, *, gold=50, kills=3, live=1, cancelled=0, counted=0, bounty="JAI-1") -> str:
    """Jaina pose une prime sur Garrosh : le message « B » qu'elle envoie à la guilde."""
    t = g._CLOCK.now
    line = f"B\t1\t{bounty}\t{JAINA}\tJaina Portvaillant\tMAGE\tGarrosh Hurlenfer\t{gold}\t{kills}\t{t}\t{cancelled}\t{counted}\t{live}"
    receive(lua, line)
    return bounty


class TestPosting:
    def test_prime_on_my_target_asks_then_tells_the_guild(self):
        lua, g, mf = start()
        lua.execute(f"_TARGET = {GARROSH}")
        mf("prime 50 3")
        # Rien n'est posé avant la confirmation : la fenêtre dit à quoi je m'engage.
        ask = popup(g)
        assert ask.which == "WFG_BOUNTY" and "50 po par kill sur Garrosh Hurlenfer" in ask.message
        assert "150 po au plus" in ask.message and bounties(g) == {} and sent(g, "B") == []
        g._NS.UI.Dialogs.WFG_BOUNTY.OnAccept(None, ask.data)
        (entry,) = bounties(g).values()
        assert (entry.name, entry.gold, entry.max, entry.kills, entry.guid) == (
            "Garrosh Hurlenfer",
            50,
            3,
            0,
            ME,
        )
        fields = sent(g, "B")[-1].split("\t")
        assert fields[2] == entry.id and fields[3] == ME and fields[6:9] == ["Garrosh Hurlenfer", "50", "3"]
        assert fields[10:] == ["0", "0", "1"]  # ni annulée ni kill compté, et elle vient d'être posée
        assert any("Prime posée sur Garrosh Hurlenfer" in line for line in chat(g))
        # Une seule prime en cours par cible : la seconde est refusée sans rien demander.
        ask.Hide(ask)
        mf("prime 10")
        assert popup(g) is None and any("déjà une prime en cours" in line for line in chat(g))

    def test_one_kill_by_default_and_a_name_works_without_a_target(self):
        lua, g, mf = start()
        mf("prime Sylvanas 20")
        ask = popup(g)
        assert "20 po sur Sylvanas" in ask.message and "1 kill" in ask.message
        g._NS.UI.Dialogs.WFG_BOUNTY.OnAccept(None, ask.data)
        (entry,) = bounties(g).values()
        assert (entry.name, entry.gold, entry.max) == ("Sylvanas", 20, 1)

    def test_what_cannot_be_a_bounty_is_refused_and_said(self):
        lua, g, mf = start()
        mf("prime 50")  # pas de cible
        assert popup(g) is None and any("Cible un joueur adverse" in line for line in chat(g))
        lua.execute("_TARGET = { name = 'Jaina', class = 'MAGE', player = true }")  # un allié
        mf("prime 50")
        assert popup(g) is None and any("joueur adverse" in line for line in chat(g))
        lua.execute(f"_TARGET = {GARROSH}")
        mf("prime 0")
        mf("prime 50 500")
        assert popup(g) is None and bounties(g) == {}
        assert sum("Une prime va de 1 à" in line for line in chat(g)) == 2

    def test_the_old_rehearsal_and_the_list_are_still_there(self):
        lua, g, mf = start()
        mf("prime Garrosh")  # un nom seul : l'essai du popup du Wanted, comme avant
        assert popup(g) is None and bounties(g) == {}
        mf("prime test Garrosh")
        assert popup(g) is None and bounties(g) == {}
        mf("prime")
        assert any("Aucune prime en cours" in line for line in chat(g))
        jaina_posts(lua, g)
        mf("prime")
        assert any("Prime sur Garrosh Hurlenfer : 50 po par kill" in line for line in chat(g))

    def test_cancelling_tells_the_guild_and_goes_to_the_site(self):
        lua, g, mf = start()
        lua.execute(f"_TARGET = {GARROSH}")
        mf("prime 50")
        g._NS.UI.Dialogs.WFG_BOUNTY.OnAccept(None, popup(g).data)
        g._ADVANCE(30)
        mf("prime annuler")
        (entry,) = bounties(g).values()
        assert entry.cancelled == g._CLOCK.now and g._NS.Bounties.Match("Garrosh Hurlenfer") is None
        assert sent(g, "B")[-1].split("\t")[10] == str(g._CLOCK.now)
        # L'export porte la prime et son annulation : le site reconnaît le commanditaire par son personnage.
        (exported,) = decode_export(logout_code(lua))["bounties"]
        assert (exported["name"], exported["gold"], exported["max"], exported["guid"]) == (
            "Garrosh Hurlenfer",
            50,
            1,
            ME,
        )
        assert exported["cancelled"] == entry.cancelled and exported["id"] == entry.id


class TestGuild:
    def test_a_bounty_posted_by_a_guildmate_is_kept_and_relayed_to_the_site(self):
        lua, g, mf = start()
        bounty = jaina_posts(lua, g)
        entry = bounties(g)[bounty]
        assert (entry.name, entry.gold, entry.max, entry.by, entry.guid) == (
            "Garrosh Hurlenfer",
            50,
            3,
            "Jaina Portvaillant",
            JAINA,
        )
        assert any("Nouvelle prime" in line and "Garrosh Hurlenfer" in line for line in chat(g))
        # Redite (résumé à la connexion d'un autre) : ni doublon ni nouvelle annonce.
        before = len(chat(g))
        jaina_posts(lua, g, live=0, counted=1)
        assert len(bounties(g)) == 1 and entry.kills == 1 and len(chat(g)) == before
        # Je la fais remonter au site : le premier qui se déconnecte suffit.
        (exported,) = decode_export(logout_code(lua))["bounties"]
        assert (exported["id"], exported["guid"], exported["gold"]) == (bounty, JAINA, 50)

    def test_bounties_are_asked_at_login_and_answered_once(self):
        lua, g, mf = start()
        g._ADVANCE(10)
        assert sent(g, "B") == ["B\t1"]
        jaina_posts(lua, g)
        # Un membre se connecte et demande : je réponds après un délai, sauf si quelqu'un l'a déjà fait.
        receive(lua, "B\t1", "Uther-Forever")
        g._ADVANCE(7)
        lines = sent(g, "B")
        assert len(lines) == 2 and lines[-1].split("\t")[2] == "JAI-1" and lines[-1].endswith("\t0")
        receive(lua, "B\t1", "Uther-Forever")
        jaina_posts(lua, g, live=0)  # Jaina répond avant moi
        g._ADVANCE(7)
        assert len(sent(g, "B")) == 2

    def test_a_cancelled_bounty_closes_everywhere(self):
        lua, g, mf = start()
        bounty = jaina_posts(lua, g)
        jaina_posts(lua, g, live=0, cancelled=g._CLOCK.now)
        assert bounties(g)[bounty].cancelled == g._CLOCK.now
        assert g._NS.Bounties.Match("Garrosh") is None
        assert any("a annulé sa prime" in line for line in chat(g))


class TestSeen:
    def test_only_a_bounty_target_is_announced_and_only_once(self):
        lua, g, mf = start()
        jaina_posts(lua, g)
        # Un joueur adverse sans prime : rien ne part.
        lua.execute(
            "_UNITS = { nameplate1 = { name = 'Sylvanas', class = 'HUNTER', hostile = true, player = true } }"
        )
        g._FIRE("NAME_PLATE_UNIT_ADDED", "nameplate1")
        g._ADVANCE(2)
        assert sent(g, "S") == []
        # La cible d'une prime : une annonce, un popup, une pièce d'or sur la carte.
        lua.execute(f"_UNITS = {{ nameplate2 = {GARROSH} }}")
        g._FIRE("NAME_PLATE_UNIT_ADDED", "nameplate2")
        g._FIRE("NAME_PLATE_UNIT_ADDED", "nameplate2")  # relue aussitôt : toujours une seule annonce
        g._ADVANCE(2)
        (line,) = sent(g, "S")
        fields = line.split("\t")
        assert fields[2] == "JAI-1" and fields[3] == ME and fields[6:8] == ["Garrosh Hurlenfer", "WARRIOR"]
        assert fields[9:12] == ["1429", "0.5000", "0.5000"]
        toast = g.WoWForeverGuildeDeath
        assert toast.shown is True and "Prime en vue" in toast.header.text
        assert "Garrosh Hurlenfer" in toast.text.text and "50 po par kill" in toast.footer.text
        coin = g._NS.MapUI.BountyIcons()["JAI-1"].map
        assert coin.gold.text == "50" and g._PINS.added[coin].map == 1429
        # Revu dans les deux minutes : pas de nouvelle annonce.
        g._ADVANCE(60)
        g._FIRE("NAME_PLATE_UNIT_ADDED", "nameplate2")
        g._ADVANCE(2)
        assert len(sent(g, "S")) == 1
        # Passé ce délai, je l'annonce de nouveau, mais le popup ne revient pas avant un quart d'heure.
        toast.shown = False
        g._ADVANCE(120)
        g._FIRE("NAME_PLATE_UNIT_ADDED", "nameplate2")
        g._ADVANCE(2)
        assert len(sent(g, "S")) == 2 and toast.shown is False

    def test_a_guildmate_who_saw_it_first_is_not_repeated(self):
        lua, g, mf = start()
        jaina_posts(lua, g)
        lua.execute(f"_UNITS = {{ nameplate1 = {GARROSH} }}")
        g._FIRE("NAME_PLATE_UNIT_ADDED", "nameplate1")
        # Avant la fin de mon délai, Uther l'annonce : je me tais, et je montre son observation.
        now = g._CLOCK.now
        receive(
            lua,
            f"S\t1\tJAI-1\tPlayer-1-00000UTH\tUther Lumière\tPALADIN\tGarrosh Hurlenfer\tWARRIOR\t{now}\t1411\t0.4000\t0.6000\tDurotar\tTranchecolline",
            "Uther-Forever",
        )
        g._ADVANCE(2)
        assert sent(g, "S") == []
        toast = g.WoWForeverGuildeDeath
        assert toast.shown is True and "Uther Lumière" in toast.text.text and "Durotar" in toast.footer.text
        coin = g._NS.MapUI.BountyIcons()["JAI-1"].map
        assert g._PINS.added[coin].map == 1411
        # Trois minutes plus tard la pièce a quitté la carte.
        g._ADVANCE(200)
        assert g._NS.MapUI.BountyIcons()["JAI-1"] is None

    def test_alerts_can_be_switched_off(self):
        lua, g, mf = start()
        jaina_posts(lua, g)
        g._NS.Bounties.SetAlerts(False)
        now = g._CLOCK.now
        receive(
            lua,
            f"S\t1\tJAI-1\tPlayer-1-00000UTH\tUther Lumière\tPALADIN\tGarrosh Hurlenfer\tWARRIOR\t{now}\t1411\t0.4000\t0.6000\tDurotar\t",
        )
        toast = g.WoWForeverGuildeDeath
        assert (toast is None or toast.shown is not True) and g._NS.MapUI.BountyIcons()["JAI-1"] is None
        assert bounties(g)["JAI-1"].seen.map == 1411  # l'observation reste connue

    def test_the_nameplate_of_a_target_carries_a_coin(self):
        lua, g, mf = start()
        jaina_posts(lua, g)
        lua.execute(f"_UNITS = {{ nameplate1 = {GARROSH} }}")
        g._FIRE("NAME_PLATE_UNIT_ADDED", "nameplate1")
        mark = g._NS.Nameplates.Mark("nameplate1")
        assert mark is not None and mark.coin is True
        # Prime annulée : la pièce quitte la plaque.
        jaina_posts(lua, g, live=0, cancelled=g._CLOCK.now)
        assert g._NS.Nameplates.Mark("nameplate1") is None


class TestKills:
    def kill(
        self, lua, g, hunter=("Player-1-00000UTH", "Uther Lumière", "PALADIN"), name="Garrosh Hurlenfer"
    ):
        guid, by, cls = hunter
        receive(
            lua, f"H\t1\t{guid}\t{by}\t{cls}\t{name}\tWARRIOR\t{g._CLOCK.now}\tDurotar\t", "Uther-Forever"
        )

    def test_kills_by_the_guild_are_counted_until_the_bounty_is_done(self):
        lua, g, mf = start()
        bounty = jaina_posts(lua, g, kills=2)
        self.kill(lua, g)
        self.kill(
            lua, g, hunter=("Player-1-00000ARC", "Arthas", "PALADIN")
        )  # le même kill, vu par son groupe
        entry = bounties(g)[bounty]
        assert entry.kills == 1 and g._NS.Bounties.Open(entry) is True
        assert any("Prime sur Garrosh Hurlenfer" in line and "1/2 kills" in line for line in chat(g))
        # Le commanditaire ne se doit rien : son kill ne compte pas.
        g._ADVANCE(300)
        self.kill(lua, g, hunter=(JAINA, "Jaina Portvaillant", "MAGE"))
        assert entry.kills == 1
        g._ADVANCE(300)
        self.kill(lua, g, name="Garrosh")  # prénom seul : la même cible
        assert entry.kills == 2 and g._NS.Bounties.Open(entry) is False
        assert g._NS.Bounties.Match("Garrosh Hurlenfer") is None

    def test_the_site_closes_a_bounty_through_the_companion(self):
        # Le compagnon recopie l'état du site dans le fichier, jeu fermé : une prime fermée n'alerte plus.
        lua = boot()
        g = lua.globals()
        lua.execute("""
          _GUILD = true
          WoWForeverGuildeDB = { bounties = {
            s7 = { id = "s7", name = "Garrosh Hurlenfer", gold = 50, max = 3, t = 1, by = "Jaina", kills = 1, closed = true },
            s8 = { id = "s8", name = "Sylvanas", gold = 20, max = 1, t = 1, by = "Jaina", kills = 0 },
          } }
        """)
        login(lua)
        assert g._NS.Bounties.Match("Garrosh Hurlenfer") is None
        assert g._NS.Bounties.Match("Sylvanas").id == "s8"
        # Posées sur le site : elles n'y retournent pas par l'export.
        assert decode_export(logout_code(lua))["bounties"] == []
