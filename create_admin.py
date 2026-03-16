import psycopg2
from passlib.context import CryptContext
from dotenv import load_dotenv
import os

load_dotenv()

# Configuration
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Connexion à la base
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432'),
    'database': os.getenv('DB_NAME', 'recettes_db'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', ''),
}

try:
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    # Générer le hash pour "admin123"
    hashed_password = pwd_context.hash("admin123")
    
    print("Hash généré pour 'admin123':")
    print(hashed_password)
    print()
    
    # Vérifier si la table users existe
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'users'
        );
    """)
    
    table_exists = cur.fetchone()[0]
    
    if not table_exists:
        print("Création de la table users...")
        cur.execute("""
            CREATE TABLE users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) NOT NULL UNIQUE,
                hashed_password VARCHAR(255) NOT NULL,
                email VARCHAR(255),
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        print("Table users créée ✓")
    
    # Supprimer l'utilisateur admin s'il existe
    cur.execute("DELETE FROM users WHERE username = 'admin'")
    
    # Créer le nouvel utilisateur admin
    cur.execute("""
        INSERT INTO users (username, hashed_password, email)
        VALUES (%s, %s, %s)
    """, ('admin', hashed_password, 'admin@recettes.local'))
    
    conn.commit()
    print("✓ Utilisateur admin créé avec succès!")
    print()
    print("Identifiants:")
    print("  Username: admin")
    print("  Password: admin123")
    print()
    print("Vous pouvez maintenant vous connecter à l'interface d'administration.")
    
    cur.close()
    conn.close()
    
except Exception as e:
    print(f"Erreur: {e}")