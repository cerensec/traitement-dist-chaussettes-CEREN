import json
import os
from datetime import datetime, timedelta
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, regexp_extract, count, expr, when, percentile_approx, stddev, mean, current_timestamp
from pyspark.sql.types import StringType, StructType, StructField, TimestampType
import numpy as np

def creer_session_spark():
    return SparkSession.builder \
        .appName("ChaussettesIO-LogAnalysis") \
        .config("spark.sql.streaming.checkpointLocation", "/tmp/spark-checkpoints") \
        .config("spark.sql.adaptive.enabled", "true") \
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true") \
        .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0") \
        .getOrCreate()

def parse_log_line(df):
    return df.selectExpr("CAST(value AS STRING) as log_line") \
        .withColumn("ip", regexp_extract("log_line", r"^(\S+)", 1)) \
        .withColumn("method", regexp_extract("log_line", r'"(\w+)\s', 1)) \
        .withColumn("url", regexp_extract("log_line", r'"(?:GET|POST|PUT|DELETE|PATCH)\s(\S+)', 1)) \
        .withColumn("status", regexp_extract("log_line", r'" (\d{3}) ', 1).cast("integer")) \
        .withColumn("size", regexp_extract("log_line", r'" \d{3} (\d+)', 1).cast("integer")) \
        .filter(col("ip").isNotNull() & col("url").isNotNull() & col("status").isNotNull()) \
        .withColumn("is_error", expr("status >= 400"))
        
def calculer_seuils_historiques(spark, kafka_broker="kafka:9092", topic="http-logs", duree_minutes=30):
    print(f"[INFO] Analyse des logs historiques des {duree_minutes} dernières minutes")
    
    try:
        # Lecture des données de Kafka depuis le debut
        print("[INFO] Lecture des logs depuis Kafka...")
        kafka_df = spark.read \
            .format("kafka") \
            .option("kafka.bootstrap.servers", kafka_broker) \
            .option("subscribe", topic) \
            .option("startingOffsets", "earliest") \
            .option("endingOffsets", "latest") \
            .load()
            
        if kafka_df.count() == 0:
            print("[WARN] Aucun log trouvé dans Kafka, utilisation des seuils par défaut")
            return {
                "global": 0.1,
                "ip": 0.3,
                "url": 0.5,
                "metadata": {
                    "calculated_at": datetime.now().isoformat(),
                    "total_logs_analyzed": 0,
                    "method": "default_values"
                }
            }
            
        # Parser les logs
        logs_df = parse_log_line(kafka_df)
        logs_df.cache()
        
        total_logs = logs_df.count()
        print(f"[INFO] {total_logs} logs analysés")
        
        if total_logs < 100:
            print("[WARN] Pas assez de données pour calculer des seuils fiables, utilisation des seuils par défaut")
            return {
                "global": 0.1,
                "ip": 0.3,
                "url": 0.5,
                "metadata": {
                    "calculated_at": datetime.now().isoformat(),
                    "total_logs_analyzed": total_logs,
                    "method": "insufficient_data"
                }
            }
        
        # Calcul du seuil global 
        print("[INFO] Calcul du seuil global...")
        total_errors = logs_df.filter(col("is_error")).count()
        global_error_rate = total_errors / total_logs
        
        global_threshold = max(global_error_rate * 0.2, 0.05)
        print(f"[INFO] Taux d'erreur global observé: {global_error_rate:.3f}")
        print(f"[INFO] Seuil global calculé: {global_threshold:.3f}")
        
        # 2. CALCUL DU SEUIL PAR IP
        print("[INFO] Calcul des seuils par IP...")
        ip_stats = logs_df.groupBy("ip") \
            .agg(
                count("*").alias("total"),
                count(when(col("is_error"), 1)).alias("errors")
            ) \
            .filter(col("total") >= 10) \
            .withColumn("error_rate", col("errors") / col("total"))
        
        ip_error_rates = [row['error_rate'] for row in ip_stats.collect()]
        
        if len(ip_error_rates) > 0:
            # 99e percentile des taux d'erreur par IP
            ip_threshold = np.percentile(ip_error_rates, 99)
            ip_threshold = max(ip_threshold, 0.2)  # Au minimum 20%
        else:
            ip_threshold = 0.3
            
        print(f"[INFO] Seuil IP calculé: {ip_threshold:.3f} (basé sur {len(ip_error_rates)} IPs)")
        
        # 3. CALCUL DU SEUIL PAR URL
        print("[INFO] Calcul des seuils par URL...")
        url_stats = logs_df.groupBy("url") \
            .agg(
                count("*").alias("total"),
                count(when(col("is_error"), 1)).alias("errors")
            ) \
            .filter(col("total") >= 5) \
            .withColumn("error_rate", col("errors") / col("total"))
        
        url_error_rates = [row['error_rate'] for row in url_stats.collect()]
        
        if len(url_error_rates) > 0:
            # 99e percentile des taux d'erreur par URL
            url_threshold = np.percentile(url_error_rates, 99)
            url_threshold = max(url_threshold, 0.3)  # Au minimum 30%
        else:
            url_threshold = 0.5
            
        print(f"[INFO] Seuil URL calculé: {url_threshold:.3f} (basé sur {len(url_error_rates)} URLs)")
        
        # 4. STATISTIQUES SUPPLÉMENTAIRES
        print("[INFO] Calcul des statistiques additionnelles...")
        
        # Top IPs avec erreurs
        top_error_ips = ip_stats.filter(col("errors") > 0) \
            .orderBy(col("error_rate").desc()) \
            .limit(5) \
            .collect()
        
        # Top URLs avec erreurs
        top_error_urls = url_stats.filter(col("errors") > 0) \
            .orderBy(col("error_rate").desc()) \
            .limit(5) \
            .collect()
        
        # Construction du résultat
        thresholds = {
            "global": round(global_threshold, 3),
            "ip": round(ip_threshold, 3), 
            "url": round(url_threshold, 3),
            "metadata": {
                "calculated_at": datetime.now().isoformat(),
                "total_logs_analyzed": total_logs,
                "total_errors": total_errors,
                "global_error_rate": round(global_error_rate, 4),
                "method": "percentile_99",
                "analysis_period_minutes": duree_minutes,
                "ips_analyzed": len(ip_error_rates),
                "urls_analyzed": len(url_error_rates),
                "top_error_ips": [
                    {
                        "ip": row['ip'], 
                        "error_rate": round(row['error_rate'], 3),
                        "total_requests": row['total']
                    } 
                    for row in top_error_ips
                ],
                "top_error_urls": [
                    {
                        "url": row['url'], 
                        "error_rate": round(row['error_rate'], 3),
                        "total_requests": row['total']
                    } 
                    for row in top_error_urls
                ]
            }
        }
        
        return thresholds
        
    except Exception as e:
        print(f"[ERROR] Erreur lors du calcul des seuils: {e}")
        return {
            "global": 0.1,
            "ip": 0.3,
            "url": 0.5,
            "metadata": {
                "calculated_at": datetime.now().isoformat(),
                "total_logs_analyzed": 0,
                "method": "error_fallback",
                "error": str(e)
            }
        }
    finally:
        logs_df.unpersist()

