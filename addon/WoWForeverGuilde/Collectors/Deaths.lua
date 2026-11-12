-- Annonces de mort, en jeu seulement : message addon (préfixe WFG, type « D ») sur le canal de guilde, lu par les
-- autres addons, popup flottant 10 s avec son chez ceux qui l'affichent. Rien de visible dans le chat, rien vers
-- Discord. Le client moderne interdit aux addons les canaux de chat : pas de canal caché, il faut une guilde.
-- Ligne « D » : neuf champs lus par toutes les versions (guid, prénom, nom, classe, niveau, tueur, zone, sous-zone,
-- heure), puis cinq champs Wanted ajoutés en 0.5.0 et ignorés par les anciennes versions : tueur joueur (1/0), sa
-- classe, carte, x, y du mort. Au-delà de 255 octets, la sous-zone puis la zone sautent ; sinon rien ne part.
local ADDON, ns = ...

local function describeKiller(death)
  if death.env and ns.Data.ENVIRONMENTAL[death.env] then return ns.L[ns.Data.ENVIRONMENTAL[death.env]] end
  if death.killer and death.killer ~= "" then return death.killer end
  return ns.L.KILLER_UNKNOWN
end

local function encodeField(s)
  return (tostring(s or ""):gsub("[\t\n]", " "))
end

local parse -- défini plus bas, utilisé par ns.OnDeath pour son propre tableau Wanted

--- Appelé par le collecteur PvE à PLAYER_DEAD.
function ns.OnDeath(char, death)
  if not ns.db.settings.announceDeaths then return end
  if not (IsInGuild and IsInGuild()) then return end
  local api = (C_ChatInfo and C_ChatInfo.SendAddonMessage) or SendAddonMessage
  if not api then return end
  -- Jeton de classe (SHAMAN) et non le nom affiché (Chaman) : c'est la clé des couleurs de classe chez le receveur,
  -- qui retraduit dans sa langue. Les anciennes versions envoyaient le nom affiché : il reste accepté tel quel.
  local class = char.class
  if type(class) ~= "string" or class == "" then
    local ok, _, token = pcall(UnitClass, "player")
    class = ok and ns.plain(token) or ""
  end
  local fields = {
    encodeField(char.guid), encodeField(char.name), encodeField(char.surname), encodeField(class),
    tostring(char.level or 0), encodeField(describeKiller(death)), encodeField(death.zone), encodeField(death.sub),
    tostring(death.t or ns.now()),
    death.player and "1" or "0", encodeField(death.kclass), death.map and tostring(death.map) or "",
    death.x and string.format("%.4f", death.x) or "", death.y and string.format("%.4f", death.y) or "",
  }
  local line = ns.Data.DEATH_PREFIX .. table.concat(fields, "\t")
  for _, i in ipairs({ 8, 7 }) do
    if #line <= 255 then break end
    fields[i] = ""
    line = ns.Data.DEATH_PREFIX .. table.concat(fields, "\t")
  end
  if #line > 255 then return end
  local ok, result = ns.Risky("SendAddonMessage GUILD (mort)", pcall, api, ns.Data.ADDON_PREFIX, line, "GUILD")
  local sent = ok and (result == nil or result == true or result == 0)
  ns.Trace("envoi D (ma mort) → %s", sent and "accepté" or tostring(result))
  -- Ma propre mort nourrit mon tableau Wanted tout de suite (ligne de chat comprise) ; l'écho du jeu (on reçoit
  -- ses propres messages de guilde) sera reconnu comme un doublon, muet, et n'affichera que le popup.
  if sent and ns.Wanted then
    local info = parse(line)
    local ok, entry, added = pcall(ns.Wanted.RecordDeath, info)
    if not ok then
      ns.Store.LogError("wanted.record", entry)
    elseif entry and added and ns.db.settings.wantedAlerts then
      ns.Safe("wanted.announce", ns.Wanted.Announce, entry, info)
    end
  end
end

