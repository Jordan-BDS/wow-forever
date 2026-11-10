-- Équipement porté : identifiant d'objet et d'enchantement par emplacement, lus depuis le lien d'objet.
-- Chaque pièce porte aussi ce que le client sait de l'objet (nom, qualité, niveau d'objet, niveau requis, type
-- d'emplacement, classe et sous-classe) : la table d'objets du client n'a pas de fiche pour tous (objets à suffixe
-- aléatoire, certains objets Forever), et le site crée alors l'objet d'après le jeu plutôt que de laisser
-- l'emplacement vide.
local ADDON, ns = ...

local function number(value)
  value = ns.plain(value)
  return type(value) == "number" and value or nil
end

--- Ce que le client sait de l'objet : nom de base (sans suffixe) d'après son identifiant, sinon le nom du lien.
local function describe(piece, link)
  local info = (C_Item and C_Item.GetItemInfo) or GetItemInfo
  if type(info) == "function" then
    local ok, name, _, quality, ilvl, req, _, _, _, _, _, _, class, sub = pcall(info, piece.id)
    if ok then
      name = ns.plain(name)
      if type(name) == "string" and name ~= "" then piece.name = name end
      piece.q, piece.ilvl, piece.req, piece.cls, piece.sub = number(quality), number(ilvl), number(req), number(class), number(sub)
    end
  end
  if not piece.name then
    local name = link:match("|h%[(.-)%]|h")
    if name and name ~= "" then piece.name = name end
  end
  local invType = C_Item and C_Item.GetItemInventoryTypeByID
  if type(invType) == "function" then
    local ok, inv = pcall(invType, piece.id)
    if ok then piece.inv = number(inv) end
  end
end

local function scan(char)
  local gear = {}
  for slotId, key in pairs(ns.Data.SLOTS) do
    local link = ns.plain(GetInventoryItemLink("player", slotId))
    if type(link) == "string" then
      local itemId, enchantId = link:match("item:(%d+):(%d*)")
      if itemId then
        local piece = { id = tonumber(itemId) }
        if enchantId and enchantId ~= "" and enchantId ~= "0" then piece.ench = tonumber(enchantId) end
        describe(piece, link)
        gear[key] = piece
      end
    end
  end
  -- Aucun lien d'objet lu alors qu'on connaissait une tenue : lecture creuse (connexion, déconnexion), on garde la
  -- tenue connue plutôt que de l'effacer sur le site.
  if next(gear) == nil and next(char.gear or {}) ~= nil then return end
  char.gear = gear
  char.gear_at = ns.now()
end

ns.RegisterCollector({
  name = "gear",
  events = { PLAYER_EQUIPMENT_CHANGED = true },
  scanOn = { PLAYER_EQUIPMENT_CHANGED = true },
  scan = scan,
})
