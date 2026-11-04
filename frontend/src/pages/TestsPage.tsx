import clsx from "clsx";
import { useEffect, useMemo, useState } from "react";
import { Navigate } from "react-router";
import { useCurrentUser } from "@/auth/useCurrentUser";
import { Card, PageTitle } from "@/components/ui";

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
        expected: "« 0.3.1 ».",
        otherwise:
          "Autre chose : le compagnon n'a pas recopié l'addon. Bouton « Réinstaller l'addon » puis /reload.",
      },
      {
        id: "talents",
        title: "Talents",
        severity: "later",
        severityLabel: "après le niveau 10",
        commands: [
          "/dump GetNumTalentTabs(), GetNumTalents(1), GetTalentInfo(1, 1)",
          "/dump GetNumTalentGroups(), GetActiveTalentGroup()",
        ],
        expected:
          "3, un nombre, puis nom, icône, rangée, colonne, rang. La seconde commande dit si la double spé existe.",
        otherwise:
          "Nil partout : la ligne Talents de /mf dira « Indisponible sur ce client » et le build « En jeu » restera vide sur le site.",
      },
      {
        id: "channel",
        title: "Canal caché des morts",
        commands: ['/dump GetChannelName("wfgdeaths")'],
        expected:
          "Après 5 s en jeu, un numéro supérieur à 0, et ce canal n'apparaît dans aucun onglet de chat.",
        otherwise: "0 : les annonces de mort et les positions hors guilde ne circuleront pas.",
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
        commands: ["/dump C_TradeSkillUI.GetBaseProfessionInfo()"],
        expected:
          "Ouvre la fenêtre du métier puis /mf : « Métiers et recettes » passe de « jamais lu » à « À jour » avec la compétence. La commande, fenêtre ouverte, donne une table avec professionID, skillLevel, maxSkillLevel.",
      },
      {
        id: "gathering",
        title: "Une récolte",
        commands: [
          "/dump C_Spell.GetSpellName(2575), C_Spell.GetSpellName(2366), C_Spell.GetSpellName(8613), C_Spell.GetSpellName(7620)",
        ],
        expected:
          "Mine un filon, cueille une herbe ou dépèce : « Récolte et artisanat » compte 1. La commande doit donner « Minage », « Cueillette », « Dépeçage », « Pêche », ou les noms anglais.",
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
        commands: ["/mf sos"],
        expected:
          "Chez le pote : ligne de chat, texte flottant orange et son s'il est sur la même carte, anneau rouge autour de ton point deux minutes. Un second appel dans la minute répond « réessaie dans N s ».",
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
      <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
        <aside className="space-y-4 lg:sticky lg:top-24 lg:self-start">
          <Card className="space-y-3">
            <div className="flex items-baseline justify-between">
              <span className="font-display text-lg">Avancement</span>
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
            <ol className="space-y-1 text-sm">
              {SECTIONS.map((section, i) => {
                const n = section.steps.filter((s) => checked.has(s.id)).length;
                return (
                  <li key={section.title} className="flex items-baseline justify-between gap-2">
                    <a href={`#tests-${i}`} className="text-text hover:text-gold">
                      {section.title}
                    </a>
                    <span
                      className={clsx(
                        "font-mono text-xs",
                        n === section.steps.length ? "text-success" : "text-muted",
                      )}
                    >
                      {n}/{section.steps.length}
                    </span>
                  </li>
                );
              })}
            </ol>
            <button
              type="button"
              className="text-xs text-muted hover:text-text"
              onClick={() => setChecked(new Set())}
            >
              Tout décocher
            </button>
          </Card>
          <p className="text-xs text-muted">
            Les collecteurs de l'addon n'ont jamais tourné sur le vrai client Forever. Si une étape rate,
            copie la sortie du /dump ou l'erreur Lua telle quelle. Les cases restent cochées sur ce
            navigateur.
          </p>
        </aside>

        <div className="space-y-8">
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
          <p className="text-xs text-muted">
            Une erreur Lua de l'addon commence par Interface/AddOns/WoWForeverGuilde/… Les erreurs sont aussi
            gardées dans le fichier de l'addon et remontent au site à l'envoi suivant.
          </p>
        </div>
      </div>
    </>
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
