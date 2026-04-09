# RAG_DATA_ENGINEER

Pipeline RAG (Retrieval-Augmented Generation) qui ingère un dossier Google Drive,
le découpe, génère des embeddings via **Voyage AI** (`voyage-3`) et persiste le tout
dans ChromaDB. La mise à jour incrémentale est orchestrée par Airflow.

## Architecture

```
Google Drive folder
        │
        ▼  (service account, drive.readonly)
 src/drive_loader.py   ── liste + télécharge (PDF, DOCX, txt, md, csv, gdoc, gsheet)
        │
        ▼
 src/rag_builder.py    ── extraction texte → chunking par tokens → embeddings Voyage
        │
        ▼
 chroma_db/            ── ChromaDB persisté (cosine, métadonnées par fichier)
        ▲
        │
 airflow/dags/rag_upgrade_dag.py  ── déclenche run_pipeline() à intervalle régulier
```

L'« upgrade » est **incrémental** : on lit `modifiedTime` de chaque fichier Drive
et on compare avec la valeur stockée dans Chroma. Seuls les fichiers nouveaux ou
modifiés sont ré-embeddés ; les fichiers supprimés du Drive sont retirés du store.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# remplir VOYAGE_API_KEY, GOOGLE_SERVICE_ACCOUNT_FILE, GDRIVE_FOLDER_ID
```

### Google Drive – service account

1. Créer un service account dans Google Cloud Console.
2. Télécharger le JSON et pointer `GOOGLE_SERVICE_ACCOUNT_FILE` dessus.
3. **Partager le dossier Drive** avec l'email du service account (lecture suffit).
4. Récupérer l'ID du dossier dans son URL : `https://drive.google.com/drive/folders/<ID>`

## Lancer en local

```bash
python scripts/build_rag.py
```

## Déploiement Airflow

1. Copier `airflow/dags/rag_upgrade_dag.py` dans `$AIRFLOW_HOME/dags/`.
2. Le worker doit pouvoir importer ce repo : définir `RAG_PROJECT_PATH` (Airflow
   Variable ou env var) sur le chemin absolu du repo, et installer
   `requirements.txt` dans l'environnement Python du worker.
3. Définir les Variables Airflow (ou env vars du worker) :
   `VOYAGE_API_KEY`, `GOOGLE_SERVICE_ACCOUNT_FILE`, `GDRIVE_FOLDER_ID`,
   `CHROMA_PERSIST_DIR` (idéalement un volume partagé entre workers),
   `RAG_PROJECT_PATH`.
4. Activer le DAG `rag_data_engineer_upgrade` dans l'UI Airflow.

Le DAG tourne `@hourly` par défaut — modifier `schedule=` dans le fichier au besoin.

## Structure

```
├── config.py                 # chargement des settings depuis l'env
├── requirements.txt
├── scripts/
│   └── build_rag.py          # entrée CLI
├── src/
│   ├── drive_loader.py       # téléchargement Drive
│   ├── rag_builder.py        # parsing + chunking + embeddings + Chroma
│   └── rag_pipeline.py       # orchestration end-to-end
└── airflow/
    └── dags/
        └── rag_upgrade_dag.py
```
