import time
import random
import argparse
from datetime import datetime
from kafka import KafkaProducer
from kafka.errors import KafkaError

# Méthode worker pour créer les logs
def creer_entree_log(ip, url, method, code, size, user_agent="Mozilla/5.0"):
    now = datetime.now().strftime("%d/%b/%Y:%H:%M:%S +0000")
    return f'{ip} - - [{now}] "{method} {url} HTTP/1.1" {code} {size} "-" "{user_agent}"'

def configurer_kafka(broker):
    try:
        producer = KafkaProducer(
            bootstrap_servers=[broker],
            value_serializer=lambda v: v.encode('utf-8'),
            # conf pour la fiabilité
            acks='all',
            retries=3,
            batch_size=16394,
            linger_ms=10
        )
        return producer
    except Exception as e:
        print(f"[ERROR] Impossible de se connecter à Kafka: {e}")
        return None
    
def creationLogs():
    parser = argparse.ArgumentParser(description="Générateur de logs HTTP pour Chaussettes.io")
    parser.add_argument("--rate", type=int, default=1, help="Logs par seconde")
    parser.add_argument("--error-users", type=float, default=10, help="%% utilisateurs qui créent des erreurs")
    parser.add_argument("--error-rate", type=float, default=20, help="%% de logs qui sont des erreurs")
    parser.add_argument("--error-urls", type=float, default=10, help="%% de URLs qui genèrent des erreurs")
    parser.add_argument("--kafka-broker", type=str, default="localhost:9092", help="Adresse du broker Kafka")
    parser.add_argument("--kafka-topic", type=str, default="http-logs", help="Topic Kafka")
    parser.add_argument("--output-mode", choices=["kafka", "console"], default="kafka", help="Mode de sortie")
    
    args = parser.parse_args()
    
    # Validation des params
    if not (0 <= args.error_users <= 100):
        print("[ERROR] error-users doit être un entier entre 0 et 100")
        return
    if not (0 <= args.error_rate <= 100):
        print("[ERROR] error-rate doit être un entier entre 0 et 100")
        return
    if not (0 <= args.error_urls <= 100):
        print("[ERROR] error-urls doit être un entier entre 0 et 100")
        return

    print(f"[INFO] Configuration")
    print(f"  - Taux: {args.rate} logs/sec")
    print(f"  - Utilisateurs d'erreur: {args.error_users}%")
    print(f"  - Taux d'erreur: {args.error_rate}%")
    print(f"  - URLs d'erreur: {args.error_urls}%")
    print(f"  - Mode de sortie: {args.output_mode}")
    
    # Données 
    user_ips = [f"192.168.1.{i}" for i in range(1, 101)]
    urls=[f"/produit/chaussette-{i}" for i in range(1, 51)] + ["/api/commande", "/api/panier", "/api/user/profile", "/", "/contact", "/about", "/admin"]
    methods = ["GET", "POST", "PUT", "DELETE"]
    error_codes = [400, 403, 404, 500, 503]
    success_codes = [200, 201, 204]
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
    ]
    
    # Sélection des users et des URLS avec erreur
    error_users = set(random.sample(user_ips, int(len(user_ips) * args.error_users / 100)))
    error_urls = set(random.sample(urls, int(len(urls) * args.error_urls / 100)))
    
    print(f"[INFO] {len(error_users)} utilisateurs génèrent des erreurs")
    print(f"[INFO] {len(error_urls)} URLs génèrent des erreurs")
    
    # Configurer Kafka si nécessaire
    producer = None
    if args.output_mode == "kafka":
        producer = configurer_kafka(args.kafka_broker)
        if not producer:
            print("[ERROR] Passage vers le mode console")
            args.output_mode = "console"
        else:
            print(f"[INFO] Connecté à Kafka ({args.kafka_broker}, topic: {args.kafka_topic})")

    # Génération des logs
    try:
        log_count = 0
        error_count = 0
        
        while True:
            ip = random.choice(user_ips)
            url = random.choice(urls)
            method = random.choice(methods)
            user_agent = random.choice(user_agents)
            
            # CORRECTION: Logique d'erreur simplifiée et plus claire
            # On génère d'abord si c'est une erreur selon le taux global
            is_error = random.random() < (args.error_rate / 100)
            
            if is_error:
                # Si c'est une erreur, on augmente les chances pour certains users/URLs
                if ip in error_users or url in error_urls:
                    # Les users/URLs "problématiques" ont plus de chances d'erreur
                    code = random.choice(error_codes)
                else:
                    # Même les autres peuvent avoir des erreurs occasionnelles
                    code = random.choice(error_codes)
                error_count += 1
            else:
                code = random.choice(success_codes)
                
            size = random.randint(100, 5000)
            log_entry = creer_entree_log(ip=ip, url=url, method=method, code=code, size=size, user_agent=user_agent)
            
            # Envoie du log
            if args.output_mode == "kafka":
                try:
                    future = producer.send(args.kafka_topic, log_entry)
                except KafkaError as e:
                    print(f"[ERROR] Erreur dans Kafka: {e}")
            
            print(f"[LOG] {log_entry}")
            log_count += 1
            
            if log_count % 100 == 0:
                error_percentage = (error_count / log_count) * 100
                print(f"[INFO] {log_count} logs générés - {error_count} erreurs ({error_percentage:.1f}%)")
            
            time.sleep(1 / args.rate)
                
    except KeyboardInterrupt:
        final_error_percentage = (error_count / log_count) * 100 if log_count > 0 else 0
        print(f"\n[INFO] Arrêt du générateur.")
        print(f"[STATS] {log_count} logs générés - {error_count} erreurs ({final_error_percentage:.1f}%)")
    finally:
        if producer:
            producer.close()

if __name__ == "__main__":
    creationLogs()