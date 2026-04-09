# RAG_DATA_ENGINEER

Pipeline RAG (Retrieval-Augmented Generation) qui ingère un dossier Google Drive,
le découpe, génère des embeddings via **Voyage AI** (`voyage-3`) et persiste le tout
dans ChromaDB. Distribué comme **package Python installable** ; le DAG Airflow vit
dans un repo séparé (`airflow-local-setup`) et n'a qu'à l'importer.

## Architecture

```
Google Drive folder
        │
        ▼  (service account, drive.readonly)
 rag_data_engineer.drive_loader   ── liste + télécharge (PDF, DOCX, PPTX, code, configs, gdoc, gsheet)
        │
        ▼
 rag_data_engineer.rag_builder    ── extraction → chunking par tokens → embeddings Voyage
        │
        ▼
 chroma_db/                       ── ChromaDB persisté (cosine, métadonnées par fichier)
```

L'« upgrade » est **incrémental** : on lit `modifiedTime` de chaque fichier Drive
et on compare avec la valeur stockée dans Chroma. Seuls les fichiers nouveaux ou
modifiés sont ré-embeddés ; les fichiers supprimés du Drive sont retirés du store.

## Structure

```
├── pyproject.toml                # package installable (PEP 621)
├── requirements.txt              # `-e .` pour le dev
├── README.md
├── .env.example
├── scripts/
│   └── build_rag.py              # wrapper CLI (équivalent à `python -m rag_data_engineer`)
└── rag_data_engineer/            # le package
    ├── __init__.py               # expose `run_pipeline` et `Settings`
    ├── __main__.py               # `python -m rag_data_engineer`
    ├── config.py                 # `Settings.from_env()`
    ├── drive_loader.py           # téléchargement Drive
    ├── rag_builder.py            # parsing + chunking + embeddings + Chroma
    └── rag_pipeline.py           # orchestration end-to-end
```

## Setup local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env
# remplir VOYAGE_API_KEY, GOOGLE_SERVICE_ACCOUNT_FILE, GDRIVE_FOLDER_ID
python -m rag_data_engineer
```

### Google Drive – service account

1. Créer un service account dans Google Cloud Console (rien à activer côté IAM).
2. Activer l'API **Google Drive** sur le projet.
3. Télécharger le JSON et pointer `GOOGLE_SERVICE_ACCOUNT_FILE` dessus.
4. **Partager le dossier Drive** avec l'email du service account (Viewer suffit).
5. Récupérer l'ID du dossier dans son URL : `https://drive.google.com/drive/folders/<ID>`

## Variables d'environnement

| Variable                       | Requis | Défaut                  | Description                                    |
|--------------------------------|--------|-------------------------|------------------------------------------------|
| `VOYAGE_API_KEY`               | oui    | —                       | Clé API Voyage AI                              |
| `GOOGLE_SERVICE_ACCOUNT_FILE`  | oui    | —                       | Chemin absolu vers le JSON du SA               |
| `GDRIVE_FOLDER_ID`             | oui    | —                       | ID du dossier Drive racine                     |
| `CHROMA_PERSIST_DIR`           | non    | `./chroma_db`           | Dossier de persistance Chroma                  |
| `CHROMA_COLLECTION`            | non    | `rag_data_engineer`     | Nom de la collection Chroma                    |
| `EMBEDDING_MODEL`              | non    | `voyage-3`              | Modèle d'embeddings Voyage                     |
| `CHUNK_SIZE`                   | non    | `800`                   | Taille des chunks (en tokens)                  |
| `CHUNK_OVERLAP`                | non    | `120`                   | Recouvrement entre chunks (en tokens)          |

## Utilisation depuis Airflow

Le code reste **dans ce repo**. Le repo `airflow-local-setup` installe ce package via pip
et n'héberge que le DAG :

```
# airflow-local-setup/requirements.txt
rag-data-engineer @ git+https://github.com/yannoushka74/RAG_DATA_ENGINEER@main
```

```python
# airflow-local-setup/dags/dag_rag_data_engineer.py
from rag_data_engineer import run_pipeline
# ... PythonOperator(python_callable=run_pipeline)
```

Pour figer une version : remplacer `@main` par un tag git (`@v0.1.0`) ou un SHA.

## Utilisation programmatique

```python
from rag_data_engineer import run_pipeline, Settings

stats = run_pipeline()                       # lit la conf depuis l'env
# ou
stats = run_pipeline(Settings(...))          # conf injectée
print(stats)
# {'added': 12, 'updated': 3, 'skipped': 1184, 'chunks': 95, 'failed': 0, 'deleted': 0}
```
