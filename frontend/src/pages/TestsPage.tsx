import clsx from "clsx";
import { useEffect, useMemo, useState } from "react";
import { Navigate } from "react-router";
import { useAddonErrors, type AddonError } from "@/api/sync";
import { useCurrentUser } from "@/auth/useCurrentUser";
import { Card, PageTitle, Spinner } from "@/components/ui";
import { formatDateTime } from "@/lib/game";

/**
 * Tests en jeu (GM seulement) : la fiche de contrôle des collecteurs de l'addon sur le vrai client Forever,
 * avec les commandes à copier et les résultats attendus. Les cases cochées restent dans le navigateur.
 */

type Severity = "block" | "later" | undefined;

type Step = {
  id: string;
  title: string;
  severity?: Severity;
  severityLabel?: string;
  commands?: string[];
  /** Ce qu'on doit voir. */
  expected: string;
  /** Quoi faire si ça rate. */
  otherwise?: string;
};

type Section = { title: string; when?: string; steps: Step[] };

const SECTIONS: Section[] = [
  {
    title: "Avant de se connecter",
    when: "Depuis l'écran de connexion, dans le chat une fois en jeu, ou dans la liste des addons.",
    steps: [
      {
        id: "errors",
        title: "Afficher les erreurs Lua",
        severity: "block",
        severityLabel: "à faire en premier",
        commands: ["/console scriptErrors 1"],
        expected: "Sans ça, une erreur de l'addon passe inaperçue.",
      },
      {
        id: "build",
        title: "Version d'interface du client",
        severity: "block",
        severityLabel: "bloquant pour l'import",
        commands: ["/dump GetBuildInfo()"],
        expected: "« 1.60.1 », un build 707xx, une date, puis 16001.",
        otherwise:
          "Si le quatrième nombre n'est pas 16001, le site refuse les envois : Guilde › Paramètres › Versions d'interface acceptées, mettre ce nombre.",
      },
      {
        id: "addonlist",
        title: "Liste des addons",
        expected: "« Manuel Feralas » présent, coché, avec le portrait de Samwise devant.",
        otherwise: "Icône par défaut : le client ignore la ligne IconTexture du toc, sans gravité.",
      },
    ],
  },
  {
    title: "À la connexion",
    steps: [
      {
        id: "welcome",
        title: "Message de bienvenue et fenêtre",
        commands: ["/mf"],
        expected:
          "Chat : « [MF] Bienvenue, Nom. Compteurs depuis le 04/11/2026. » La fenêtre s'ouvre, titre Manuel Feralas avec le portrait, sept lignes d'état à droite, quatre boutons alignés en bas, huit cases à gauche.",
      },
      {
        id: "version",
        title: "Version de l'addon chargée",
        commands: ['/dump C_AddOns.GetAddOnMetadata("WoWForeverGuilde", "Version")'],
        expected: "La version de la dernière release (0.6.2 au 9 novembre).",
        otherwise:
          "Autre chose : le compagnon n'a pas recopié l'addon. Bouton « Réinstaller l'addon » puis /reload.",
      },
      {
        id: "api",
        title: "API du client lisibles par l'addon",
        severity: "block",
        severityLabel: "à faire une fois, le résultat arrive ici",
        commands: ["/mf api"],
        expected:
          "Quatre lignes dans le chat : talents, métiers, carte (fonctions présentes et absentes), puis ce que l'addon en lit. Le tout est noté et remonte dans la colonne de droite au prochain envoi, ligne « diagnostic ».",
        otherwise:
          "« talents : aucune » ou « métiers · présent : rien » : copie la ligne, c'est le nom des fonctions qui manquent qu'il me faut.",
      },
      {
        id: "talents",
        title: "Talents",
        severity: "later",
        severityLabel: "après le niveau 10",
        commands: [
          "/dump GetNumTalentTabs(), GetNumTalents(1), GetTalentInfo(1, 1)",
          "/dump C_SpecializationInfo.GetTalentInfo(1, 1)",
          "/dump C_ClassTalents.GetActiveConfigID()",
        ],
        expected:
          "Après un point dépensé puis /mf : la ligne Talents passe « À jour » et le build « En jeu » de la fiche montre le point au bon endroit. L'une des trois commandes répond : 3, un nombre, puis nom, icône, rangée, colonne, rang ; ou une table name / tier / column / rank ; ou un numéro de configuration (traits modernes).",
        otherwise:
          "Nil partout : la ligne Talents de /mf dit « Indisponible sur ce client », une ligne « talents.scan » arrive à droite, et le build « En jeu » reste vide sur le site.",
      },
      {
        id: "guild",
        title: "Dans la guilde",
        commands: ["/dump IsInGuild()"],
        expected:
          "true. Positions et annonces de mort passent par messages addon sur le canal de guilde (les canaux de chat sont interdits aux addons sur Forever).",
        otherwise: "false : rien ne circule, ni carte, ni Guilde en jeu, ni annonces, jusqu'à l'invitation.",
      },
      {
        id: "prefix",
        title: "Messages addon enregistrés",
        commands: ['/dump C_ChatInfo.IsAddonMessagePrefixRegistered("WFG")'],
        expected: "true.",
        otherwise: "Sinon ni la carte, ni Guilde en jeu, ni l'appel à l'aide ne fonctionnent.",
      },
    ],
  },
  {
    title: "Premiers mobs, premiers kills",
    when: "Durotar ou Mulgore, les cinq premières minutes.",
    steps: [
      {
        id: "combatlog",
        title: "Journal de combat lisible",
        severity: "block",
        severityLabel: "bloquant pour kills et morts",
        commands: [
          '/run local f=CreateFrame("Frame") f:RegisterEvent("COMBAT_LOG_EVENT_UNFILTERED") f:SetScript("OnEvent",function() local _,e,_,sg,sn,_,_,dg,dn=CombatLogGetCurrentEventInfo() print(e,sg,sn,dg,dn) f:UnregisterAllEvents() end)',
        ],
        expected:
          "Tue trois ou quatre créatures puis /mf : la ligne PvE doit dire « … · 4 créatures ». La commande, lancée avant un coup, affiche une ligne du type « SWING_DAMAGE Player-… TonNom Creature-0-…-299-… Sanglier ».",
        otherwise:
          "Compteur à 0, ou des « secret value » / nil à la place des GUID : Forever masque le journal de combat, l'attribution des morts tombe aussi. Copie la ligne telle quelle.",
      },
      {
        id: "death",
        title: "Mort et annonce",
        expected:
          "Meurs une fois : un pote avec l'addon voit le texte flottant rouge avec une des vingt phrases et entend le son. Chez toi, rien dans le chat, la ligne PvE compte 1 mort, le tueur nommé est la créature, ou « une chute » si tu sautes d'un rocher.",
      },
      {
        id: "level",
        title: "Montée de niveau",
        expected:
          "Au passage du niveau 2, pas d'erreur Lua. La montée apparaîtra dans l'historique de la fiche au prochain envoi.",
      },
    ],
  },
  {
    title: "Métiers et récolte",
    when: "Dès le premier métier appris, vers le niveau 5.",
    steps: [
      {
        id: "profession",
        title: "Fenêtre du métier ouverte une fois",
        commands: [
          "/dump GetProfessionInfo((GetProfessions()))",
          "/dump C_TradeSkillUI.GetBaseProfessionInfo()",
          "/dump C_TradeSkillUI.GetChildProfessionInfo()",
        ],
        expected:
          "Ouvre la fenêtre du métier puis /mf : « Métiers et recettes » passe de « jamais lu » à « À jour » avec la compétence. La première commande donne nom, icône, compétence, maximum, deux nombres, puis la ligne de compétence (171 pour l'alchimie, ou un nombre en 24xx-25xx pour une ligne « Classic »). Les deux autres, fenêtre ouverte, donnent une table avec professionID, parentProfessionID, skillLevel, maxSkillLevel.",
        otherwise:
          "Métier absent de la fiche sur le site alors que /mf le liste : copie la ligne de compétence (septième valeur) de la première commande, le site ne la connaît pas.",
      },
      {
        id: "gathering",
        title: "Une récolte",
        commands: [
          "/dump C_Spell.GetSpellName(2575), C_Spell.GetSpellName(2366), C_Spell.GetSpellName(8613), C_Spell.GetSpellName(7620)",
        ],
        expected:
          "Mine un filon, cueille une herbe ou dépèce : « Récolte et artisanat » compte 1. La commande doit donner « Minage », « Cueillette », « Dépeçage », « Pêche », ou les noms anglais. Pêche : lance la ligne, attends la touche, clique le bouchon, puis /mf api : la ligne « récolte · dernier sort … » doit dire « → fishing » et « poissons » doit avoir compté ; sinon copie cette ligne et /mf trace pendant une prise.",
        otherwise:
          "Un nil : identifiant de sort changé sur Forever. Envoie le nom affiché dans ton livre de sorts, je corrige la table.",
      },
    ],
  },
  {
    title: "Carte, guilde en jeu, appel à l'aide",
    when: "Avec un pote qui a l'addon et « Partager ma position » coché.",
    steps: [
      {
        id: "map",
        title: "Position lisible par l'addon",
        commands: [
          '/dump C_Map.GetBestMapForUnit("player"), C_Map.GetPlayerMapPosition(C_Map.GetBestMapForUnit("player"), "player"):GetXY()',
        ],
        expected:
          "Un numéro de carte puis deux nombres entre 0 et 1. Sur la carte du monde : le point couleur de classe du pote, infobulle au survol, menu au clic.",
      },
      {
        id: "roster",
        title: "Guilde en jeu",
        commands: ["/mf qui"],
        expected:
          "Le pote apparaît sous sa zone avec son niveau. Un texte dans « Je cherche un groupe pour » remonte dans « Cherchent un groupe » chez lui.",
      },
      {
        id: "sos",
        title: "Appel à l'aide",
        commands: ["/mf trace", "/mf sos"],
        expected:
          "Chez le pote : ligne de chat, texte flottant orange et son s'il est sur la même carte, anneau rouge autour de ton point deux minutes. Un second appel dans la minute répond « réessaie dans N s ». Avec la trace active des deux côtés : « envoi G → accepté » chez l'appelant, « reçu G de … » chez l'autre.",
        otherwise:
          "« Appel non envoyé : le jeu a répondu N » : le rang de guilde n'a peut-être pas le droit de parler. « reçu G … ignoré » : la raison est écrite. Rien reçu du tout alors que l'envoi est accepté : le serveur ne relaie pas, copie les deux traces.",
      },
      {
        id: "lfg",
        title: "Outil de recherche de groupe du jeu",
        severity: "later",
        severityLabel: "pour automatiser la recherche de groupe",
        commands: ["/dump C_LFGList.HasActiveEntryInfo()", "/dump C_LFGList.GetActiveEntryInfo()"],
        expected: "Une fois inscrit dans l'outil du jeu : true, puis une table avec activityID et comment.",
        otherwise: "C_LFGList absent : Forever a refait son outil, on garde le champ manuel.",
      },
    ],
  },
  {
    title: "Envoi au site",
    steps: [
      {
        id: "sync",
        title: "Déconnexion ou /reload, puis le compagnon",
        expected:
          "Dans la minute, le compagnon affiche « envoyé » avec le nom du perso ; le site le montre dans le roster avec son niveau, le set « En jeu » dans Équipement et les compteurs dans Progression.",
        otherwise: "Un refus « client non accepté » renvoie à la version d'interface.",
      },
      {
        id: "reload",
        title: "Rappel de sauvegarde",
        expected:
          "Après trois heures sans déconnexion ni /reload, hors combat, le dialogue « Mettre tes données à l'abri ? » s'ouvre une fois. Pas à provoquer.",
      },
    ],
  },
  {
    title: "Plus tard dans la semaine",
    steps: [
      {
        id: "dungeon",
        title: "Premier donjon, Gouffre de Ragefeu",
        severity: "later",
        severityLabel: "niveau 13",
        commands: [
          '/run local f=CreateFrame("Frame") f:RegisterEvent("ENCOUNTER_END") f:SetScript("OnEvent",function(_,_,id,name,_,size,ok) print("ENCOUNTER_END",id,name,size,ok) end)',
        ],
        expected: "Au dernier boss, la ligne PvE compte 1 boss et « 1 donjons ».",
        otherwise:
          "Boss compté mais pas le donjon : l'identifiant de rencontre diffère de Classic. La commande, lancée avant le boss, affiche l'identifiant à m'envoyer.",
      },
      {
        id: "pvp",
        title: "Honneur et champs de bataille",
        severity: "later",
        severityLabel: "niveau 10 pour le Goulet",
        commands: ["/dump GetPVPLifetimeStats()"],
        expected: "Deux nombres. Un BG joué compte 1 joué et, le cas échéant, 1 gagné.",
      },
      {
        id: "reputation",
        title: "Réputations, accès, verrous",
        expected:
          "La ligne est « À jour » dès la connexion. Quêtes d'accès et identifiants des raids restent à confirmer quand la guilde y arrivera.",
      },
    ],
  },
];