def sauvegarder_seuils(seuils, fichier_sortie="/data/seuils.json"):
    """Sauvegarder les seuils calculés dans un fichier JSON"""
    try:
        # Créer le répertoire si nécessaire
        os.makedirs(os.path.dirname(fichier_sortie), exist_ok=True)
        
        with open(fichier_sortie, 'w') as f:
            json.dump(seuils, f, indent=2)
        
        print(f"[SUCCESS] Seuils sauvegardés dans {fichier_sortie}")
        
        # Copie également dans le répertoire app pour le streaming
        app_seuils = "/app/seuils.json"
        with open(app_seuils, 'w') as f:
            json.dump(seuils, f, indent=2)
        
        print(f"[SUCCESS] Seuils copiés dans {app_seuils}")
        
    except Exception as e:
        print(f"[ERROR] Impossible de sauvegarder les seuils: {e}")

def simuler_validation_seuils(spark, seuils, kafka_broker="kafka:9092", topic="http-logs"):
    """
    Simuler l'application des seuils sur les données historiques 
    pour valider qu'ils génèrent environ 1% d'alertes
    """
    print("[INFO] Validation des seuils calculés...")
    
    try:
        # Relire les données
        kafka_df = spark.read \
            .format("kafka") \
            .option("kafka.bootstrap.servers", kafka_broker) \
            .option("subscribe", topic) \
            .option("startingOffsets", "earliest") \
            .option("endingOffsets", "latest") \
            .load()
        
        logs_df = parse_log_line(kafka_df)
        
        # Simuler les alertes avec les nouveaux seuils
        total_logs = logs_df.count()
        if total_logs == 0:
            return
            
        # Test du seuil global
        total_errors = logs_df.filter(col("is_error")).count()
        global_error_rate = total_errors / total_logs
        global_alert = global_error_rate > seuils["global"]
        
        # Test des seuils par IP
        ip_alerts = logs_df.groupBy("ip") \
            .agg(
                count("*").alias("total"),
                count(when(col("is_error"), 1)).alias("errors")
            ) \
            .filter(col("total") >= 5) \
            .withColumn("error_rate", col("errors") / col("total")) \
            .filter(col("error_rate") > seuils["ip"]) \
            .count()
        
        # Test des seuils par URL
        url_alerts = logs_df.groupBy("url") \
            .agg(
                count("*").alias("total"),
                count(when(col("is_error"), 1)).alias("errors")
            ) \
            .filter(col("total") >= 3) \
            .withColumn("error_rate", col("errors") / col("total")) \
            .filter(col("error_rate") > seuils["url"]) \
            .count()
        
        total_alerts = (1 if global_alert else 0) + ip_alerts + url_alerts
        alert_rate = (total_alerts / max(total_logs/100, 1)) * 100  # Approximation
        
        print(f"[VALIDATION] Alertes simulées: {total_alerts}")
        print(f"[VALIDATION] Taux d'alerte estimé: {alert_rate:.2f}%")
        print(f"[VALIDATION] Alerte globale: {'OUI' if global_alert else 'NON'}")
        print(f"[VALIDATION] Alertes IP: {ip_alerts}")
        print(f"[VALIDATION] Alertes URL: {url_alerts}")
        
    except Exception as e:
        print(f"[ERROR] Erreur lors de la validation: {e}")

