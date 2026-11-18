-- Achats et ventes à l'hôtel des ventes, notés pour la courbe de prix du site (page /hv) : niveau compte
-- (`db.trades`), envoyés avec l'export. Notre addon n'achète ni ne vend rien : il écoute.
--
-- Achats : tout achat passe par `C_AuctionHouse.PlaceBid` (un objet) ou `StartCommoditiesPurchase` puis
-- `ConfirmCommoditiesPurchase` (une marchandise), quelle que soit l'interface (celle du jeu, Auctionator,
-- NaowhForever). On accroche ces fonctions pour savoir quoi et à quel prix, et on note l'achat quand le jeu le
-- confirme (`AUCTION_HOUSE_PURCHASE_COMPLETED`, `COMMODITY_PURCHASE_SUCCEEDED`). Une enchère posée sous le prix
-- d'achat immédiat n'est pas un achat : si elle l'emporte, sa facture arrive par le courrier.
--
-- Ventes : la facture du courrier de l'hôtel (`GetInboxInvoiceInfo`, type « seller »), lue à chaque mise à jour
-- de la boîte. C'est la seule trace d'une vente faite pendant qu'on était ailleurs ; elle donne le prix, le dépôt
-- et la commission. Elle ne donne que le nom de l'objet : l'identifiant vient de nos mises en vente (`posts`,
-- notées en accrochant `PostItem` et `PostCommodity`), sinon le site le retrouve par le nom. Un courrier n'a pas
-- d'identifiant : une facture déjà notée est reconnue à son type, son objet, ses montants et son heure d'arrivée
-- (tirée des jours restants du courrier), à `TRADE_MAIL_SLACK` près.
--
-- Une entrée : n (numéro, par installation), t, k (« buy » ou « sell »), src (« bid », « commodity », « mail »),
-- item, name, qty, price (à l'unité), total, fee (commission), deposit, char, realm, faction. Montants en cuivre.
-- Lecture du courrier pas essayée en jeu à l'écriture (0.7.18) : /mf ventes montre ce que le jeu répond.
local ADDON, ns = ...

local Trades = {}
ns.Trades = Trades

local hooked = false
local pendingBids = {} -- enchère → { t, total, item, name, qty, buyout } : PlaceBid appelé, réponse du jeu attendue
local commodity = nil -- { item, qty, total, confirmed } : l'achat de marchandise en cours
local lastKey = nil -- la clé d'objet des derniers résultats de recherche reçus
local mailRead = nil -- { t, mails, invoices, new } : la dernière lecture du courrier, pour /mf ventes

local function store()
  local db = ns.db
  if not db then return nil end
  if type(db.trades) ~= "table" then db.trades = {} end
  local s = db.trades
  s.list = s.list or {}
  s.posts = s.posts or {}
  s.seq = s.seq or 0
  return s
end

local function number(value)
  value = tonumber(ns.plain(value))
  return value and value >= 0 and value or nil
end

--- Identifiant et nom d'un lien d'objet.
local function linkItem(link)
  link = ns.plain(link)
  if type(link) ~= "string" then return nil, nil end
  return tonumber(link:match("item:(%d+)")), link:match("%[(.-)%]")
end

--- Le nom d'un objet. Ce client range `GetItemInfo` dans `C_Item` ; l'ancienne fonction globale n'y est plus.
local function itemName(item)
  local info = (type(C_Item) == "table" and C_Item.GetItemInfo) or GetItemInfo
  if not item or type(info) ~= "function" then return nil end
  local ok, name = pcall(info, item)
  name = ok and ns.plain(name) or nil
  return type(name) == "string" and name or nil
end

local function add(entry)
  local s = store()
  if not s then return nil end
  s.seq = s.seq + 1
  entry.n = s.seq
  entry.char = ns.char and ns.char.guid or nil
  entry.faction = ns.char and ns.char.faction or nil
  entry.realm = type(GetRealmName) == "function" and ns.plain(GetRealmName()) or nil
  if entry.qty and entry.qty > 0 and entry.total then entry.price = math.floor(entry.total / entry.qty) end
  s.list[#s.list + 1] = entry
  local oldest = ns.now() - ns.Data.TRADES_DAYS * 86400
  while #s.list > ns.Data.TRADES_MAX or (s.list[1] and s.list[1] ~= entry and (s.list[1].t or 0) < oldest) do
    table.remove(s.list, 1)
  end
  ns.Trace("hôtel des ventes : %s noté (%s, %s × %s, total %s)", entry.k == "buy" and "achat" or "vente",
    tostring(entry.name or entry.item), tostring(entry.qty), tostring(entry.price), tostring(entry.total))
  return entry
end

-- Achat d'un objet ---------------------------------------------------------------------------------------

--- Ce que le jeu sait d'une enchère : par son numéro, sinon dans les derniers résultats de recherche.
local function auctionInfo(auctionID)
  local ah = C_AuctionHouse
  local info
  if type(ah.GetAuctionInfoByID) == "function" then
    local ok, got = pcall(ah.GetAuctionInfoByID, auctionID)
    if ok and type(got) == "table" then info = got end
  end
  if not info and lastKey and type(ah.GetNumItemSearchResults) == "function"
    and type(ah.GetItemSearchResultInfo) == "function" then
    local ok, count = pcall(ah.GetNumItemSearchResults, lastKey)
    for i = 1, ok and tonumber(count) or 0 do
      local fine, row = pcall(ah.GetItemSearchResultInfo, lastKey, i)
      if fine and type(row) == "table" and row.auctionID == auctionID then
        info = row
        break
      end
    end
  end
  if not info then return nil end
  local item, name = linkItem(info.itemLink)
  item = item or (type(info.itemKey) == "table" and tonumber(info.itemKey.itemID)) or nil
  return { item = item, name = name or itemName(item), qty = number(info.quantity) or 1, buyout = number(info.buyoutAmount) }
end

local function onPlaceBid(auctionID, amount)
  amount = number(amount)
  if auctionID == nil or not amount or amount <= 0 then return end
  local t = ns.now()
  for id, pending in pairs(pendingBids) do
    if t - pending.t > ns.Data.TRADE_BID_WINDOW then pendingBids[id] = nil end
  end
  local pending = auctionInfo(auctionID) or {}
  pending.t, pending.total = t, amount
  pendingBids[auctionID] = pending
end

local function onPurchaseCompleted(auctionID)
  local pending = auctionID ~= nil and pendingBids[auctionID] or nil
  if not pending then return end
  pendingBids[auctionID] = nil
  if ns.now() - pending.t > ns.Data.TRADE_BID_WINDOW then return end
  -- Sous le prix d'achat immédiat : une enchère posée, pas encore un achat.
  if pending.buyout and pending.buyout > 0 and pending.total < pending.buyout then return end
  add({ t = ns.now(), k = "buy", src = "bid", item = pending.item, name = pending.name, qty = pending.qty, total = pending.total })
end

-- Achat d'une marchandise --------------------------------------------------------------------------------

local function onStartCommodity(item, quantity)
  item, quantity = number(item), number(quantity)
  commodity = item and quantity and quantity > 0 and { item = item, qty = quantity } or nil
end

--- Le prix que le jeu annonce pour la quantité demandée : c'est celui qui sera payé.
local function onCommodityPrice(_, total)
  if commodity and not commodity.confirmed then commodity.total = number(total) end
end

local function onConfirmCommodity(item, quantity)
  item, quantity = number(item), number(quantity)
  if not (commodity and commodity.item == item and commodity.total) then
    commodity = nil
    return
  end
  commodity.confirmed = true
  if quantity and quantity > 0 and quantity ~= commodity.qty then
    -- Quantité changée entre le prix annoncé et la confirmation : le total ne vaut plus.
    commodity = nil
  end
end

local function onCommoditySucceeded()
  local bought = commodity
  commodity = nil
  if not (bought and bought.confirmed and bought.total and bought.total > 0) then return end
  add({ t = ns.now(), k = "buy", src = "commodity", item = bought.item, name = itemName(bought.item), qty = bought.qty, total = bought.total })
end

-- Mises en vente : le nom d'un objet → son identifiant et son prix, pour lire les factures ----------------

local function notePost(location, price)
  price = number(price)
  local s = store()
  if not s or not price or price <= 0 or type(C_Item) ~= "table" or type(C_Item.GetItemID) ~= "function" then return end
  local ok, item = pcall(C_Item.GetItemID, location)
  item = ok and number(item) or nil
  if not item then return end
  local name
  if type(C_Item.GetItemName) == "function" then
    local fine, got = pcall(C_Item.GetItemName, location)
    name = fine and ns.plain(got) or nil
  end
  if type(name) ~= "string" or name == "" then name = itemName(item) end
  if not name then return end
  local t = ns.now()
  s.posts[name] = { item = item, price = price, t = t }
  local oldest = t - ns.Data.TRADES_DAYS * 86400
  for other, post in pairs(s.posts) do
    if (post.t or 0) < oldest then s.posts[other] = nil end
  end
end

local function onPostItem(location, _, _, bid, buyout)
  notePost(location, number(buyout) and number(buyout) > 0 and buyout or bid)
end

local function onPostCommodity(location, _, _, unitPrice)
  notePost(location, unitPrice)
end

local HOOKS = {
  PlaceBid = onPlaceBid,
  StartCommoditiesPurchase = onStartCommodity,
  ConfirmCommoditiesPurchase = onConfirmCommodity,
  PostItem = onPostItem,
  PostCommodity = onPostCommodity,
}

local function hook()
  if hooked or type(C_AuctionHouse) ~= "table" or type(hooksecurefunc) ~= "function" then return end
  hooked = true
  for name, fn in pairs(HOOKS) do
    if type(C_AuctionHouse[name]) == "function" then
      hooksecurefunc(C_AuctionHouse, name, function(...) ns.Safe("trades." .. name, fn, ...) end)
    end
  end
end

-- Courrier -----------------------------------------------------------------------------------------------

--- La facture du courrier `index`, ou nil : { k, name, total, fee, deposit, qty, item, t, won }.
local function readInvoice(index)
  local ok, kind, name, _, bid, buyout, deposit, cut, _, _, _, count = pcall(GetInboxInvoiceInfo, index)
  kind, name = ns.plain(kind), ns.plain(name)
  if not ok or (kind ~= "seller" and kind ~= "buyer") or type(name) ~= "string" or name == "" then return nil end
  bid, buyout = number(bid), number(buyout) or 0
  if not bid or bid <= 0 then return nil end
  local invoice = { k = kind == "seller" and "sell" or "buy", name = name, total = bid, t = ns.now() }
  invoice.won = kind == "buyer" and bid ~= buyout -- emportée à l'enchère, pas achetée tout de suite
  count = number(count)
  if count and count > 0 then invoice.qty = count end
  local subject, daysLeft
  if type(GetInboxHeaderInfo) == "function" then
    local fine, _, _, _, title, _, _, days = pcall(GetInboxHeaderInfo, index)
    if fine then subject, daysLeft = ns.plain(title), number(days) end
  end
  if daysLeft then
    local arrived = math.floor(ns.now() - (ns.Data.AH_MAIL_DAYS - daysLeft) * 86400 + 0.5)
    invoice.t = math.min(ns.now(), arrived)
  end
  if not invoice.qty and type(subject) == "string" then
    local stack = tonumber(subject:match("%((%d+)%)%s*$"))
    if stack and stack > 0 then invoice.qty = stack end
  end
  if invoice.k == "sell" then
    invoice.fee, invoice.deposit = number(cut) or 0, number(deposit) or 0
    local post = store().posts[name]
    if post then
      invoice.item = post.item
      -- Une marchandise se vend par morceaux : la quantité est le prix encaissé divisé par le prix demandé.
      if not invoice.qty and post.price > 0 and bid % post.price == 0 then invoice.qty = bid / post.price end
    end
  else
    -- L'objet acheté est joint au courrier.
    if type(GetInboxItemLink) == "function" then
      local fine, link = pcall(GetInboxItemLink, index, 1)
      if fine then invoice.item = linkItem(link) end
    end
    if not invoice.qty and type(GetInboxItem) == "function" then
      local fine, _, _, _, stack = pcall(GetInboxItem, index, 1)
      stack = fine and number(stack) or nil
      if stack and stack > 0 then invoice.qty = stack end
    end
  end
  local instant = (type(C_Item) == "table" and C_Item.GetItemInfoInstant) or GetItemInfoInstant
  if not invoice.item and type(instant) == "function" then
    local fine, item = pcall(instant, name)
    invoice.item = fine and number(item) or nil
  end
  return invoice
end

local function sameInvoice(entry, invoice)
  return entry.src == "mail" and entry.k == invoice.k and entry.name == invoice.name and entry.total == invoice.total
    and (entry.fee or 0) == (invoice.fee or 0) and math.abs((entry.t or 0) - invoice.t) <= ns.Data.TRADE_MAIL_SLACK
end

--- Lit les factures de la boîte : note celles qu'on n'a pas encore. Deux factures identiques arrivées ensemble
--- (deux enchères pareilles au même acheteur) sont deux ventes : chaque entrée ne répond qu'à un courrier.
function Trades.ScanMail()
  local s = store()
  if not s or type(GetInboxNumItems) ~= "function" or type(GetInboxInvoiceInfo) ~= "function" then return end
  local ok, mails = pcall(GetInboxNumItems)
  mails = ok and number(mails) or 0
  local claimed, invoices, new = {}, 0, 0
  for index = 1, mails do
    local invoice = readInvoice(index)
    if invoice then
      invoices = invoices + 1
      local known
      for _, entry in ipairs(s.list) do
        if not claimed[entry] and sameInvoice(entry, invoice) then
          known = entry
          break
        end
      end
      if known then
        claimed[known] = true
      elseif invoice.k == "sell" or invoice.won then
        local entry = add({
          t = invoice.t, k = invoice.k, src = "mail", item = invoice.item, name = invoice.name, qty = invoice.qty,
          total = invoice.total, fee = invoice.fee, deposit = invoice.deposit,
        })
        if entry then claimed[entry] = true end
        new = new + 1
      else
        -- Achat immédiat : déjà noté à l'achat. S'il l'a été sans que le jeu dise quel objet, le courrier le dit.
        for _, entry in ipairs(s.list) do
          if entry.src == "bid" and not entry.item and entry.total == invoice.total
            and invoice.t - (entry.t or 0) >= -ns.Data.TRADE_MAIL_SLACK
            and invoice.t - (entry.t or 0) <= ns.Data.TRADE_FILL_WINDOW then
            entry.item, entry.name, entry.qty = invoice.item, invoice.name, invoice.qty or entry.qty
            if entry.qty and entry.qty > 0 then entry.price = math.floor(entry.total / entry.qty) end
            break
          end
        end
      end
    end
  end
  mailRead = { t = ns.now(), mails = mails, invoices = invoices, new = new }
end

-- Export et diagnostic -----------------------------------------------------------------------------------

--- Un achat noté avant que le jeu connaisse le nom de l'objet le reçoit ici, à l'export et au rapport.
local function fillNames(list)
  for _, entry in ipairs(list) do
    if entry.item and not entry.name then entry.name = itemName(entry.item) end
  end
end

--- Les transactions notées, pour le site ; nil s'il n'y en a pas.
function Trades.Export()
  local s = ns.db and ns.db.trades
  if type(s) ~= "table" or type(s.list) ~= "table" or #s.list == 0 then return nil end
  fillNames(s.list)
  local out = ns.Json.array()
  for _, entry in ipairs(s.list) do out[#out + 1] = entry end
  return out
end

local function money(copper)
  if not copper then return "?" end
  copper = math.floor(copper)
  local parts = {}
  if copper >= 10000 then parts[#parts + 1] = math.floor(copper / 10000) .. " po" end
  if math.floor(copper / 100) % 100 > 0 then parts[#parts + 1] = (math.floor(copper / 100) % 100) .. " pa" end
  if copper % 100 > 0 or #parts == 0 then parts[#parts + 1] = (copper % 100) .. " pc" end
  return table.concat(parts, " ")
end

local SOURCES = { bid = "achat immédiat", commodity = "marchandise", mail = "courrier" }

--- Les lignes de /mf ventes : ce que ce client offre, ce qui est noté, et ce que le jeu répond pour les
--- premiers courriers de la boîte si elle est ouverte.
function Trades.ReportLines()
  local lines = {}
  local have, miss = {}, {}
  for _, name in ipairs({ "PlaceBid", "GetAuctionInfoByID", "StartCommoditiesPurchase", "ConfirmCommoditiesPurchase", "PostItem", "PostCommodity" }) do
    local present = type(C_AuctionHouse) == "table" and type(C_AuctionHouse[name]) == "function"
    local list = present and have or miss
    list[#list + 1] = name
  end
  for _, name in ipairs({ "GetInboxInvoiceInfo", "GetInboxHeaderInfo", "GetInboxItemLink" }) do
    local list = type(_G[name]) == "function" and have or miss
    list[#list + 1] = name
  end
  lines[#lines + 1] = string.format("ventes · présent : %s · absent : %s · fonctions accrochées : %s",
    #have > 0 and table.concat(have, ", ") or "rien", #miss > 0 and table.concat(miss, ", ") or "rien", hooked and "oui" or "non")
  local s = store()
  local list = s and s.list or {}
  local buys = 0
  fillNames(list)
  for _, entry in ipairs(list) do
    if entry.k == "buy" then buys = buys + 1 end
  end
  lines[#lines + 1] = string.format("ventes · %d achats et %d ventes notés · courrier : %s", buys, #list - buys,
    mailRead and string.format("lu à %s, %d courriers, %d factures, %d nouvelles", date("%H:%M", mailRead.t), mailRead.mails, mailRead.invoices, mailRead.new)
      or "pas lu cette session (ouvre une boîte aux lettres)")
  for i = math.max(1, #list - ns.Data.TRADE_REPORT_LINES + 1), #list do
    local entry = list[i]
    lines[#lines + 1] = string.format("%s · %s · %s%s · %s pièce · total %s%s · %s",
      date("%d/%m %H:%M", entry.t or 0), entry.k == "buy" and "achat" or "vente",
      tostring(entry.name or "objet inconnu"), entry.item and (" (" .. entry.item .. ")") or " (sans identifiant)",
      entry.qty and (entry.qty .. " × " .. money(entry.price)) or "quantité inconnue",
      money(entry.total), entry.fee and (" · commission " .. money(entry.fee) .. ", dépôt " .. money(entry.deposit)) or "",
      SOURCES[entry.src] or tostring(entry.src))
  end
  -- La réponse brute du jeu, pour vérifier la lecture des factures sur ce client.
  if type(GetInboxNumItems) == "function" and type(GetInboxInvoiceInfo) == "function" then
    local ok, mails = pcall(GetInboxNumItems)
    local shown = 0
    for index = 1, ok and number(mails) or 0 do
      local got = { pcall(GetInboxInvoiceInfo, index) }
      if got[1] and got[2] ~= nil and shown < ns.Data.TRADE_REPORT_MAILS then
        shown = shown + 1
        local fields = {}
        for i = 2, #got do fields[#fields + 1] = tostring(ns.plain(got[i])) end
        local days = type(GetInboxHeaderInfo) == "function" and select(8, pcall(GetInboxHeaderInfo, index)) or nil
        lines[#lines + 1] = string.format("courrier %d · %s · jours restants : %s", index, table.concat(fields, " | "), tostring(ns.plain(days)))
      end
    end
  end
  return lines
end

--- /mf ventes : dans le chat, et noté avec les erreurs pour partir au site (page « Tests en jeu »).
function Trades.Report()
  local lines = Trades.ReportLines()
  for _, line in ipairs(lines) do ns.Print("%s", line) end
  ns.Store.LogError("ventes", table.concat(lines, " | "))
end

ns.RegisterCollector({
  name = "trades",
  events = {
    AUCTION_HOUSE_SHOW = true, AUCTION_HOUSE_PURCHASE_COMPLETED = true, ITEM_SEARCH_RESULTS_UPDATED = true,
    COMMODITY_PRICE_UPDATED = true, COMMODITY_PURCHASE_SUCCEEDED = true, COMMODITY_PURCHASE_FAILED = true,
    MAIL_SHOW = true, MAIL_INBOX_UPDATE = true,
  },
  onLogin = function() hook() end,
  onEvent = function(_, event, first, second)
    if event == "AUCTION_HOUSE_SHOW" then
      hook()
    elseif event == "AUCTION_HOUSE_PURCHASE_COMPLETED" then
      onPurchaseCompleted(ns.plain(first))
    elseif event == "ITEM_SEARCH_RESULTS_UPDATED" then
      if type(first) == "table" then lastKey = first end
    elseif event == "COMMODITY_PRICE_UPDATED" then
      onCommodityPrice(first, second)
    elseif event == "COMMODITY_PURCHASE_SUCCEEDED" then
      onCommoditySucceeded()
    elseif event == "COMMODITY_PURCHASE_FAILED" then
      commodity = nil
    else
      ns.Debounce("trades:mail", ns.Data.TRADE_MAIL_DELAY, function() ns.Safe("trades.mail", Trades.ScanMail) end)
    end
  end,
})
