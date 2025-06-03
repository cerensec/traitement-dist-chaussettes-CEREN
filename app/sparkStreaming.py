import json
from datetime import datetime
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, regexp_extract, count, expr, lit, concat, current_timestamp, when
from pyspark.sql.types import StringType, StructType, StructField, TimestampType

def charger_thresholds(file_path="seuils.json"):
    default_thresholds = {
        "global" : 0.1,
        "ip": 0.3,
        "url": 0.5
    }
    
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[WARN] Fichier {file_path} pas trouvé, utilisation des seuils par défaut")
        return default_thresholds
    
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
        .withColumn("timestamp", current_timestamp()) \
        .withColumn("ip", regexp_extract("log_line", r"^(\S+)", 1)) \
        .withColumn("method", regexp_extract("log_line", r'"(\w+)\s', 1)) \
        .withColumn("url", regexp_extract("log_line", r'"(?:GET|POST|PUT|DELETE|PATCH)\s(\S+)', 1)) \
        .withColumn("status", regexp_extract("log_line", r'" (\d{3}) ', 1).cast("integer")) \
        .withColumn("size", regexp_extract("log_line", r'" \d{3} (\d+)', 1).cast("integer")) \
        .filter(col("ip").isNotNull() & col("url").isNotNull() & col("status").isNotNull()) \
        .withColumn("is_error", expr("status >= 400"))
        
def processer_batch(batch_df, batch_id, thresholds, spark):
    print(f"[INFO] Traitement du batch {batch_id} - {batch_df.count()} logs")
    
    if batch_df.isEmpty():
        print(f"[INFO] Batch {batch_id} vide, passage au suivant")
        return

    # On cache le df pour éviter les recalculs
    batch_df.cache()
    
    try:
        # Stats du batch
        total_logs = batch_df.count()
        error_logs = batch_df.filter(col("is_error")).count()
        
        print(f"[STATS] Batch {batch_id}: {total_logs} logs et {error_logs} logs d'erreur")
        
        # Métrique globale
        global_error_rate = error_logs / total_logs if total_logs > 0 else 0
        
        # Métrique par ip
        ip_stats = batch_df.groupBy("ip") \
            .agg(
                count("*").alias("total"),
                count(when(col("is_error"), 1)).alias("errors")
            ) \
            .filter(col("total") >= 5) \
            .withColumn("error_rate", col("errors") / col("total")) \
            .filter(col("error_rate") > thresholds["ip"]) \
            .orderBy(col("error_rate").desc())
        
        # Métrique par url
        url_stats = batch_df.groupBy("url") \
            .agg(
                count("*").alias("total"),
                count(when(col("is_error"), 1)).alias("errors")
            ) \
            .filter(col("total") >= 3) \
            .withColumn("error_rate", col("errors") / col("total")) \
            .filter(col("error_rate") > thresholds["url"]) \
            .orderBy(col("error_rate").desc())     
            
        # Génération des alertes
        alerts = []
        alert_timestamp = datetime.now().isoformat()
        
        # Alertes globales
        if global_error_rate > thresholds["global"]:
            alert = {
                "timestamp": alert_timestamp,
                "type": "GLOBAL_ERROR_RATE",
                "severity": "HIGH" if global_error_rate > 0.3 else "MEDIUM",
                "message": f"Taux d'erreur global élevé: {global_error_rate:.2%}",
                "value": global_error_rate,
                "threshold": thresholds["global"],
                "batch_id": batch_id
            }
            alerts.append(json.dumps(alert))  # CORRECTION: json.dumps au lieu de json.dump
            print(f"[ALERTE] Taux d'erreur global : {global_error_rate:.2%}")
            
        # Alertes par ip
        for row in ip_stats.collect():
            alert = {
                "timestamp": alert_timestamp,
                "type": "IP_ERROR_RATE",
                "severity": "HIGH" if row['error_rate'] > 0.5 else "MEDIUM",
                "message": f"IP {row['ip']} avec taux d'erreur élevé: {row['error_rate']:.2%}",
                "ip": row['ip'],
                "value": row['error_rate'],
                "threshold": thresholds["ip"],
                "total_requests": row['total'],
                "batch_id": batch_id
            }
            alerts.append(json.dumps(alert))
            print(f"[ALERTE] IP {row['ip']} avec {row['error_rate']:.2%} d'erreurs ({row['total']} requêtes)")
        
        # Alertes par url
        for row in url_stats.collect():
            alert = {
                "timestamp": alert_timestamp,
                "type": "URL_ERROR_RATE",
                "severity": "HIGH" if row['error_rate'] > 0.7 else "MEDIUM",
                "message": f"URL {row['url']} avec taux d'erreur élevé: {row['error_rate']:.2%}",
                "url": row['url'],
                "value": row['error_rate'],
                "threshold": thresholds["url"],
                "total_requests": row['total'],
                "batch_id": batch_id
            }
            alerts.append(json.dumps(alert))
            print(f"[ALERTE] URL {row['url']} avec {row['error_rate']:.2%} d'erreurs ({row['total']} requêtes)")
        
        # Envoie des alertes vers Kafka
        if alerts:
            print(f"[INFO] Envoi de {len(alerts)} alertes vers Kafka")
            alert_df = spark.createDataFrame([(alert,) for alert in alerts], ["value"])
            
            alert_df.write \
                .format("kafka") \
                .option("kafka.bootstrap.servers", "kafka:9092") \
                .option("topic", "alerts") \
                .mode("append") \
                .save()
            
            print(f"[SUCCESS] {len(alerts)} alertes envoyées")
        else:
            print("[INFO] Aucune alerte générée pour ce batch")
                   
    except Exception as e:
        print(f"[ERROR] Erreur lors du traitement du batch {batch_id}: {e}")
    finally:
        # Libération du cache
        batch_df.unpersist()
        
def analyser_logs():
    print("[INFO] Démarrage de l'analyse de logs en temps réel")
    
    # Chargement des seuils
    thresholds = charger_thresholds()
    print(f"[INFO] Seuils chargés: {thresholds}")
    
    # Création de la session Spark
    spark = creer_session_spark()
    spark.sparkContext.setLogLevel("WARN")  # Réduire les logs Spark
    
    try:
        # Lecture depuis Kafka
        print("[INFO] Connexion à Kafka...")
        kafka_df = spark.readStream \
            .format("kafka") \
            .option("kafka.bootstrap.servers", "kafka:9092") \
            .option("subscribe", "http-logs") \
            .option("startingOffsets", "latest") \
            .option("failOnDataLoss", "false") \
            .load()
        
        # Parsing des logs
        print("[INFO] Configuration du parsing des logs...")
        parsed_logs = parse_log_line(kafka_df)
        
        # Configuration du streaming
        print("[INFO] Démarrage du streaming...")
        query = parsed_logs.writeStream \
            .foreachBatch(lambda batch_df, batch_id: processer_batch(batch_df, batch_id, thresholds, spark)) \
            .outputMode("append") \
            .trigger(processingTime="10 seconds") \
            .option("checkpointLocation", "/tmp/spark-stream-alerts") \
            .start()
        
        print("[INFO] Streaming démarré. Appuyez sur Ctrl+C pour arrêter.")
        query.awaitTermination()
        
    except KeyboardInterrupt:
        print("\n[INFO] Arrêt demandé par l'utilisateur")
    except Exception as e:
        print(f"[ERROR] Erreur fatale: {e}")
    finally:
        print("[INFO] Nettoyage et arrêt de Spark...")
        spark.stop()

if __name__ == "__main__":
    analyser_logs()