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


KORKRON = "{ name = 'Garrosh Hurlenfer', class = 'WARRIOR', player = true, hostile = true, guild = \"Les Kor'kron\" }"
NAZGREL = "{ name = 'Nazgrel', class = 'SHAMAN', player = true, hostile = true, guild = \"Les Kor'kron\" }"


class TestGuildBounty:
    """Prime sur une guilde adverse : `/mf prime guilde`, chaque membre lu avec sa guilde compte."""

    def post(self, lua, g, mf, command="prime guilde 20 5"):
        lua.execute(f"_TARGET = {KORKRON}")
        mf(command)
        ask = popup(g)
        g._NS.UI.Dialogs.WFG_BOUNTY.OnAccept(None, ask.data)
        ask.Hide(ask)
        (entry,) = bounties(g).values()
        return ask, entry

    def test_prime_guilde_takes_the_guild_of_my_target(self):
        lua, g, mf = start()
        ask, entry = self.post(lua, g, mf)
        assert "20 po par kill sur la guilde Les Kor'kron" in ask.message
        assert "Chaque membre de cette guilde" in ask.message
        assert (entry.name, entry.kind, entry.gold, entry.max) == ("Les Kor'kron", "g", 20, 5)
        assert sent(g, "B")[-1].split("\t")[13] == "g"
        assert any("Prime posée sur la guilde Les Kor'kron" in line for line in chat(g))
        # Une seule par guilde ; le nom se donne aussi à la main ; une cible sans guilde est refusée.
        mf("prime guilde Les Kor'kron 10")
        assert popup(g) is None and any("déjà une prime en cours sur la guilde" in line for line in chat(g))
        lua.execute("_TARGET = { name = 'Sylvanas', class = 'HUNTER', player = true, hostile = true }")
        mf("prime guilde 10")
        assert popup(g) is None and any("pas de guilde lisible" in line for line in chat(g))
        # Elle remonte au site comme prime de guilde, et s'annule par son nom ou par la cible.
        (exported,) = decode_export(logout_code(lua))["bounties"]
        assert (exported["name"], exported["kind"]) == ("Les Kor'kron", "g")
        mf("prime annuler guilde Les Kor'kron")
        assert entry.cancelled == g._CLOCK.now

    def test_any_member_of_the_guild_is_announced_and_carries_the_coin(self):
        lua, g, mf = start()
        self.post(lua, g, mf)
        lua.execute("_TARGET = nil")
        # Un joueur du même nom que la guilde, ou sans guilde lue : rien.
        lua.execute(
            '_UNITS = { nameplate1 = { name = "Les Kor\'kron", class = "ROGUE", hostile = true, player = true } }'
        )
        g._FIRE("NAME_PLATE_UNIT_ADDED", "nameplate1")
        g._ADVANCE(2)
        assert sent(g, "S") == [] and g._NS.Nameplates.Mark("nameplate1") is None
        lua.execute(f"_UNITS = {{ nameplate2 = {NAZGREL} }}")
        g._FIRE("NAME_PLATE_UNIT_ADDED", "nameplate2")
        g._ADVANCE(2)
        (line,) = sent(g, "S")
        assert line.split("\t")[6:8] == ["Nazgrel", "SHAMAN"]
        toast = g.WoWForeverGuildeDeath
        assert toast.shown is True and "Nazgrel" in toast.text.text and "<Les Kor'kron>" in toast.text.text
        assert g._NS.Nameplates.Mark("nameplate2").coin is True

    def test_kills_count_per_member_and_the_export_names_the_guild(self):
        lua, g, mf = start()
        _, entry = self.post(lua, g, mf)
        lua.execute("_TARGET = nil")
        lua.execute(f"_UNITS = {{ nameplate1 = {KORKRON}, nameplate2 = {NAZGREL} }}")
        g._FIRE("NAME_PLATE_UNIT_ADDED", "nameplate1")
        g._FIRE("NAME_PLATE_UNIT_ADDED", "nameplate2")
        uther = "Player-1-00000UTH\tUther Lumière\tPALADIN"
        now = g._CLOCK.now
        # Uther a lu la guilde de sa victime : son « H » la porte. Deux victimes au même moment : deux kills.
        receive(lua, f"H\t1\t{uther}\tGarrosh Hurlenfer\tWARRIOR\t{now}\tDurotar\t\tWARRIOR\t\tLes Kor'kron")
        receive(lua, f"H\t1\t{uther}\tNazgrel\tSHAMAN\t{now}\tDurotar\t\tSHAMAN\t\tLes Kor'kron")
        receive(
            lua, f"H\t1\tPlayer-1-00000ARC\tArthas\tPALADIN\tNazgrel\tSHAMAN\t{now + 2}\tDurotar\t"
        )  # son groupe
        assert entry.kills == 2
        # Un « H » sans guilde (addon plus ancien) sur un joueur que j'ai lu moi-même : compté aussi.
        g._ADVANCE(300)
        g._FIRE("NAME_PLATE_UNIT_ADDED", "nameplate1")
        receive(lua, f"H\t1\t{uther}\tGarrosh\tWARRIOR\t{g._CLOCK.now}\tDurotar\t")
        assert entry.kills == 3
        # Un inconnu, sans guilde lue nulle part : rien.
        receive(lua, f"H\t1\t{uther}\tMalkorok\tWARRIOR\t{g._CLOCK.now}\tDurotar\t")
        assert entry.kills == 3

    def test_my_own_kill_names_the_guild_for_the_site_and_the_guild(self):
        lua, g, mf = start()
        receive(
            lua,
            f"B\t1\tJAI-9\t{JAINA}\tJaina Portvaillant\tMAGE\tLes Kor'kron\t20\t5\t{g._CLOCK.now}\t0\t0\t1\tg",
        )
        entry = bounties(g)["JAI-9"]
        assert entry.kind == "g" and any("la guilde Les Kor'kron" in line for line in chat(g))
        lua.execute(f"_UNITS = {{ nameplate1 = {KORKRON} }}")
        g._FIRE("NAME_PLATE_UNIT_ADDED", "nameplate1")
        g._ADVANCE(5)
        g._FIRE(
            "CHAT_MSG_COMBAT_HONOR_GAIN",
            "Garrosh meurt, victoire honorable Rang : Grunt (Points d'honneur estimés : 198)",
        )
        (pk,) = [e for e in g._NS.char.events.values() if e.k == "pk"]
        assert (pk.name, pk.guild) == ("Garrosh Hurlenfer", "Les Kor'kron")
        assert entry.kills == 1
        assert sent(g, "H")[-1].split("\t")[11] == "Les Kor'kron"


