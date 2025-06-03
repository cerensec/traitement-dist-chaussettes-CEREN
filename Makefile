# Makefile pour Chaussettes.io - Analyse de logs
.PHONY: help build up down logs clean batch-thresholds status kafka-topics test

# Variables
COMPOSE_FILE = docker-compose.yml
PROJECT_NAME = chaussettes-io

help: ## Afficher cette aide
	@echo "Chaussettes.io - Commandes disponibles:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

build: ## Construire les images Docker
	@echo "🔨 Construction des images Docker..."
	docker-compose -f $(COMPOSE_FILE) build

up: ## Démarrer tous les services
	@echo "🚀 Démarrage de l'infrastructure Chaussettes.io..."
	docker-compose -f $(COMPOSE_FILE) up -d
	@echo "✅ Services démarrés!"
	@echo "📊 Spark UI: http://localhost:8080"
	@echo "🔍 Kafka: localhost:9092"

down: ## Arrêter tous les services
	@echo "🛑 Arrêt des services..."
	docker-compose -f $(COMPOSE_FILE) down

stop: ## Arrêter sans supprimer les volumes
	@echo "⏸️  Arrêt temporaire des services..."
	docker-compose -f $(COMPOSE_FILE) stop

restart: down up ## Redémarrer tous les services

logs: ## Voir les logs de tous les services
	docker-compose -f $(COMPOSE_FILE) logs -f

logs-generator: ## Voir les logs du générateur
	docker-compose -f $(COMPOSE_FILE) logs -f log-generator

logs-streaming: ## Voir les logs du streaming
	docker-compose -f $(COMPOSE_FILE) logs -f spark-streaming

logs-kafka: ## Voir les logs de Kafka
	docker-compose -f $(COMPOSE_FILE) logs -f kafka

status: ## Vérifier le statut des services
	@echo "📋 Statut des services:"
	docker-compose -f $(COMPOSE_FILE) ps

batch-thresholds: ## Lancer le calcul des seuils en batch
	@echo "🧮 Lancement du calcul des seuils..."
	docker-compose -f $(COMPOSE_FILE) --profile batch up spark-batch
	@echo "✅ Calcul terminé! Vérifiez le fichier data/seuils.json"

kafka-topics: ## Lister les topics Kafka
	@echo "📝 Topics Kafka disponibles:"
	docker exec -it $$(docker-compose ps -q kafka) kafka-topics --bootstrap-server localhost:9092 --list

kafka-consume-logs: ## Consommer les logs depuis Kafka
	@echo "👀 Écoute du topic http-logs (Ctrl+C pour arrêter):"
	docker exec -it $$(docker-compose ps -q kafka) kafka-console-consumer --bootstrap-server localhost:9092 --topic http-logs --from-beginning

kafka-consume-alerts: ## Consommer les alertes depuis Kafka
	@echo "🚨 Écoute du topic alerts (Ctrl+C pour arrêter):"
	docker exec -it $$(docker-compose ps -q kafka) kafka-console-consumer --bootstrap-server localhost:9092 --topic alerts --from-beginning

clean-volumes: ## Supprimer les volumes Docker du projet
	@echo "🧹 Suppression des volumes Docker..."
	docker-compose -f $(COMPOSE_FILE) down -v
	@echo "✅ Volumes supprimés !"