function parse(line)
  if line:sub(1, #ns.Data.DEATH_PREFIX) ~= ns.Data.DEATH_PREFIX then return nil end
  local fields = {}
  for field in (line:sub(#ns.Data.DEATH_PREFIX + 1) .. "\t"):gmatch("([^\t]*)\t") do fields[#fields + 1] = field end
  if #fields < 9 then return nil end
  return {
    guid = fields[1], name = fields[2], surname = fields[3], class = fields[4], level = tonumber(fields[5]) or 0,
    killer = fields[6], zone = fields[7], sub = fields[8], t = tonumber(fields[9]),
    -- Champs Wanted (0.5.0), absents chez les anciennes versions : alors pas de joueur, pas de position.
    player = fields[10] == "1", kclass = fields[11] or "",
    map = tonumber(fields[12]), x = tonumber(fields[13]), y = tonumber(fields[14]),
  }
end
ns.ParseDeathLine = parse

--- Nom de classe dans la langue du client (« Chaman ») d'après le jeton reçu, ou le texte reçu tel quel.
function ns.ClassLabel(class)
  local names = LOCALIZED_CLASS_NAMES_MALE
  return (type(names) == "table" and names[class]) or class or ""
end

--- Phrase d'un avis de décès, prête à afficher : le mort à la couleur de sa classe (jeton, ou nom affiché des
--- anciennes versions : alors sans couleur), le tueur à la sienne quand c'est un joueur (seuls eux en ont une).
--- « Prénom Nom » du mort (0.7.3 : l'annonce porte les deux, la phrase n'affichait que le prénom) ; le prénom
--- seul quand le personnage n'a pas de nom de famille ou que l'annonce vient d'une version d'avant la 0.6.12.
function ns.DeathName(info)
  local name = info.name or "?"
  if type(info.surname) == "string" and info.surname ~= "" then name = name .. " " .. info.surname end
  return name
end

function ns.DeathPhrase(info)
  local color = RAID_CLASS_COLORS and RAID_CLASS_COLORS[(info.class or ""):upper()]
  local name = ns.DeathName(info)
  local victim = { plain = name, shown = color and ("|c" .. (color.colorStr or "ffffffff") .. name .. "|r") or name }
  local killer = (info.killer and info.killer ~= "") and info.killer or ns.L.KILLER_UNKNOWN
  local roles = { personnage = victim, tueur = ns.Phrases.Role(killer, info.player and info.kclass or nil) }
  -- La graine : le mort et l'heure de sa mort, portés par le message. Tous les guildiens tirent la même phrase.
  local seed = info.guid and info.guid ~= "" and info.t and ("D:" .. info.guid .. ":" .. tostring(info.t)) or nil
  return ns.Phrases.Fill(ns.Phrases.Pick(ns.PHRASES, "{personnage} est hors jeu : {tueur}.", seed), roles)
end

local recentDeaths = {} -- guid du mort → { t = heure de réception, player = tueur joueur } de la dernière annonce gardée

--- Deux annonces pour une même mort (le client peut signaler la mort deux fois, et la seconde lecture du tueur
--- diffère alors de la première : une annonce PvE et une PvP) : vrai si celle-ci est à ignorer. Dans les
--- DEATH_DEDUPE s après une annonce du même personnage, seule une mort PvP qui suit une mort PvE passe (elle
--- remplace le popup et prend son point Wanted) ; la mort PvP l'emporte toujours.
local function duplicate(info)
  local t = ns.now() -- heure de réception : une seule horloge, la mienne
  for guid, seen in pairs(recentDeaths) do
    if math.abs(t - seen.t) >= ns.Data.DEATH_DEDUPE then recentDeaths[guid] = nil end
  end
  local seen = recentDeaths[info.guid]
  if seen and (seen.player or not info.player) then return true end
  recentDeaths[info.guid] = { t = t, player = info.player }
  return false
end

ns.RegisterCollector({
  name = "deaths",
  events = { CHAT_MSG_ADDON = true },
  onEvent = function(char, event, prefix, text, channel)
    if ns.plain(prefix) ~= ns.Data.ADDON_PREFIX or ns.plain(channel) ~= "GUILD" then return end
    text = ns.plain(text)
    if type(text) ~= "string" then return end
    local info = parse(text)
    if not info then return end
    if duplicate(info) then
      ns.Trace("mort de %s : doublon d'une annonce récente, ignoré", info.name)
      return
    end
    -- Tableau Wanted d'abord, popup ou non : un tueur joueur prend un point (doublon de ma propre mort reconnu).
    local wanted = nil
    if ns.Wanted then
      local ok, entry, added = pcall(ns.Wanted.RecordDeath, info)
      if not ok then
        ns.Store.LogError("wanted.record", entry)
      elseif entry then
        wanted = entry
        if added and ns.db.settings.wantedAlerts then ns.Safe("wanted.announce", ns.Wanted.Announce, entry, info) end
      end
    end
    -- Popup décoché : la mort est quand même notée dans l'historique de /mf.
    local quiet = not ns.db.settings.showDeaths
    if quiet then
      ns.Trace("mort de %s : popup désactivé dans les réglages", info.name)
    else
      ns.Trace("mort de %s reçue : popup%s", info.name, wanted and " (tueur recherché)" or "")
    end
    if ns.UI and ns.UI.ShowDeath then ns.UI.ShowDeath(info, ns.DeathPhrase(info), wanted, quiet) end
  end,
})
