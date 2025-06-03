# 🧦 Chaussettes.io - Analyse de Logs en Temps Réel

Application d'analyse de logs HTTP utilisant Apache Spark et Kafka pour détecter les anomalies et générer des alertes en temps réel.

## 🏗 Architecture

- Générateur de logs HTTP simulés
- Pipeline Kafka pour le streaming des logs
- Job Spark Streaming pour l'analyse en temps réel
- Job Spark Batch pour le calcul des seuils
- Système d'alertes basé sur des seuils configurables

## 📋 Prérequis

- Docker et Docker Compose
- ~4GB RAM disponible
- Ports disponibles:
  - 2181 (ZooKeeper)
  - 9092 (Kafka)
  - 8080 (Spark UI)
  - 7077 (Spark Master)

## 🚀 Démarrage rapide

1. Cloner le projet:

```bash
git clone <url-du-repo>
cd traitement-dist-chaussettes-CEREN
```

2. Construire les images:

```bash
make build
```

3. Démarrer l'infrastructure:

```bash
make up
```

4. Vérifier que tout fonctionne:

```bash
make status
```

## 📊 Interfaces Web

- Spark UI: http://localhost:8080

## 🔍 Commandes utiles

### Voir les logs

```bash
make logs                # Tous les services
make logs-generator      # Générateur de logs
make logs-streaming     # Job Spark Streaming
make logs-kafka        # Broker Kafka
```

### Kafka

```bash
make kafka-topics          # Lister les topics
make kafka-consume-logs    # Voir les logs en direct
make kafka-consume-alerts  # Voir les alertes en direct
```

### Gestion des seuils

```bash
make batch-thresholds     # Calculer les nouveaux seuils
```

### Administration

```bash
make stop                 # Arrêter temporairement
make restart             # Redémarrer tous les services
make down                # Arrêter et supprimer les conteneurs
make clean-volumes       # Nettoyer les volumes
```

## 📁 Structure du projet

```
.
├── app/                    # Code source Python
│   ├── log_gen.py         # Générateur de logs
│   ├── sparkSeuilCalcul.py # Calcul des seuils
│   └── sparkStreaming.py  # Analyse temps réel
├── data/                  # Données persistantes
│   └── seuils.json       # Seuils calculés
├── docker-compose.yml     # Configuration Docker
├── Dockerfile.*          # Images Docker
├── Makefile             # Commandes Make
├── requirements.txt     # Dépendances Python
└── seuils.json         # Configuration des seuils
```

## ⚙️ Configuration

Les seuils d'alerte sont configurables dans `seuils.json`:

```json
{
  "global": 0.1,
  "ip": 0.3,
  "url": 0.5
}
```

## 🐛 Dépannage

1. Si Kafka n'est pas disponible:

```bash
make down
make clean-volumes
make up
```

2. Pour redémarrer un service spécifique:

```bash
docker-compose restart <service-name>
```
