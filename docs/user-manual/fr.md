# Planificateur Radio Azan — Guide de l'utilisateur

*Langues : [English](en.md) · [العربية](ar.md) · [Bahasa Melayu](ms.md) · [اردو](ur.md) · **Français***

> **Remarque :** l'interface de l'application elle-même est en anglais.
> C'est pourquoi le nom de chaque bouton ou page est indiqué en anglais
> à côté de sa traduction, afin que vous puissiez facilement le retrouver
> à l'écran.

## À propos de ce projet

Cette application a été créée par Sherif, pour la satisfaction d'Allah —
conçue librement afin que chacun puisse faire résonner l'adhan
automatiquement sur ses propres enceintes connectées à l'heure de la
prière, sans aucune manipulation quotidienne. Elle est libre
d'utilisation, libre de partage, et libre de modification. Si elle vous
est utile, à vous ou à votre famille, c'est là tout son but.

Ce guide explique comment **utiliser** l'application une fois qu'elle est
déjà installée et en fonctionnement — il ne couvre pas son installation
sur un serveur (voir le [README](../../README.md) principal pour cela).
Il suppose que quelqu'un (vous-même, un proche à l'aise avec la
technique, ou un membre de la famille) l'a déjà configurée et vous a
donné une adresse web du type `http://<adresse-de-votre-serveur>:8730`.

## Ouvrir l'application pour la première fois

1. Ouvrez l'adresse web de l'application dans n'importe quel navigateur
   (ordinateur ou téléphone).
2. La toute première fois, elle vous demandera de **créer un mot de
   passe administrateur** (Admin password) (8 caractères minimum). C'est
   le seul mot de passe qui protège l'application — choisissez-en un
   dont vous vous souviendrez, et ne le partagez avec personne qui ne
   devrait pas pouvoir modifier vos réglages.
3. Ensuite, à chaque ouverture de l'application, ce mot de passe vous
   sera demandé pour vous connecter (Login).

## Le tableau de bord (Dashboard)

C'est la page que vous voyez après connexion. Elle affiche :

- Les cinq horaires de prière du jour, selon la source d'horaires que
  vous avez configurée.
- Si la radio de chaque prière a déjà démarré/s'est déjà arrêtée
  aujourd'hui.
- Une courte liste de l'activité récente (pratique pour un coup d'œil
  rapide, sans avoir à ouvrir la page complète des journaux).

## Page Réglages (Settings)

### Radio et horaires (Radio & timing)

- **URL du flux (Stream URL)** — l'adresse web du flux audio de la
  station de radio. Vous n'avez normalement pas besoin de la modifier,
  sauf si la station change l'adresse de son flux.
- **Type de contenu du flux (Stream content type)** — un détail
  technique dont certaines enceintes ont besoin ; laissez tel quel sauf
  indication contraire.
- **Nom de la station (Station name)** — utilisé uniquement pour Alexa,
  car Alexa ne peut pas lire une adresse web directement ; l'application
  demande plutôt à Alexa de jouer cette station par son nom (comme dire
  « Alexa, joue *Warna 94.2FM* »).
- **Durée par défaut (Default duration)** — pendant combien de minutes
  la radio joue avant de s'arrêter automatiquement.
- **Démarrage anticipé (Start early)** — combien de **secondes** avant
  l'heure de prière réelle la radio doit démarrer (0 = démarre pile à
  l'heure). Une petite avance (par exemple 15 secondes) peut être utile
  pour que le son soit déjà en train de jouer dès le début de l'heure de
  prière.
- **Fuseau horaire (Timezone)** — le fuseau horaire utilisé pour
  calculer/afficher les horaires de prière.
- **Source des horaires de prière (Prayer time source)** — choisissez
  **Singapore (MUIS)** si vous êtes à Singapour, pour le calendrier
  officiel publié par le gouvernement. Sinon, choisissez **Generic
  (Aladhan)** et indiquez votre latitude/longitude ainsi qu'une méthode
  de calcul — cela fonctionne n'importe où dans le monde.

Cliquez sur **Save** après avoir effectué des modifications. Le bouton
**Refresh today's prayer times now** récupère manuellement le calendrier
du jour (cela se fait normalement automatiquement chaque jour).

### Prières (Prayers)

Un tableau vous permettant d'ajuster individuellement chacune des 5
prières :

- **Activée (Enabled)** — décochez pour ignorer complètement une prière
  donnée (par exemple si vous ne voulez pas d'adhan automatique pour
  Fajr).
