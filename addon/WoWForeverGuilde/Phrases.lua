-- Gabarits des popups, tirés au hasard, et leur remplissage.
--
-- Écrire un gabarit :
--   {personnage}, {tueur}…       le nom, tel quel ;
--   {de_tueur}, {a_tueur}…       le nom précédé de « de » ou « à », contracté ou élidé comme il faut : « du feu »,
--                                « d'une chute », « d'Arthas », « de Hogger », « au feu », « à la lave » ;
--   {a|ont}, {rappelle|rappellent}  singulier ou pluriel selon le nombre de tueurs (kill à plusieurs).
-- Le lieu, le niveau, la classe et la prime ne sont pas dans les phrases : le pied du popup les donne.
-- Le sexe des personnages n'est pas connu : pas de participe ni d'adjectif accordé avec eux (« mort », « tombé »,
-- « abattu », « plus fort que lui »). Le tueur d'un avis de décès est un joueur, une créature (« Sanglier des
-- Tarides », sans article), une cause (« une chute », « le feu ») ou « quelque chose » : la phrase doit tenir
-- avec les quatre.
local ADDON, ns = ...

-- Avis de décès. Source : le fichier `templates-morts` à la racine du dépôt (une ligne = une phrase) ; le recopier
-- ici après modification.
ns.PHRASES = {
  "{personnage} s'est fait saucer par {tueur} et a fini comme une merde.",
  "{personnage} vient de perdre un 1v1 contre {tueur}. Respect.",
  "{personnage} a rencontré {tueur}. Le cimetière présente ses condoléances.",
  "{tueur} 1 – {personnage} 0. Revanche au cimetière.",
  "{personnage} a tenté un truc. {tueur} a dit non.",
  "Pensée pour {personnage}, qui n'a pas fait le poids face {a_tueur}.",
  "Spoiler : {personnage} ne survivra pas {a_tueur}. Ah bah non, c'est déjà fait.",
  "{personnage} vient de tester la résurrection grâce {a_tueur}. Verdict : ça marche.",
  "Le corps {de_personnage} refroidit déjà. Merci {a_tueur} pour ce moment.",
  "{personnage} voulait prouver que {tueur}, c'était facile. Raté.",
  "{personnage} a confondu courage et bêtise face {a_tueur}.",
  "Breaking news : {tueur} a eu raison {de_personnage}. Les heals n'y sont pour rien, paraît-il.",
  "Décès validé pour {personnage}. {tueur} n'a même pas forcé.",
  "Dix secondes de silence pour {personnage}, qui n'a rien pu faire contre {tueur}. Bon, cinq, on a du farm.",
  "{personnage} file voir l'Esprit guérisseur, sur recommandation {de_tueur}.",
  "Si {personnage} demande, {tueur} a cheaté. Évidemment.",
  "{personnage} erre en fantôme à cause {de_tueur}. Venez rez si ça vous chante.",
  "Toujours pas à l'abri {de_tueur} : {personnage} vient de le prouver.",
  "{tueur} a encore frappé. Cette fois, c'est tombé sur {personnage}.",
  "{personnage} pensait gérer {tueur}. {personnage} ne gérait pas.",
}

-- Victoires honorables : un joueur adverse ({personnage}, ou « un adversaire » quand le jeu ne le nomme pas)
-- abattu par un ou plusieurs membres ({tueur} : « Thrall », « Thrall et Jaina »).
ns.KILL_PHRASES = {
  "{tueur} {a|ont} envoyé {personnage} au cimetière. Bon voyage.",
  "{tueur} 1 – {personnage} 0. Suivant.",
  "{personnage} a croisé {tueur}. Mauvaise idée.",
  "{tueur} {rappelle|rappellent} {a_personnage} qui tient la zone.",
  "{personnage} voulait du PvP. {tueur} {a|ont} livré.",
  "Victoire {de_tueur} sur {personnage}. Propre, net, sans bavure.",
  "{tueur} {vient|viennent} de plier {personnage}. Les honneurs sont pour la maison.",
  "Si {personnage} demande, {tueur} {a|ont} cheaté. Évidemment.",
  "{personnage} pensait passer tranquille. {tueur} {était|étaient} dans le coin.",
  "{tueur} {offre|offrent} {a_personnage} un aller simple chez l'Esprit guérisseur.",
  "Un point d'honneur de plus pour {tueur}, un trajet en fantôme pour {personnage}.",
  "{tueur} {n'a|n'ont} laissé aucune chance {a_personnage}.",
}

-- Primes encaissées : un recherché ({ennemi}) abattu par un membre ({chasseur}).
ns.BOUNTY_PHRASES = {
  "{chasseur} vient d'encaisser la prime sur {ennemi}. Justice est faite.",
  "{ennemi} a enfin trouvé plus fort : {chasseur}.",
  "Avis à la population : {chasseur} a fait tomber {ennemi}. Sa tête était mise à prix.",
  "{chasseur} 1 – {ennemi} 0. La prime est encaissée.",
  "Wanted, mort ou vif : pour {ennemi}, ce sera mort. Merci {chasseur}.",
  "{ennemi} a croisé {chasseur}. Le cimetière, c'est par là.",
  "Tête mise à prix, tête tombée : {chasseur} règle le compte {de_ennemi}.",
  "{chasseur} rappelle {a_ennemi} que la guilde a de la mémoire.",
  "{ennemi} voulait une revanche. {chasseur} a livré.",
  "Le mandat d'arrêt contre {ennemi} a été exécuté par {chasseur}. Affaire classée.",
}