const STORAGE_KEY = "mf-tests-en-jeu";
const ALL_IDS = SECTIONS.flatMap((s) => s.steps.map((st) => st.id));

function loadChecked(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return new Set(raw ? (JSON.parse(raw) as string[]) : []);
  } catch {
    return new Set();
  }
}

export function TestsPage() {
  const me = useCurrentUser();
  const [checked, setChecked] = useState<Set<string>>(loadChecked);
  const done = useMemo(() => ALL_IDS.filter((id) => checked.has(id)).length, [checked]);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify([...checked]));
    } catch {
      /* stockage indisponible : la page marche quand même */
    }
  }, [checked]);

  if (me.site_role !== "gm") return <Navigate to="/roster" replace />;

  const toggle = (id: string) =>
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <>
      <PageTitle>Tests en jeu</PageTitle>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_400px]">
        {/* Gauche : ce que je dois tester. */}
        <div className="space-y-8">
          <Card className="space-y-3">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="font-display text-lg">À tester</span>
              <span className="font-mono text-sm text-gold-light">
                {done} / {ALL_IDS.length}
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded bg-bg">
              <div
                className="h-full bg-gold transition-[width]"
                style={{ width: `${(100 * done) / ALL_IDS.length}%` }}
              />
            </div>
            <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm">
              {SECTIONS.map((section, i) => {
                const n = section.steps.filter((s) => checked.has(s.id)).length;
                return (
                  <a key={section.title} href={`#tests-${i}`} className="text-text hover:text-gold">
                    {section.title}{" "}
                    <span
                      className={clsx(
                        "font-mono text-xs",
                        n === section.steps.length ? "text-success" : "text-muted",
                      )}
                    >
                      {n}/{section.steps.length}
                    </span>
                  </a>
                );
              })}
              <button
                type="button"
                className="ml-auto text-xs text-muted hover:text-text"
                onClick={() => setChecked(new Set())}
              >
                Tout décocher
              </button>
            </div>
            <p className="text-xs text-muted">
              Les collecteurs de l'addon n'ont jamais tourné sur le vrai client Forever. Si une étape rate,
              copie la sortie du /dump ou l'erreur Lua telle quelle. Les cases restent cochées sur ce
              navigateur.
            </p>
          </Card>
          {SECTIONS.map((section, i) => (
            <section key={section.title} id={`tests-${i}`} className="scroll-mt-24 space-y-3">
              <div>
                <h2 className="font-display text-xl">{section.title}</h2>
                {section.when && <p className="text-sm text-muted">{section.when}</p>}
              </div>
              <ol className="space-y-2">
                {section.steps.map((step) => (
                  <StepRow
                    key={step.id}
                    step={step}
                    checked={checked.has(step.id)}
                    onToggle={() => toggle(step.id)}
                  />
                ))}
              </ol>
            </section>
          ))}
        </div>

        {/* Droite : ce qui remonte des addons, collé à l'écran pendant qu'on déroule la liste. */}
        <aside className="space-y-3 lg:sticky lg:top-24 lg:max-h-[calc(100vh-7rem)] lg:self-start lg:overflow-y-auto">
          <AddonErrorsCard />
          <p className="text-xs text-muted">
            Une erreur Lua de l'addon commence par Interface/AddOns/WoWForeverGuilde/… Elles sont gardées dans
            le fichier de l'addon, visibles avec /mf erreurs, et remontent ici à l'envoi suivant.
          </p>
        </aside>
      </div>
    </>
  );
}

