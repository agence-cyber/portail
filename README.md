# Portail propriétaire Aurora Conciergerie

Site statique publié sur portail.auroraconciergerie.com (GitHub Pages).

- `index.html` : page du portail, données chiffrées avec le code d'accès du propriétaire.
- `tools/portail.py` : reconstruction (Lodgify + récaps) et gestion des récaps ; `tools/config.json` : propriétaires et biens ; `tools/template.html` : gabarit.
- `data/*.enc` : récaps de séjours chiffrés (clé hors dépôt) ; `data/market.json` : comparaison marché.

Aucune clé ni donnée en clair dans ce dépôt. Mise à jour quotidienne automatisée.
