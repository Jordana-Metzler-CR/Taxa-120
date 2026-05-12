import psycopg2
from app.classes.log import Log

class DBLogger:
    def __init__(self, host, port, dbname, user, password):
        self.conn_params = {
            "host": host,
            "port": port,
            "dbname": dbname,
            "user": user,
            "password": password
        }
        self._create_table()

    def _get_connection(self):
        return psycopg2.connect(**self.conn_params)

    def _create_table(self):
        conn = self._get_connection()
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS logs_taxa_120 (
                id SERIAL PRIMARY KEY,
                status VARCHAR(50) NOT NULL,
                fluxo TEXT,
                mensagem TEXT,
                horario TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)

        conn.commit()
        cur.close()
        conn.close()

    def registrar(self, log: Log):
        conn = self._get_connection()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO logs_taxa_120 (status, fluxo, mensagem)
            VALUES (%s, %s, %s);
        """, (log.status.value, log.fluxo, log.mensagem))

        conn.commit()
        cur.close()
        conn.close()