- **Durée personnalisée (Duration override)** — une durée de lecture
  différente juste pour cette prière, remplaçant le réglage par défaut
  global ci-dessus. Laissez vide pour utiliser le réglage par défaut.
- **Démarrage anticipé personnalisé (Start early override)** — un temps
  de démarrage anticipé différent (en secondes) juste pour cette prière.
  Laissez vide pour utiliser le réglage global par défaut ; saisissez
  `0` pour que cette prière précise démarre pile à l'heure même si les
  autres démarrent en avance.

### Mot de passe administrateur (Admin password)

Modifiez ici votre mot de passe de connexion. Vous devrez d'abord saisir
votre mot de passe actuel.

## Page Appareils (Devices)

C'est ici que vous connectez vos véritables enceintes connectées.

### Appareils configurés (tableau en haut de page)

Une fois qu'au moins un appareil a été ajouté, il apparaît ici avec :

- **Activé / Désactiver (Enabled / Disable)** — allumer ou éteindre
  entièrement un appareil sans le supprimer.
- **Joue pour (Plays for)** — une case à cocher pour chacune des 5
  prières. Décochez une prière pour empêcher **cet appareil précis** de
  jouer à ce moment-là, tout en continuant de jouer aux autres prières.
  Cela permet, par exemple, qu'une enceinte de chambre ne joue que pour
  Fajr et Isha, tandis qu'une enceinte de salon joue pour les cinq
  prières.
- **Test (Démarrer/Arrêter) — Test (Start/Stop)** — déclenche
  manuellement l'appareil dès maintenant, utile pour confirmer qu'il
  fonctionne réellement avant de lui faire confiance pour une véritable
  heure de prière.
- **Supprimer (Remove)** — supprime définitivement cet appareil de
  l'application (vous pouvez toujours le rajouter plus tard via
  Discover).

### Ajouter une enceinte Google Home / Nest

1. Cliquez sur **Discover Google speakers** — cela scanne votre réseau
   local pendant quelques secondes.
2. Cliquez sur **Add** à côté de l'enceinte souhaitée. Elle doit déjà
   être configurée dans l'application Google Home sur votre téléphone.

### Ajouter un Apple HomePod

1. Cliquez sur **Discover HomePods**.
2. Cliquez sur **Pair** à côté de l'appareil souhaité — votre HomePod
   affichera (ou annoncera) un code PIN.
3. Saisissez ce code PIN et confirmez.
4. Cliquez sur **Add**.

### Ajouter un appareil Amazon Alexa / Echo

Alexa n'offre pas de moyen d'être contrôlée directement comme le font
Google et Apple ; cette application communique donc avec elle via une
instance **Home Assistant** (un logiciel domotique distinct, gratuit et
open source) sur laquelle l'extension communautaire **Alexa Media
Player** est installée et connectée à votre compte Amazon.

1. Si Home Assistant avec Alexa Media Player n'est pas encore configuré,
   demandez à la personne qui gère votre réseau de le configurer d'abord
   (cette étape technique n'est à faire qu'une seule fois).
2. Dans Home Assistant, générez un **jeton d'accès longue durée
   (Long-Lived Access Token)** (disponible dans votre profil → Security).
3. Retournez dans la page Appareils (Devices) de cette application,
   collez l'adresse web de votre Home Assistant ainsi que ce jeton dans
   la carte Alexa, puis cliquez sur **Save & test connection**.
4. Cliquez sur **Discover Alexa devices** — cela demande à Home
   Assistant quels appareils Echo il connaît.
5. Cliquez sur **Add** à côté de chaque véritable enceinte souhaitée
   (ignorez les entrées qui ressemblent à des groupes d'appareils plutôt
   qu'à une enceinte physique réelle, comme « Everywhere » ou « Echo
   group »).

## Page Journaux (Logs)

Une liste continue de tout ce que l'application a fait — connexions des
appareils, lectures et arrêts réussis ou échoués, avertissements et
erreurs. Si une prière n'a pas joué, ou qu'un appareil ne s'est pas
arrêté alors qu'il aurait dû, c'est le premier endroit à consulter : il
montrera exactement ce qui s'est passé et pourquoi.

## Obtenir de l'aide

Ce projet est open source et libre d'utilisation, de modification et de
partage pour tous. Si vous rencontrez un problème, avez une correction
à proposer pour la traduction de ce guide, ou souhaitez suggérer une
amélioration, merci d'ouvrir une « issue » ou une « pull request » sur
la page GitHub du projet.

*Puisse ceci être bénéfique pour vous et votre famille. Jazakumullahu
khairan.*