class TestTab:
    """Onglet « Primes » de /mf : le formulaire pose une prime, la liste montre celles en cours."""

    def open(self):
        lua, g, mf = start()
        mf("primes")
        panel = g.WoWForeverGuildeBounties
        assert panel.shown is True and g._NS.UI.Shown("bounties") is True
        return lua, g, mf, panel

    def click(self, button):
        button.scripts.OnClick(button)

    def test_the_form_posts_a_bounty_after_confirmation(self):
        lua, g, mf, panel = self.open()
        assert panel.empty.shown is True and panel.kills.text == "1"
        # Rien de rempli : la raison est dite dans l'onglet, rien n'est demandé.
        self.click(panel.post)
        assert "Donne un nom" in panel.status.text and popup(g) is None
        # « Ma cible » reprend le nom du joueur adverse ciblé.
        self.click(panel.target)
        assert "Cible un joueur adverse" in panel.status.text
        lua.execute(f"_TARGET = {KORKRON}")
        self.click(panel.target)
        assert panel.name.text == "Garrosh Hurlenfer" and panel.status.text == ""
        panel.gold.text = ""
        self.click(panel.post)
        assert "Une prime va de 1 à" in panel.status.text and popup(g) is None
        panel.gold.text, panel.kills.text = "50", "3"
        self.click(panel.post)
        ask = popup(g)
        assert "50 po par kill sur Garrosh Hurlenfer" in ask.message and "150 po au plus" in ask.message
        assert "Confirme" in panel.status.text and (panel.name.text, panel.kills.text) == ("", "1")
        g._NS.UI.Dialogs.WFG_BOUNTY.OnAccept(None, ask.data)
        ask.Hide(ask)
        g._ADVANCE(3)
        (line,) = g._NS.BountiesUI.Lines().values()
        assert "Garrosh Hurlenfer" in line.cells[1] and "50 po par kill" in line.cells[2]
        assert "annuler" in line.cells[5] and panel.empty.shown is False
        assert sent(g, "B")[-1].split("\t")[6:9] == ["Garrosh Hurlenfer", "50", "3"]

    def test_the_guild_box_takes_the_guild_of_my_target(self):
        lua, g, mf, panel = self.open()
        lua.execute(f"_TARGET = {KORKRON}")
        panel.guild.checked = True
        self.click(panel.guild)
        assert panel.nameLabel.text == "Guilde adverse"
        self.click(panel.target)
        assert panel.name.text == "Les Kor'kron"
        panel.gold.text, panel.kills.text = "20", ""  # kills vide : un kill
        self.click(panel.post)
        ask = popup(g)
        assert "20 po sur la guilde Les Kor'kron" in ask.message
        g._NS.UI.Dialogs.WFG_BOUNTY.OnAccept(None, ask.data)
        (entry,) = bounties(g).values()
        assert (entry.name, entry.kind, entry.max) == ("Les Kor'kron", "g", 1)

    def test_the_list_follows_the_guild_and_a_click_cancels_mine(self):
        lua, g, mf, panel = self.open()
        jaina_posts(lua, g)
        g._ADVANCE(3)
        (line,) = g._NS.BountiesUI.Lines().values()
        assert "Jaina Portvaillant" in line.cells[3] and line.cells[5] == ""
        # Celle d'une autre ne s'annule pas d'un clic.
        row = next(
            f for f in g._FRAMES.values() if f.entry and f.entry.id == line.entry.id and f.scripts.OnClick
        )
        self.click(row)
        assert popup(g) is None
        mf("prime Sylvanas 80")
        ask = popup(g)
        g._NS.UI.Dialogs.WFG_BOUNTY.OnAccept(None, ask.data)
        ask.Hide(ask)
        g._ADVANCE(3)
        first, second = g._NS.BountiesUI.Lines().values()  # les plus fortes d'abord
        assert "Sylvanas" in first.cells[1] and "annuler" in first.cells[5]
        mine = next(
            f for f in g._FRAMES.values() if f.entry and f.entry.id == first.entry.id and f.scripts.OnClick
        )
        self.click(mine)
        ask = popup(g)
        assert ask.which == "WFG_BOUNTY_CANCEL" and "Annuler ta prime sur Sylvanas" in ask.message
        g._NS.UI.Dialogs.WFG_BOUNTY_CANCEL.OnAccept(None, ask.data)
        g._ADVANCE(3)
        (left,) = g._NS.BountiesUI.Lines().values()
        assert "Garrosh Hurlenfer" in left.cells[1]
        assert list(g.WoWForeverGuildeDB.errors.values()) == []