def calculSeuil():
    """Fonction principale d'analyse batch"""
    print("="*60)
    print("CHAUSSETTES.IO - CALCUL AUTOMATIQUE DES SEUILS")
    print("="*60)
    
    spark = creer_session_spark()
    spark.sparkContext.setLogLevel("WARN")
    
    try:
        # Récupération des paramètres d'environnement
        kafka_broker = os.getenv("KAFKA_BROKER", "kafka:9092")
        topic = os.getenv("KAFKA_TOPIC", "http-logs")
        duree_minutes = int(os.getenv("ANALYSIS_DURATION_MINUTES", "30"))
        
        print(f"[CONFIG] Kafka Broker: {kafka_broker}")
        print(f"[CONFIG] Topic: {topic}")
        print(f"[CONFIG] Durée d'analyse: {duree_minutes} minutes")
        
        # Calcul des seuils
        seuils = calculer_seuils_historiques(spark, kafka_broker, topic, duree_minutes)
        
        # Affichage des résultats
        print("\n" + "="*50)
        print("SEUILS CALCULÉS")
        print("="*50)
        print(f"Seuil global: {seuils['global']}")
        print(f"Seuil IP: {seuils['ip']}")
        print(f"Seuil URL: {seuils['url']}")
        
        if 'metadata' in seuils:
            metadata = seuils['metadata']
            print(f"\nMétadonnées:")
            print(f"- Logs analysés: {metadata.get('total_logs_analyzed', 'N/A')}")
            print(f"- Méthode: {metadata.get('method', 'N/A')}")
            print(f"- Calculé le: {metadata.get('calculated_at', 'N/A')}")
            
            if 'top_error_ips' in metadata and metadata['top_error_ips']:
                print(f"\nTop IPs avec erreurs:")
                for ip_info in metadata['top_error_ips'][:3]:
                    print(f"- {ip_info['ip']}: {ip_info['error_rate']*100:.1f}% ({ip_info['total_requests']} req)")
            
            if 'top_error_urls' in metadata and metadata['top_error_urls']:
                print(f"\nTop URLs avec erreurs:")
                for url_info in metadata['top_error_urls'][:3]:
                    print(f"- {url_info['url']}: {url_info['error_rate']*100:.1f}% ({url_info['total_requests']} req)")
        
        # Sauvegarde
        sauvegarder_seuils(seuils)
        
        # Validation
        simuler_validation_seuils(spark, seuils, kafka_broker, topic)
        
        print("\n[SUCCESS] Analyse terminée avec succès!")
        
    except Exception as e:
        print(f"[ERROR] Erreur fatale: {e}")
        raise
    finally:
        print("[INFO] Arrêt de Spark...")
        spark.stop()

if __name__ == "__main__":
    calculSeuil()