# Sport à l'antenne

Planning des diffusions TV de basket (dont la Betclic Élite), football, rugby (Top 14, coupes d'Europe, XV de France), handball, fléchettes, pétanque, hockey sur glace, MMA, MotoGP et Formule 1 sur DAZN, EuroLeague TV, L'Équipe, beIN Sports, Canal+, Eurosport, France TV, TF1, M6 et RMC Sport.

## Comment ça marche

- `scripts/build_data.py` télécharge le guide TV XMLTV de [xmltvfr.fr](https://xmltvfr.fr) (5 jours à venir, toutes les chaînes ci-dessous) et le calendrier officiel EuroLeague / EuroCup (`api-live.euroleague.net`, 3 semaines à venir). Il garde les programmes des sports suivis et écrit `data/events.json` et `data/sports.ics`.
- `.github/workflows/update.yml` relance le script toutes les 4 heures sur GitHub et publie les données.
- `index.html` affiche le planning (filtres par sport et par chaîne, recherche, directs en rouge).
- `data/sports.ics` est un agenda auquel on peut s'abonner pour recevoir une alerte 15 minutes avant chaque diffusion.

## Chaînes couvertes

| Diffuseur | Chaînes du guide |
|---|---|
| DAZN | DAZN 1 à 5 |
| EuroLeague TV | tous les matchs EuroLeague et EuroCup |
| L'Équipe | La chaîne L'Équipe, L'Équipe Live 1 à 7, L'Équipe Live Foot |
| beIN Sports | beIN SPORTS 1, 2, 3, MAX 4 à 10 |
| Canal+ | Canal+, Canal+ Sport, Sport 360, Foot, Premier League, Live 1 à 19, Infosport+ |
| Eurosport | Eurosport 1, 2, Eurosport 360 |
| France TV | France 2, France 3, France 4 |
| TF1 / M6 | TF1, M6 |
| RMC Sport | RMC Sport 1, 2, Live, UHD |

Les sports sont reconnus à partir de la catégorie, du titre et de la description de chaque programme ; les règles sont en tête de `scripts/build_data.py` (`SPORTS`, `BROADCASTERS`).

## Mise en ligne (GitHub Pages, gratuit)

1. Créer un dépôt GitHub (public pour GitHub Pages gratuit) et y pousser ces fichiers sur `main`.
2. Settings › Pages › Source : « Deploy from a branch », branche `main`, dossier `/ (root)`.
3. Actions › « Mise à jour du programme » › Run workflow (première génération des données).
4. L'appli est sur `https://<compte>.github.io/<dépôt>/` et l'agenda sur `https://<compte>.github.io/<dépôt>/data/sports.ics`.

## Tester en local

```
python3 scripts/build_data.py
python3 -m http.server 8000   # puis http://localhost:8000
```