/** Erreurs des collecteurs remontées par les addons de toute la guilde, à copier d'un bloc. */
function AddonErrorsCard() {
  const errors = useAddonErrors(true);
  const [copied, setCopied] = useState(false);
  if (errors.isPending) return <Spinner />;
  const list = errors.data ?? [];
  const asText = list
    .map(
      (e) =>
        `${e.at ? formatDateTime(e.at) : "?"} · ${e.user.display_name}${e.device ? ` (${e.device})` : ""} · addon ${e.addon}${
          e.client ? ` · client ${e.client}` : ""
        }\n  ${e.where || "?"} : ${e.error}`,
    )
    .join("\n");
  const copyAll = async () => {
    try {
      await navigator.clipboard.writeText(asText);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* presse-papiers refusé : le texte reste sélectionnable ci-dessous */
    }
  };
  return (
    <Card className={clsx("space-y-3", list.length > 0 && "border-danger/40")}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-xl">Erreurs remontées par les addons</h2>
        <span className="text-xs text-muted">14 derniers jours · toute la guilde · dédoublonnées</span>
      </div>
      {errors.isError ? (
        <p className="text-sm text-danger">Impossible de charger les erreurs.</p>
      ) : list.length === 0 ? (
        <p className="text-sm text-muted">
          Aucune erreur reçue. Un collecteur qui plante est noté par l'addon et arrive ici au prochain envoi.
        </p>
      ) : (
        <>
          <ul className="space-y-2">
            {list.map((e, i) => (
              <ErrorRow key={`${e.user.id}-${e.at}-${i}`} e={e} />
            ))}
          </ul>
          <button
            type="button"
            onClick={copyAll}
            className={clsx(
              "rounded-sm border px-3 py-1.5 text-sm transition-colors",
              copied
                ? "border-success text-success"
                : "border-border text-muted hover:border-gold hover:text-gold",
            )}
          >
            {copied ? "Tout copié" : `Tout copier (${list.length})`}
          </button>
        </>
      )}
    </Card>
  );
}

