# 🧦 Projet Chaussettes.io – Analyse de logs en temps réel

Ce projet consiste à développer un système d'analyse de logs HTTP en temps réel pour l'entreprise fictive **Chaussettes.io**, à l'aide de **Python**, **Apache Spark** et **Kafka**. Il est divisé en trois étapes évolutives : **version minimale**, **version complète**, et **version finale**.

---

## 📁 Structure du dépôt

```
.
├── minimal/                    # Version minimale
│   ├── log_generator.py
│   └── spark_streaming_analyzer.py
│
├── complet/                    # Version complète
│   ├── log_generator.py
│   ├── spark_streaming_analyzer.py
│   ├── conf/
│   │   └── spark-defaults.conf
│   └── README.md
│
├── finale/                     # (À venir) Version finale avec Kafka, seuils, alertes, etc.
└── README.md                   # Ce fichier
```

---

## 🧪 Prérequis

- Python ≥ 3.8
- Java JDK ≥ 17
- Apache Spark (3.4.1 ou 4.0.0)
- PySpark (`pip install pyspark`)

---

## 🧩 Version 1 : minimale

### 🎯 Objectif :
- Générer 1 ligne de log HTTP Apache par seconde (aléatoire).
- Lire ces logs via une socket avec Spark Streaming.
- Afficher les erreurs HTTP détectées (codes ≥ 400).

### ▶️ Lancement :

Dans un terminal :
```bash
python minimal/minimal.py
```

Puis dans un autre :
```bash
python minimal/sparkStreaming.py
```

---

## 🧩 Version 2 : complète

### 🎯 Objectif :
- Générateur de logs **configurable via argparse**
- Contrôle du taux d'erreurs par utilisateurs et par URLs
- Configuration du **chiffrement et de l'authentification Spark** pour la production

### ⚙️ Paramètres du générateur (`log_gen.py`)

| Argument | Description |
|----------|-------------|
| `--rate` | Nombre de logs générés par seconde |
| `--error-users` | % d'utilisateurs qui génèrent des erreurs |
| `--error-rate` | % des requêtes erronées chez ces utilisateurs |
| `--error-urls` | % d'URLs susceptibles de générer des erreurs |
| `--host` | Hôte pour le socket (par défaut : `localhost`) |
| `--port` | Port d'écoute (par défaut : `9999`) |

### ▶️ Exemple de lancement :

```bash
python complet/log_gen.py --rate 10 --error-users 30 --error-rate 60 --error-urls 50
```

### 🧠 Analyse Spark Streaming :

```bash
python complet/sparkStreamingComplet.py
```

### 🔐 Sécurité – Configuration Spark pour la production

Un fichier `spark-defaults.conf` est fourni dans `complet/conf/`. Il contient :

```properties
spark.authenticate true
spark.authenticate.secret chaussettesIo
spark.network.crypto.enabled true
spark.io.encryption.enabled true
```

⚠️ **Note** : cette configuration est prête pour un déploiement sécurisé en production. Elle n'est **pas activée en environnement local** mais peut être intégrée directement via `--properties-file` ou `.config()` dans Spark.

---

## 🧩 Version 3 : finale (à venir)

### 🎯 Objectif :
- Envoi des logs dans Kafka (`http-logs`)
- Analyse Spark Streaming lisant Kafka et publiant des alertes dans `alerts`
- Détermination automatique des seuils via Spark batch
- Déploiement automatisé (ex : `docker-compose`)
- Documentation pour l'extensibilité du système

---
