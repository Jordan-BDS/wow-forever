-- Fin d'un scan complet de l'hôtel des ventes par un addon tiers (Auctionator, NaowhForever) : on propose de
-- recharger l'interface. Le jeu n'écrit les prix sur le disque qu'au /reload ou à la déconnexion, et c'est le
-- fichier écrit que le compagnon envoie au site de la guilde. Notre addon ne scanne rien lui-même.
--
-- Auctionator publie la fin d'un scan complet sur son bus d'événements (`Auctionator.FullScan.Events.ScanComplete`,
-- lu dans sa version 309). On ne passe pas par son API publique (`RegisterForDBUpdate`) : elle se déclenche aussi
-- à chaque recherche à la main. Si le bus ou l'événement manque (autre version), rien ne se passe.
--
-- NaowhForever n'annonce rien qu'on connaisse : on lit sa table de prix en mémoire tant que l'hôtel des ventes
-- est ouvert (`NaowhForeverDB.account.ahPrices[hôtel].time`, l'heure de fin du dernier scan, celle que le
-- compagnon lit dans le fichier). Quand elle avance, un scan vient de finir.
local ADDON, ns = ...
local L = ns.L

local M = {}
ns.AuctionScan = M

local NAOWH_TICK = 2 -- secondes entre deux lectures de la table de NaowhForever, hôtel des ventes ouvert

local open = false -- l'hôtel des ventes est ouvert
local ticking = false
local hooked = false -- abonné au bus d'Auctionator
local naowhSeen = nil -- heure du dernier scan NaowhForever déjà connu

--- Propose de recharger l'interface après un scan de `source` (le nom de l'addon de scan). Hors combat seulement :
--- la question attend la fin du combat.
function M.Suggest(source)
  if not (ns.db and ns.db.settings.scanReload) then return end
  if not (ns.UI and ns.UI.ShowDialog) then return end
  ns.UI.Dialogs.WFG_SCAN_RELOAD = ns.UI.Dialogs.WFG_SCAN_RELOAD or {
    button1 = L.SCAN_RELOAD_YES,
    button2 = L.RELOAD_LATER,
    button3 = L.RELOAD_NEVER,
    reload = true,
    OnAlt = function() ns.db.settings.scanReload = false end,
  }
  ns.Defer(function() ns.UI.ShowDialog("WFG_SCAN_RELOAD", string.format(L.SCAN_RELOAD_TEXT, source)) end)
end

--- L'heure de fin du scan NaowhForever le plus récent, tous hôtels confondus ; nil si l'addon n'est pas là.
local function naowhTime()
  local db = _G.NaowhForeverDB
  local houses = type(db) == "table" and type(db.account) == "table" and db.account.ahPrices or nil
  if type(houses) ~= "table" then return nil end
  local latest = 0
  for _, house in pairs(houses) do
    if type(house) == "table" and type(house.time) == "number" and house.time > latest then latest = house.time end
  end
  return latest
end

local function checkNaowh()
  local latest = naowhTime()
  if not latest then return end
  if naowhSeen and latest > naowhSeen then
    naowhSeen = latest
    M.Suggest("NaowhForever")
  else
    naowhSeen = naowhSeen or latest
  end
end

local function hookAuctionator()
  if hooked then return end
  local auctionator = _G.Auctionator
  if type(auctionator) ~= "table" then return end
  local bus, scan = auctionator.EventBus, auctionator.FullScan
  local event = type(scan) == "table" and type(scan.Events) == "table" and scan.Events.ScanComplete or nil
  if not (event and type(bus) == "table" and type(bus.Register) == "function") then return end
  hooked = true
  bus:Register(
    { ReceiveEvent = function() ns.Safe("auctionscan.auctionator", M.Suggest, "Auctionator") end },
    { event }
  )
end

local function onShow()
  open = true
  ns.Safe("auctionscan.hook", hookAuctionator)
  -- La table telle qu'elle est à l'ouverture : seul un scan fini après compte.
  naowhSeen = naowhTime() or naowhSeen
  if not ticking and C_Timer and C_Timer.NewTicker then
    -- Un seul ticker pour la session : il ne lit rien tant que l'hôtel des ventes est fermé.
    ticking = true
    C_Timer.NewTicker(NAOWH_TICK, function()
      if open then ns.Safe("auctionscan.naowh", checkNaowh) end
    end)
  end
end

local function onClosed()
  if not open then return end
  ns.Safe("auctionscan.naowh", checkNaowh) -- un scan fini entre la dernière lecture et la fermeture
  open = false
end

local frame = CreateFrame("Frame")
frame:RegisterEvent("PLAYER_LOGIN")
frame:RegisterEvent("AUCTION_HOUSE_SHOW")
frame:RegisterEvent("AUCTION_HOUSE_CLOSED")
frame:SetScript("OnEvent", function(_, event)
  if event == "AUCTION_HOUSE_SHOW" then
    ns.Safe("auctionscan.show", onShow)
  elseif event == "AUCTION_HOUSE_CLOSED" then
    ns.Safe("auctionscan.closed", onClosed)
  else
    ns.Safe("auctionscan.hook", hookAuctionator)
  end
end)
