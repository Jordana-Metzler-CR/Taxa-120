import psycopg2
import psycopg2

DB_CONFIG = {
    "host": "192.168.150.226",
    "port": "5432",
    "dbname": "rpa_taxa120_hml",
    "user": "postgres",
    "password": "Hi@M!vLe"
}

def testar_conexao():
    try:
        conn = psycopg2.connect(**DB_CONFIG)

        cursor = conn.cursor()
        cursor.execute("SELECT 1;")

        print("Conectado com sucesso!")
        print(cursor.fetchone())

        cursor.close()
        conn.close()

    except Exception as e:
        print("Erro:")
        print(e)


testar_conexao()