ns.Phrases = {}
local Phrases = ns.Phrases

--- « 1 point », « 3 points » : l'unité des primes, partout la même.
function ns.Points(n)
  n = n or 0
  return string.format(n > 1 and ns.L.POINTS_PLURAL or ns.L.POINTS_SINGULAR, n)
end

local VOWELS = {
  "a", "e", "i", "o", "u", "A", "E", "I", "O", "U",
  "à", "â", "é", "è", "ê", "î", "ô", "û", "À", "Â", "É", "È", "Ê", "Î", "Ô", "Û",
}

local function startsWithVowel(text)
  for _, vowel in ipairs(VOWELS) do
    if text:sub(1, #vowel) == vowel then return true end
  end
  return false
end

-- L'article défini en tête (« le feu ») ne se contracte que sur un texte sans couleur : `shown` est alors `plain`.
local function article(plain, shown)
  if shown ~= plain then return nil end
  local lower = plain:sub(1, 4):lower()
  if lower:sub(1, 3) == "le " then return "le", plain:sub(4) end
  if lower == "les " then return "les", plain:sub(5) end
  return nil
end

--- « de » + nom : « du feu », « de la lave », « de l'épuisement », « d'une chute », « d'Arthas », « de Hogger ».
function Phrases.De(plain, shown)
  shown = shown or plain
  local which, rest = article(plain, shown)
  if which == "le" then return "du " .. rest end
  if which == "les" then return "des " .. rest end
  if startsWithVowel(plain) then return "d'" .. shown end
  return "de " .. shown
end

--- « à » + nom : « au feu », « à la lave », « à une chute », « à Hogger ».
function Phrases.A(plain, shown)
  shown = shown or plain
  local which, rest = article(plain, shown)
  if which == "le" then return "au " .. rest end
  if which == "les" then return "aux " .. rest end
  return "à " .. shown
end

-- Majuscule en tête de phrase, y compris sous un code de couleur : une cause (« une chute ») ou « un adversaire »
-- peut ouvrir la phrase, ou en ouvrir une autre après un point.
local COLOR = "|c%x%x%x%x%x%x%x%x"
local function sentenceCase(text)
  text = text:gsub("^(" .. COLOR .. ")(%l)", function(color, letter) return color .. letter:upper() end)
  text = text:gsub("^%l", string.upper)
  text = text:gsub("([%.!?] )(" .. COLOR .. ")(%l)", function(stop, color, letter) return stop .. color .. letter:upper() end)
  text = text:gsub("([%.!?] )(%l)", function(stop, letter) return stop .. letter:upper() end)
  return text
end

--- Un rôle d'une phrase : le nom nu (pour l'élision) et le nom affiché (à la couleur de sa classe s'il en a une).
function Phrases.Role(name, class)
  name = name or ""
  local known = type(class) == "string" and class ~= ""
  return { plain = name, shown = known and ns.ClassColored(name, class) or name }
end

--- Remplit un gabarit. `roles` : { tueur = rôle, … }, un rôle étant un texte ou { plain, shown } ; `plural` : les
--- alternatives {singulier|pluriel} prennent la seconde forme. Une variable inconnue reste telle quelle.
function Phrases.Fill(template, roles, plural)
  local text = template:gsub("{([^{}]+)}", function(key)
    local singular, several = key:match("^([^|]*)|([^|]*)$")
    if singular then return plural and several or singular end
    local form, name = key:match("^(de)_(.+)$")
    if not form then form, name = key:match("^(a)_(.+)$") end
    local role = roles[name or key]
    if role == nil then return "{" .. key .. "}" end
    if type(role) ~= "table" then role = { plain = tostring(role), shown = tostring(role) } end
    if form == "de" then return Phrases.De(role.plain, role.shown) end
    if form == "a" then return Phrases.A(role.plain, role.shown) end
    return role.shown
  end)
  return sentenceCase(text)
end

--- Un gabarit du lot ; `fallback` si le lot est vide. Avec une graine (`seed`, un texte tiré de ce que tous les
--- guildiens reçoivent : qui, quand), le choix est le même chez tous ceux qui ont le même lot : pour un même
--- événement, tout le monde lit la même phrase. Sans graine, au hasard.
function Phrases.Pick(phrases, fallback, seed)
  if type(phrases) ~= "table" or #phrases == 0 then return fallback end
  if type(seed) ~= "string" or seed == "" then return phrases[math.random(1, #phrases)] end
  local hash = 0
  for i = 1, #seed do hash = (hash * 31 + seed:byte(i)) % 2147483647 end
  return phrases[hash % #phrases + 1]
end
