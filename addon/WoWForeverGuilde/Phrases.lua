-- Gabarits des annonces de mort, tirés au hasard. Variables : {personnage}, {tueur}, {zone}, {niveau}, {classe}.
-- Source : le fichier `templates-morts` à la racine du dépôt (une ligne = une phrase) ; le recopier ici après modification.
local ADDON, ns = ...

ns.PHRASES = {
  "{personnage} s'est fait saucer par {tueur} dans {zone} et est mort comme une merde.",
  "{personnage}, {classe} niveau {niveau}, vient de perdre un 1v1 contre {tueur} dans {zone}. Respect.",
  "Avis de décès : {personnage} a rencontré {tueur} dans {zone}. Le cimetière présente ses condoléances.",
  "{tueur} 1 – {personnage} 0. Match joué dans {zone}, revanche au cimetière.",
  "{personnage} a tenté un truc dans {zone}. {tueur} a dit non.",
  "Pensée pour {personnage}, mort au combat (ou presque) face à {tueur} dans {zone}.",
  "Spoiler : {personnage} ne survivra pas à {tueur} dans {zone}. Ah bah non, c'est déjà fait.",
  "Un {classe} niveau {niveau} qui meurt contre {tueur} dans {zone}, ça s'appelle {personnage}.",
  "{personnage} vient de tester la résurrection grâce à {tueur}. Verdict : ça marche.",
  "Le corps de {personnage} refroidit dans {zone}. Merci {tueur} pour ce moment.",
  "{personnage} voulait prouver que {tueur} c'était facile. {zone} s'en souviendra.",
  "Nouvelle mort pour {personnage}, encore à cause de {tueur}. Ça devient une habitude.",
  "{personnage} ({classe} {niveau}) a confondu courage et bêtise face à {tueur} dans {zone}.",
  "Breaking news : {personnage} est tombé face à {tueur} dans {zone}. Les heals n'y sont pour rien, paraît-il.",
  "{tueur} remercie {personnage} pour sa participation. Décès validé dans {zone}.",
  "Dix secondes de silence pour {personnage}, vaincu par {tueur}. Bon, cinq, on a du farm.",
  "{personnage} est parti voir l'Esprit guérisseur de {zone}, sur recommandation de {tueur}.",
  "Si {personnage} demande, {tueur} a cheaté. Dans {zone}. Évidemment.",
  "{tueur} fait savoir que {personnage} est en fantôme dans {zone}. Venez le rez si ça vous chante.",
  "Niveau {niveau} et toujours pas à l'abri de {tueur} : {personnage} vient de le prouver dans {zone}.",
}
