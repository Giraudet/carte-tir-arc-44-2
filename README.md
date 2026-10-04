# Carte des concours de tir à l'arc du 44 : mise en route

1. Créez un compte gratuit sur github.com, puis un dépôt (New repository) nommé `carte-tir-arc-44`.
2. Dans le dépôt : Add file > Upload files, déposez `index.html`, `scraper.py` et `requirements.txt`.
3. Add file > Create new file. Dans le nom, tapez exactement `.github/workflows/update.yml`
   (les « / » créent les dossiers). Collez le contenu du fichier `update.yml`, puis Commit.
4. Onglet Actions > « Mise à jour des concours » > Run workflow. Après environ 1 minute, une pastille verte
   apparaît et le fichier `events.json` est créé. Ensuite, la mise à jour se fait seule chaque nuit.
   Si la pastille est rouge, ouvrez l'exécution et copiez-moi le message d'erreur.
5. Netlify : Site configuration > Build & deploy > Link repository, choisissez ce dépôt (aucune commande de
   build, dossier de publication vide ou « / »). Si Netlify ne le propose pas pour votre site, créez un
   nouveau site depuis GitHub : on utilisera sa nouvelle adresse pour le QR code.