function ErrorRow({ e }: { e: AddonError }) {
  return (
    <li className="rounded-md border border-border bg-bg/60 p-3 text-sm">
      <div className="flex flex-wrap items-baseline gap-x-2 text-xs text-muted">
        <span className="text-text">{e.at ? formatDateTime(e.at) : "heure inconnue"}</span>
        <span>{e.user.display_name}</span>
        {e.device && <span>· {e.device}</span>}
        <span>· addon {e.addon}</span>
        {e.client && <span>· client {e.client}</span>}
        <span>· reçu {formatDateTime(e.received_at)}</span>
      </div>
      <div className="mt-1 font-mono text-[12.5px] break-words whitespace-pre-wrap">
        <span className="text-gold-light">{e.where || "?"}</span> : {e.error}
      </div>
    </li>
  );
}

function StepRow({ step, checked, onToggle }: { step: Step; checked: boolean; onToggle: () => void }) {
  return (
    <li
      className={clsx(
        "grid grid-cols-[auto_1fr] gap-3 rounded-md border bg-surface/80 p-3 transition-colors",
        checked ? "border-success/40" : step.severity === "block" ? "border-danger/40" : "border-border",
      )}
    >
      <input
        type="checkbox"
        id={`test-${step.id}`}
        checked={checked}
        onChange={onToggle}
        className="mt-1 size-4 accent-gold"
        aria-label={step.title}
      />
      <div className={clsx("min-w-0 space-y-1.5", checked && "opacity-60")}>
        <label
          htmlFor={`test-${step.id}`}
          className="flex flex-wrap items-baseline gap-x-2 gap-y-1 font-medium"
        >
          {step.title}
          {step.severity && (
            <span
              className={clsx(
                "rounded-full border px-2 py-0.5 text-[11px] font-normal",
                step.severity === "block" ? "border-danger/60 text-danger" : "border-gold/50 text-gold-light",
              )}
            >
              {step.severityLabel}
            </span>
          )}
        </label>
        {step.commands?.map((command) => (
          <CommandLine key={command} command={command} />
        ))}
        <p className="text-sm">
          <span className="text-success">Attendu</span> <span className="text-muted">·</span> {step.expected}
        </p>
        {step.otherwise && (
          <p className="text-sm">
            <span className="text-danger">Sinon</span> <span className="text-muted">·</span> {step.otherwise}
          </p>
        )}
      </div>
    </li>
  );
}

function CommandLine({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      const selection = window.getSelection();
      const node = document.getElementById(`cmd-${command.length}-${command.slice(0, 12)}`);
      if (selection && node) {
        const range = document.createRange();
        range.selectNodeContents(node);
        selection.removeAllRanges();
        selection.addRange(range);
      }
    }
  };
  return (
    <div className="flex items-start gap-2">
      <code
        id={`cmd-${command.length}-${command.slice(0, 12)}`}
        className="min-w-0 flex-1 rounded bg-bg px-2 py-1 font-mono text-[12.5px] break-all text-gold-light"
      >
        {command}
      </code>
      <button
        type="button"
        onClick={copy}
        className={clsx(
          "shrink-0 rounded-sm border px-2 py-1 text-xs transition-colors",
          copied
            ? "border-success text-success"
            : "border-border text-muted hover:border-gold hover:text-gold",
        )}
      >
        {copied ? "copié" : "copier"}
      </button>
    </div>
  );
}