class TestPortraitMenu:
    """Clic droit sur le portrait d'un joueur adverse : « Ajouter une prime » ouvre l'onglet, le nom rempli."""

    def menu(self, lua, g, tag="MENU_UNIT_ENEMY_PLAYER", unit="target"):
        lua.execute("""
          _ROOT = { buttons = {}, dividers = 0 }
          function _ROOT:CreateDivider() self.dividers = self.dividers + 1 end
          function _ROOT:CreateButton(text, fn) table.insert(self.buttons, { text = text, run = fn }) end
        """)
        g._MENUS[tag](None, g._ROOT, lua.table(unit=unit))
        return list(g._ROOT.buttons.values())

    def test_an_enemy_player_gets_the_entry_and_it_fills_the_form(self):
        lua, g, mf = start()
        lua.execute("_TARGET = { name = 'Sylvanas', class = 'HUNTER', player = true, hostile = true }")
        (add,) = self.menu(lua, g)
        assert add.text == "Ajouter une prime" and g._ROOT.dividers == 1
        add.run()
        panel = g.WoWForeverGuildeBounties
        assert panel.shown is True and g._NS.UI.Shown("bounties") is True
        assert (panel.name.text, panel.gold.text, panel.kills.text) == ("Sylvanas", "", "1")
        assert not panel.guild.checked and "Indique l'or" in panel.status.text
        # Il ne reste qu'à donner l'or : la prime part par la confirmation habituelle.
        panel.gold.text = "30"
        panel.post.scripts.OnClick(panel.post)
        assert "30 po sur Sylvanas" in popup(g).message

    def test_a_guilded_enemy_also_offers_a_bounty_on_the_guild(self):
        lua, g, mf = start()
        lua.execute(f"_TARGET = {KORKRON}")
        add, guild = self.menu(lua, g, tag="MENU_UNIT_TARGET")
        assert guild.text == "Prime sur la guilde Les Kor'kron"
        guild.run()
        panel = g.WoWForeverGuildeBounties
        assert panel.guild.checked is True and panel.nameLabel.text == "Guilde adverse"
        assert panel.name.text == "Les Kor'kron"
        panel.gold.text = "20"
        panel.post.scripts.OnClick(panel.post)
        assert "20 po sur la guilde Les Kor'kron" in popup(g).message

    def test_nothing_is_added_for_a_friend_a_creature_or_a_bare_menu(self):
        lua, g, mf = start()
        lua.execute("_TARGET = { name = 'Jaina', class = 'MAGE', player = true }")
        assert self.menu(lua, g) == []
        lua.execute("_TARGET = { name = 'Sanglier', hostile = true }")
        assert self.menu(lua, g) == [] and g._ROOT.dividers == 0
        g._MENUS.MENU_UNIT_TARGET(None, g._ROOT, None)  # menu sans unité : rien, et pas d'erreur
        assert list(g.WoWForeverGuildeDB.errors.values()) == []
