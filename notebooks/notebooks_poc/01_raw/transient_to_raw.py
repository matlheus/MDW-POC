# Databricks notebook source
# DBTITLE 1,Importando bibliotecas
from pyspark.sql.functions import *
from pyspark.sql.types import *
from delta.tables import *

# COMMAND ----------

# DBTITLE 1,Carrega parametros vindos do ADF
dbutils.widgets.text("directory_transient", "")
dbutils.widgets.text("file_transient", "")
dbutils.widgets.text("columns_merge", "")
dbutils.widgets.text("container_target", "")
dbutils.widgets.text("raw_delta_table_name", "")


directory_transient = dbutils.widgets.get("directory_transient")
file_transient = dbutils.widgets.get("file_transient")
columns_merge = dbutils.widgets.get("columns_merge")
container_target = dbutils.widgets.get("container_target")
raw_delta_table_name = dbutils.widgets.get("raw_delta_table_name")

path_transient = "/mnt/transient/" + directory_transient + "/" + file_transient + ".parquet"
raw_delta_table = container_target + "." + raw_delta_table_name

print("diretorio_origem:", directory_transient)
print("arquivo_origem:", file_transient)
print("container_destino:", container_target)
print("chave merge:", columns_merge)
print("diretorio origem formatado:", path_transient)
print("raw delta table:",raw_delta_table)

# COMMAND ----------

print(directory_transient)
print(file_transient)

# COMMAND ----------

# DBTITLE 1,Carrega arquivo da transient e acrescenta novas colunas
origemDF = spark.read.format("parquet").option("header", True).load(path_transient)
origem_novasColunasDF = (origemDF
                         .withColumn("Updated_Date", lit(''))
                         .withColumn("Insert_Date", date_format(current_timestamp() - expr('INTERVAL 3 HOURS'), 'yyyy-MM-dd HH:mm:ss'))
                         .withColumn("Partition_Date", date_format(current_timestamp() - expr('INTERVAL 3 HOURS'), 'yyyyMM').cast("Integer"))
                        )

# COMMAND ----------

# DBTITLE 1,Realização das Cargas Automaticas (Full e Incremental)
t = spark.sql(f"show tables in raw")
table_name = raw_delta_table.split('.')[1]
if len(t.filter(t.tableName==table_name).collect()) == 0 :
    print("create table")
    deltaFile = f'/mnt/raw/{directory_transient}/{table_name}'
    #spark.sql(f"""drop table if exists {raw_delta_table}""")
    origem_novasColunasDF.write.option("overwriteSchema", "true").mode("overwrite").format('delta').partitionBy("Partition_Date").saveAsTable(raw_delta_table, path = deltaFile)
else:
    print("merge")
    colunas, chave_fmt, flag = '', '', False
    arr_chaves = columns_merge.split("|")
    for x in origemDF.columns:
        for chave in arr_chaves:            
            find = colunas.find(x)
            if chave != "" and flag == False:
                chave_fmt = f"{chave_fmt} and src.{chave} = dtn.{chave}"
            elif chave != x and chave != '' and find == -1:  
                colunas += f'dtn.{x} = src.{x} ,'    
        flag = True
    cond_merge = chave_fmt[5:]
    print(colunas)
    origem_novasColunasDF.createOrReplaceTempView('source')
    query_merge = f"""
        MERGE INTO {raw_delta_table} dtn
        USING source src
        on {cond_merge}
        WHEN MATCHED THEN UPDATE SET 
        {colunas} dtn.Updated_Date = date_format(to_utc_timestamp(current_timestamp(), 'GMT+3'),'yyyy-MM-dd HH:mm:ss')
        WHEN NOT MATCHED THEN INSERT *
    """
    print(query_merge)
    spark.sql(query_merge)