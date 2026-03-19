from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
from datetime import timedelta
# modif SUPABASE lignes 8 et 9 mises en commentaires
#import psycopg2
#from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv
from auth import (
    verify_password, 
    get_password_hash, 
    create_access_token, 
    get_current_user,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
# modif SUPABASE ajout ligne ci-dessous
from database import get_db_connection, VIDEO_BASE_URL, get_current_env

# Charger les variables d'environnement
load_dotenv()

app = FastAPI(title="Recettes NFC API")

# Configuration CORS pour permettre les requêtes depuis Flutter
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration de la base de données SUPPRIME A LA BASCULE VERS SUPABASE
#DB_CONFIG = {
#    'host': os.getenv('DB_HOST', 'localhost'),
#    'port': os.getenv('DB_PORT', '5432'),
#    'database': os.getenv('DB_NAME', 'recettes_db'),
#    'user': os.getenv('DB_USER', 'postgres'),
#    'password': os.getenv('DB_PASSWORD', ''),
#}

# ========== MODÈLES PYDANTIC ==========

# Modèles pour les recettes
class Ingredient(BaseModel):
    id: Optional[int] = None
    name: str
    order_index: int

class Step(BaseModel):
    id: Optional[int] = None
    description: str
    order_index: int

class Tag(BaseModel):
    id: int
    name: str

class RecipeBase(BaseModel):
    name: str
    short_description: str
    nfc_tag: str
    video_url: str
    icon_code_point: int

class RecipeCreate(RecipeBase):
    ingredients: List[str]
    steps: List[str]
    tag_ids: List[int]
    materiel_ids: Optional[List[int]] = []

class RecipeUpdate(BaseModel):
    name: Optional[str] = None
    short_description: Optional[str] = None
    nfc_tag: Optional[str] = None
    video_url: Optional[str] = None
    icon_code_point: Optional[int] = None
    ingredients: Optional[List[str]] = None
    steps: Optional[List[str]] = None
    tag_ids: Optional[List[int]] = None
    materiel_ids: Optional[List[int]] = None

class Recipe(RecipeBase):
    id: int
    ingredients: List[Ingredient]
    steps: List[Step]
    tags: List[Tag]
    is_unlocked: bool = False  # ✅ Ajout du champ is_unlocked
    materiel: List[dict] = []

class RecipeList(RecipeBase):
    id: int
    is_unlocked: bool = False
    tags: List[Tag] = []  # ✅ Ajout des tags pour le filtrage
    materiel: List[dict] = []

# Modèles d'authentification
class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    email: str
    password: str
    first_name: str
    last_name: str

class AppLoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user_id: int
    email: str
    first_name: str
    last_name: str

class UserProfile(BaseModel):
    id: int
    email: str
    first_name: str
    last_name: str
    created_at: str

# Modèles pour la gestion des utilisateurs (admin)
class UpdateAppUserRequest(BaseModel):
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None

class UnlockRecipeForUserRequest(BaseModel):
    recipe_ids: List[int]

#Modèles pour la gestion du matériel

class MaterielBase(BaseModel):
    name: str
    description: Optional[str] = None
    category: str
    image_url: Optional[str] = None
    is_active: bool = True

class MaterielCreate(MaterielBase):
    pass

class MaterielUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    is_active: Optional[bool] = None

class Materiel(MaterielBase):
    id: int
    created_at: str
    updated_at: str

class RecipeMaterielBase(BaseModel):
    materiel_id: int
    quantity: int = 1
    is_optional: bool = False
    note: Optional[str] = None

class RecipeMaterielDetail(RecipeMaterielBase):
    id: int
    name: str
    description: Optional[str]
    image_url: Optional[str]
    category: str
    is_owned: bool = False

class UserMaterielBase(BaseModel):
    materiel_id: int
    quantity: int = 1
    note: Optional[str] = None

class UserMaterielDetail(UserMaterielBase):
    id: int
    name: str
    description: Optional[str]
    image_url: Optional[str]
    category: str
    added_at: str

# ========== FONCTIONS DE CONNEXION À LA BASE DE DONNÉES ==========
#
#def get_db_connection():
#    try:
#        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
#        return conn
#    except Exception as e:
#        print(f"Erreur de connexion à la base de données: {e}")
#        raise HTTPException(status_code=500, detail="Erreur de connexion à la base de données")

# ========== ROUTES DE L'API ==========

@app.get("/")
def read_root():
    return {"message": "API Recettes NFC", "version": "1.0.0"}

@app.get("/healthcheck")
def healthcheck():
    """Vérifie que l'API fonctionne et indique l'environnement DB actif"""
    env = get_current_env()
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        return {
            "status": "ok",
            "database": "connectée",
            **env
        }
    except Exception as e:
        return {"status": "error", "detail": str(e), **env}
    finally:
        conn.close()


# ========== ROUTES D'AUTHENTIFICATION ==========

# Connexion admin (interface web)
@app.post("/login")
def login(request: LoginRequest):
    """Connexion administrateur (interface web)"""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT username, hashed_password FROM users WHERE username = %s AND is_active = TRUE",
            (request.username,)
        )
        user = cur.fetchone()
        
        if not user or not verify_password(request.password, user['hashed_password']):
            raise HTTPException(
                status_code=401,
                detail="Nom d'utilisateur ou mot de passe incorrect"
            )
        
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user['username'], "type": "admin"}, 
            expires_delta=access_token_expires
        )
        
        return {
            "access_token": access_token,
            "token_type": "bearer"
        }
    finally:
        conn.close()

# Inscription utilisateur app mobile
@app.post("/app/register", response_model=TokenResponse)
def register_app_user(request: RegisterRequest):
    """Inscription d'un nouvel utilisateur (app mobile)"""
    
    # Validation du mot de passe
    password = request.password
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Le mot de passe doit contenir au moins 8 caractères")
    if not any(c.isupper() for c in password):
        raise HTTPException(status_code=400, detail="Le mot de passe doit contenir au moins une majuscule")
    if not any(c.islower() for c in password):
        raise HTTPException(status_code=400, detail="Le mot de passe doit contenir au moins une minuscule")
    if not any(c.isdigit() for c in password):
        raise HTTPException(status_code=400, detail="Le mot de passe doit contenir au moins un chiffre")
    
    # Validation de l'email (basique)
    if '@' not in request.email or '.' not in request.email:
        raise HTTPException(status_code=400, detail="Email invalide")
    
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        # Vérifier si l'email existe déjà
        cur.execute("SELECT id FROM app_users WHERE email = %s", (request.email.lower(),))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="Cet email est déjà utilisé")
        
        # Créer l'utilisateur
        hashed_password = get_password_hash(password)
        cur.execute("""
            INSERT INTO app_users (email, hashed_password, first_name, last_name)
            VALUES (%s, %s, %s, %s)
            RETURNING id, email, first_name, last_name, created_at
        """, (request.email.lower(), hashed_password, request.first_name, request.last_name))
        
        user = cur.fetchone()
        conn.commit()
        
        # Créer le token
        access_token_expires = timedelta(days=30)  # Token valable 30 jours pour l'app
        access_token = create_access_token(
            data={"sub": str(user['id']), "type": "app_user"}, 
            expires_delta=access_token_expires
        )
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user_id": user['id'],
            "email": user['email'],
            "first_name": user['first_name'],
            "last_name": user['last_name']
        }
    finally:
        conn.close()

# Connexion utilisateur app mobile
@app.post("/app/login", response_model=TokenResponse)
def login_app_user(request: AppLoginRequest):
    """Connexion utilisateur (app mobile)"""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, email, hashed_password, first_name, last_name, is_active
            FROM app_users 
            WHERE email = %s
        """, (request.email.lower(),))
        user = cur.fetchone()
        
        if not user:
            raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
        
        if not user['is_active']:
            raise HTTPException(status_code=401, detail="Compte désactivé")
        
        if not verify_password(request.password, user['hashed_password']):
            raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
        
        # Créer le token
        access_token_expires = timedelta(days=30)
        access_token = create_access_token(
            data={"sub": str(user['id']), "type": "app_user"}, 
            expires_delta=access_token_expires
        )
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user_id": user['id'],
            "email": user['email'],
            "first_name": user['first_name'],
            "last_name": user['last_name']
        }
    finally:
        conn.close()

# Profil utilisateur
@app.get("/app/profile", response_model=UserProfile)
def get_user_profile(current_user: dict = Depends(get_current_user)):
    """Récupérer le profil de l'utilisateur connecté"""
    if not isinstance(current_user, dict) or current_user.get('type') != 'app_user':
        raise HTTPException(status_code=403, detail="Accès refusé")
    
    user_id = current_user.get('user_id')
    
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, email, first_name, last_name, created_at::text
            FROM app_users 
            WHERE id = %s
        """, (user_id,))
        user = cur.fetchone()
        
        if not user:
            raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
        
        return user
    finally:
        conn.close()

# ========== ROUTES PUBLIQUES (App Mobile) ==========

@app.get("/recipes", response_model=List[RecipeList])
def get_recipes(user_id: Optional[int] = None):
    """Récupérer toutes les recettes avec statut de déverrouillage et tags (PUBLIC)"""
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # ✅ 1 seule requête pour les recettes + count ingrédients + count étapes
        if user_id is not None:
            cur.execute("""
                SELECT 
                    r.id, r.name, r.short_description, r.nfc_tag, r.video_url, r.icon_code_point,
                    CASE WHEN ur.user_id IS NOT NULL THEN true ELSE false END as is_unlocked,
                    COUNT(DISTINCT i.id) as ingredients_count,
                    COUNT(DISTINCT s.id) as steps_count
                FROM recipes r
                LEFT JOIN unlocked_recipes ur ON r.id = ur.recipe_id AND ur.user_id = %s
                LEFT JOIN ingredients i ON r.id = i.recipe_id
                LEFT JOIN steps s ON r.id = s.recipe_id
                GROUP BY r.id, r.name, r.short_description, r.nfc_tag, r.video_url, r.icon_code_point, ur.user_id
                ORDER BY r.name
            """, (user_id,))
        else:
            cur.execute("""
                SELECT 
                    r.id, r.name, r.short_description, r.nfc_tag, r.video_url, r.icon_code_point,
                    false as is_unlocked,
                    COUNT(DISTINCT i.id) as ingredients_count,
                    COUNT(DISTINCT s.id) as steps_count
                FROM recipes r
                LEFT JOIN ingredients i ON r.id = i.recipe_id
                LEFT JOIN steps s ON r.id = s.recipe_id
                GROUP BY r.id, r.name, r.short_description, r.nfc_tag, r.video_url, r.icon_code_point
                ORDER BY r.name
            """)

        recipes = cur.fetchall()
        recipe_ids = [r['id'] for r in recipes]

        if not recipe_ids:
            return []

        # ✅ 1 seule requête pour TOUS les tags de toutes les recettes
        cur.execute("""
            SELECT rt.recipe_id, t.id, t.name
            FROM tags t
            JOIN recipe_tags rt ON t.id = rt.tag_id
            WHERE rt.recipe_id = ANY(%s)
        """, (recipe_ids,))
        all_tags = cur.fetchall()

        # ✅ 1 seule requête pour TOUT le matériel de toutes les recettes
        cur.execute("""
            SELECT rm.recipe_id, m.id, m.name, m.description, m.image_url, m.category
            FROM materiel m
            JOIN recipe_materiel rm ON m.id = rm.materiel_id
            WHERE rm.recipe_id = ANY(%s)
            ORDER BY m.category, m.name
        """, (recipe_ids,))
        all_materiel = cur.fetchall()

        # Indexer tags et matériel par recipe_id pour accès O(1)
        tags_by_recipe = {}
        for tag in all_tags:
            rid = tag['recipe_id']
            if rid not in tags_by_recipe:
                tags_by_recipe[rid] = []
            tags_by_recipe[rid].append({'id': tag['id'], 'name': tag['name']})

        materiel_by_recipe = {}
        for mat in all_materiel:
            rid = mat['recipe_id']
            if rid not in materiel_by_recipe:
                materiel_by_recipe[rid] = []
            materiel_by_recipe[rid].append({
                'id': mat['id'], 'name': mat['name'],
                'description': mat['description'],
                'image_url': mat['image_url'], 'category': mat['category']
            })

        result = []
        for recipe in recipes:
            rid = recipe['id']
            result.append({
                **recipe,
                'tags': tags_by_recipe.get(rid, []),
                'materiel': materiel_by_recipe.get(rid, []),
            })

        return result
    finally:
        conn.close()

@app.get("/recipes/{recipe_id}", response_model=Recipe)
def get_recipe(recipe_id: int, user_id: Optional[int] = None):
    """Récupérer une recette par son ID avec statut de déverrouillage (PUBLIC)"""
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # ✅ Recette + statut déverrouillage en une seule requête
        if user_id is not None:
            cur.execute("""
                SELECT r.*,
                    CASE WHEN ur.user_id IS NOT NULL THEN true ELSE false END as is_unlocked
                FROM recipes r
                LEFT JOIN unlocked_recipes ur ON r.id = ur.recipe_id AND ur.user_id = %s
                WHERE r.id = %s
            """, (user_id, recipe_id))
        else:
            cur.execute("SELECT *, false as is_unlocked FROM recipes WHERE id = %s", (recipe_id,))

        recipe = cur.fetchone()
        if not recipe:
            raise HTTPException(status_code=404, detail="Recette non trouvée")

        cur.execute(
            "SELECT id, name, order_index FROM ingredients WHERE recipe_id = %s ORDER BY order_index",
            (recipe_id,)
        )
        ingredients = cur.fetchall()

        cur.execute(
            "SELECT id, description, order_index FROM steps WHERE recipe_id = %s ORDER BY order_index",
            (recipe_id,)
        )
        steps = cur.fetchall()

        cur.execute("""
            SELECT t.id, t.name FROM tags t
            JOIN recipe_tags rt ON t.id = rt.tag_id
            WHERE rt.recipe_id = %s
        """, (recipe_id,))
        tags = cur.fetchall()

        cur.execute("""
            SELECT m.id, m.name, m.description, m.image_url, m.category
            FROM materiel m
            JOIN recipe_materiel rm ON m.id = rm.materiel_id
            WHERE rm.recipe_id = %s AND m.is_active = TRUE
            ORDER BY m.category, m.name
        """, (recipe_id,))
        materiel = cur.fetchall() or []

        return {
            **recipe,
            'ingredients': ingredients,
            'steps': steps,
            'tags': tags,
            'materiel': materiel,
        }
    finally:
        conn.close()

class UnlockRequest(BaseModel):
    nfc_tag: str
    user_id: int

@app.post("/unlock")
def unlock_recipe(unlock_data: UnlockRequest):
    """Déverrouiller une recette via tag NFC (PUBLIC)"""
    nfc_tag_cleaned = unlock_data.nfc_tag.strip().lower()
    user_id = unlock_data.user_id

    conn = get_db_connection()
    try:
        cur = conn.cursor()

        cur.execute("SELECT id FROM app_users WHERE id = %s", (user_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

        cur.execute(
            "SELECT id, name FROM recipes WHERE LOWER(TRIM(nfc_tag)) = %s",
            (nfc_tag_cleaned,)
        )
        recipe = cur.fetchone()

        if not recipe:
            raise HTTPException(
                status_code=404,
                detail=f"Ce tag NFC ne correspond à aucune recette"
            )

        # ✅ INSERT ON CONFLICT — évite la double vérification SELECT + INSERT
        cur.execute("""
            INSERT INTO unlocked_recipes (user_id, recipe_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
        """, (user_id, recipe['id']))

        already_unlocked = cur.rowcount == 0
        conn.commit()

        return {
            "message": f"Recette '{recipe['name']}' {'était déjà déverrouillée' if already_unlocked else 'déverrouillée avec succès !'}",
            "recipe_id": recipe['id'],
            "already_unlocked": already_unlocked
        }
    finally:
        conn.close()

@app.get("/tags")
def get_tags():
    """Récupérer tous les tags disponibles (PUBLIC)"""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM tags ORDER BY name")
        tags = cur.fetchall()
        return tags
    finally:
        conn.close()

# ========== ROUTES PROTÉGÉES (Admin) ==========

@app.post("/recipes", response_model=Recipe)
def create_recipe(recipe: RecipeCreate, current_user: str = Depends(get_current_user)):
    """Créer une nouvelle recette (PROTÉGÉ)"""
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        cur.execute("SELECT id FROM recipes WHERE nfc_tag = %s", (recipe.nfc_tag,))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="Ce tag NFC est déjà utilisé")

        cur.execute("""
            INSERT INTO recipes (name, short_description, nfc_tag, video_url, icon_code_point)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
        """, (recipe.name, recipe.short_description, recipe.nfc_tag, recipe.video_url, recipe.icon_code_point))

        recipe_id = cur.fetchone()['id']

        # ✅ executemany — 1 seul appel réseau par type
        if recipe.ingredients:
            cur.executemany(
                "INSERT INTO ingredients (recipe_id, name, order_index) VALUES (%s, %s, %s)",
                [(recipe_id, name, i) for i, name in enumerate(recipe.ingredients)]
            )
        if recipe.steps:
            cur.executemany(
                "INSERT INTO steps (recipe_id, description, order_index) VALUES (%s, %s, %s)",
                [(recipe_id, desc, i) for i, desc in enumerate(recipe.steps)]
            )
        if recipe.tag_ids:
            cur.executemany(
                "INSERT INTO recipe_tags (recipe_id, tag_id) VALUES (%s, %s)",
                [(recipe_id, tag_id) for tag_id in recipe.tag_ids]
            )
        if recipe.materiel_ids:
            cur.executemany(
                "INSERT INTO recipe_materiel (recipe_id, materiel_id) VALUES (%s, %s)",
                [(recipe_id, mat_id) for mat_id in recipe.materiel_ids]
            )

        conn.commit()
        return get_recipe(recipe_id)
    finally:
        conn.close()

@app.put("/recipes/{recipe_id}", response_model=Recipe)
def update_recipe(recipe_id: int, recipe: RecipeUpdate, current_user: str = Depends(get_current_user)):
    """Mettre à jour une recette (PROTÉGÉ)"""
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        cur.execute("SELECT id FROM recipes WHERE id = %s", (recipe_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Recette non trouvée")

        update_fields = []
        update_values = []

        if recipe.name is not None:
            update_fields.append("name = %s")
            update_values.append(recipe.name)
        if recipe.short_description is not None:
            update_fields.append("short_description = %s")
            update_values.append(recipe.short_description)
        if recipe.nfc_tag is not None:
            cur.execute("SELECT id FROM recipes WHERE nfc_tag = %s AND id != %s", (recipe.nfc_tag, recipe_id))
            if cur.fetchone():
                raise HTTPException(status_code=400, detail="Ce tag NFC est déjà utilisé")
            update_fields.append("nfc_tag = %s")
            update_values.append(recipe.nfc_tag)
        if recipe.video_url is not None:
            update_fields.append("video_url = %s")
            update_values.append(recipe.video_url)
        if recipe.icon_code_point is not None:
            update_fields.append("icon_code_point = %s")
            update_values.append(recipe.icon_code_point)

        if update_fields:
            update_values.append(recipe_id)
            cur.execute(f"UPDATE recipes SET {', '.join(update_fields)} WHERE id = %s", update_values)

        # ✅ executemany pour tous les sous-éléments
        if recipe.ingredients is not None:
            cur.execute("DELETE FROM ingredients WHERE recipe_id = %s", (recipe_id,))
            if recipe.ingredients:
                cur.executemany(
                    "INSERT INTO ingredients (recipe_id, name, order_index) VALUES (%s, %s, %s)",
                    [(recipe_id, name, i) for i, name in enumerate(recipe.ingredients)]
                )
        if recipe.steps is not None:
            cur.execute("DELETE FROM steps WHERE recipe_id = %s", (recipe_id,))
            if recipe.steps:
                cur.executemany(
                    "INSERT INTO steps (recipe_id, description, order_index) VALUES (%s, %s, %s)",
                    [(recipe_id, desc, i) for i, desc in enumerate(recipe.steps)]
                )
        if recipe.tag_ids is not None:
            cur.execute("DELETE FROM recipe_tags WHERE recipe_id = %s", (recipe_id,))
            if recipe.tag_ids:
                cur.executemany(
                    "INSERT INTO recipe_tags (recipe_id, tag_id) VALUES (%s, %s)",
                    [(recipe_id, tag_id) for tag_id in recipe.tag_ids]
                )
        if recipe.materiel_ids is not None:
            cur.execute("DELETE FROM recipe_materiel WHERE recipe_id = %s", (recipe_id,))
            if recipe.materiel_ids:
                cur.executemany(
                    "INSERT INTO recipe_materiel (recipe_id, materiel_id) VALUES (%s, %s)",
                    [(recipe_id, mat_id) for mat_id in recipe.materiel_ids]
                )

        conn.commit()
        return get_recipe(recipe_id)
    finally:
        conn.close()

@app.delete("/recipes/{recipe_id}")
def delete_recipe(recipe_id: int, current_user: str = Depends(get_current_user)):
    """Supprimer une recette (PROTÉGÉ)"""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        # Vérifier que la recette existe
        cur.execute("SELECT id FROM recipes WHERE id = %s", (recipe_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Recette non trouvée")
        
        # Supprimer la recette (les contraintes CASCADE supprimeront les dépendances)
        cur.execute("DELETE FROM recipes WHERE id = %s", (recipe_id,))
        conn.commit()
        
        return {"message": "Recette supprimée avec succès"}
    finally:
        conn.close()


# ========== ROUTES GESTION UTILISATEURS (Admin uniquement) ==========

@app.get("/admin/users")
def get_all_app_users(current_user: str = Depends(get_current_user)):
    """Récupérer tous les utilisateurs de l'app (admin)"""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT u.id, u.email, u.first_name, u.last_name, u.is_active, u.created_at,
                   COUNT(DISTINCT ur.recipe_id) as unlocked_count
            FROM app_users u
            LEFT JOIN unlocked_recipes ur ON u.id = ur.user_id
            GROUP BY u.id, u.email, u.first_name, u.last_name, u.is_active, u.created_at
            ORDER BY u.created_at DESC
        """)
        users = cur.fetchall()
        return users
    finally:
        conn.close()

@app.get("/admin/users/{user_id}")
def get_app_user_detail(user_id: int, current_user: str = Depends(get_current_user)):
    """Récupérer les détails d'un utilisateur avec ses recettes débloquées"""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        # Info utilisateur
        cur.execute("""
            SELECT id, email, first_name, last_name, is_active, created_at
            FROM app_users
            WHERE id = %s
        """, (user_id,))
        user = cur.fetchone()
        
        if not user:
            raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
        
        # Recettes débloquées
        cur.execute("""
            SELECT r.id, r.name, ur.unlocked_at
            FROM unlocked_recipes ur
            JOIN recipes r ON ur.recipe_id = r.id
            WHERE ur.user_id = %s
            ORDER BY ur.unlocked_at DESC
        """, (user_id,))
        unlocked_recipes = cur.fetchall()
        
        return {
            **user,
            'unlocked_recipes': unlocked_recipes
        }
    finally:
        conn.close()

@app.put("/admin/users/{user_id}")
def update_app_user(user_id: int, user: UpdateAppUserRequest, current_user: str = Depends(get_current_user)):
    """Mettre à jour un utilisateur (admin)"""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        # Vérifier que l'utilisateur existe
        cur.execute("SELECT id FROM app_users WHERE id = %s", (user_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
        
        # Construire la requête de mise à jour
        update_fields = []
        update_values = []
        
        if user.email is not None:
            # Vérifier que l'email n'est pas déjà utilisé
            cur.execute("SELECT id FROM app_users WHERE email = %s AND id != %s", (user.email.lower(), user_id))
            if cur.fetchone():
                raise HTTPException(status_code=400, detail="Cet email est déjà utilisé")
            update_fields.append("email = %s")
            update_values.append(user.email.lower())
        
        if user.first_name is not None:
            update_fields.append("first_name = %s")
            update_values.append(user.first_name)
        
        if user.last_name is not None:
            update_fields.append("last_name = %s")
            update_values.append(user.last_name)
        
        if user.password is not None:
            # Valider le mot de passe
            if len(user.password) < 8:
                raise HTTPException(status_code=400, detail="Le mot de passe doit contenir au moins 8 caractères")
            update_fields.append("hashed_password = %s")
            update_values.append(get_password_hash(user.password))
        
        if user.is_active is not None:
            update_fields.append("is_active = %s")
            update_values.append(user.is_active)
        
        if update_fields:
            update_values.append(user_id)
            query = f"UPDATE app_users SET {', '.join(update_fields)} WHERE id = %s"
            cur.execute(query, update_values)
            conn.commit()
        
        return {"message": "Utilisateur mis à jour avec succès"}
    finally:
        conn.close()

@app.delete("/admin/users/{user_id}")
def delete_app_user(user_id: int, current_user: str = Depends(get_current_user)):
    """Supprimer un utilisateur (admin)"""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        # Vérifier que l'utilisateur existe
        cur.execute("SELECT id FROM app_users WHERE id = %s", (user_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
        
        # Supprimer l'utilisateur (CASCADE supprimera les unlocked_recipes)
        cur.execute("DELETE FROM app_users WHERE id = %s", (user_id,))
        conn.commit()
        
        return {"message": "Utilisateur supprimé avec succès"}
    finally:
        conn.close()

@app.post("/admin/users/{user_id}/unlock-recipes")
def unlock_recipes_for_user(user_id: int, request: UnlockRecipeForUserRequest, current_user: str = Depends(get_current_user)):
    """Débloquer des recettes pour un utilisateur (admin)"""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        # Vérifier que l'utilisateur existe
        cur.execute("SELECT id FROM app_users WHERE id = %s", (user_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
        
        added_count = 0
        for recipe_id in request.recipe_ids:
            # Vérifier que la recette existe
            cur.execute("SELECT id FROM recipes WHERE id = %s", (recipe_id,))
            if cur.fetchone():
                # Vérifier si pas déjà débloquée
                cur.execute("SELECT id FROM unlocked_recipes WHERE user_id = %s AND recipe_id = %s", (user_id, recipe_id))
                if not cur.fetchone():
                    cur.execute("INSERT INTO unlocked_recipes (user_id, recipe_id) VALUES (%s, %s)", (user_id, recipe_id))
                    added_count += 1
        
        conn.commit()
        return {"message": f"{added_count} recette(s) débloquée(s) pour l'utilisateur"}
    finally:
        conn.close()

@app.delete("/admin/users/{user_id}/recipes/{recipe_id}")
def lock_recipe_for_user(user_id: int, recipe_id: int, current_user: str = Depends(get_current_user)):
    """Verrouiller une recette pour un utilisateur (admin)"""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        cur.execute("DELETE FROM unlocked_recipes WHERE user_id = %s AND recipe_id = %s", (user_id, recipe_id))
        conn.commit()
        
        return {"message": "Recette verrouillée pour l'utilisateur"}
    finally:
        conn.close()

# Servir les fichiers statiques (interface admin)
admin_dir = os.path.join(os.path.dirname(__file__), "admin")
if os.path.exists(admin_dir):
    app.mount("/interface", StaticFiles(directory=admin_dir, html=True), name="admin")

# ========== ROUTES PUBLIQUES - MATÉRIEL ==========

@app.get("/materiel", response_model=List[Materiel])
def get_materiel():
    """Récupérer tout le matériel actif (PUBLIC)"""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, name, description, category, image_url, is_active,
                   created_at::text, updated_at::text
            FROM materiel
            WHERE is_active = TRUE
            ORDER BY category, name
        """)
        materiel = cur.fetchall()
        return materiel
    finally:
        conn.close()

@app.get("/materiel/categories", response_model=List[str])
def get_materiel_categories():
    """Récupérer toutes les catégories de matériel (PUBLIC)"""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT category 
            FROM materiel 
            WHERE is_active = TRUE 
              AND category IS NOT NULL 
              AND category != ''
            ORDER BY category
        """)
        results = cur.fetchall()
        # Extraire juste les valeurs de catégorie
        categories = [row['category'] for row in results]
        return categories
    finally:
        conn.close()

@app.get("/materiel/{materiel_id}", response_model=Materiel)
def get_materiel_by_id(materiel_id: int):
    """Récupérer un matériel par son ID (PUBLIC)"""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, name, description, category, image_url, is_active,
                   created_at::text, updated_at::text
            FROM materiel
            WHERE id = %s
        """, (materiel_id,))
        materiel = cur.fetchone()
        
        if not materiel:
            raise HTTPException(status_code=404, detail="Matériel non trouvé")
        
        return materiel
    finally:
        conn.close()

@app.get("/recipes/{recipe_id}/materiel", response_model=List[RecipeMaterielDetail])
def get_recipe_materiel(recipe_id: int, user_id: Optional[int] = None):
    """Récupérer le matériel nécessaire pour une recette avec info de possession si user_id fourni (PUBLIC)"""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        # Vérifier que la recette existe
        cur.execute("SELECT id FROM recipes WHERE id = %s", (recipe_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Recette non trouvée")
        
        # Récupérer le matériel avec info de possession si user_id est fourni
        if user_id is not None:
            cur.execute("""
                SELECT 
                    rm.id,
                    rm.materiel_id,
                    rm.quantity,
                    rm.is_optional,
                    rm.note,
                    m.name,
                    m.description,
                    m.image_url,
                    m.category,
                    CASE WHEN um.materiel_id IS NOT NULL THEN TRUE ELSE FALSE END as is_owned
                FROM recipe_materiel rm
                INNER JOIN materiel m ON rm.materiel_id = m.id
                LEFT JOIN user_materiel um ON rm.materiel_id = um.materiel_id AND um.user_id = %s
                WHERE rm.recipe_id = %s AND m.is_active = TRUE
                ORDER BY rm.is_optional ASC, m.name ASC
            """, (user_id, recipe_id))
        else:
            cur.execute("""
                SELECT 
                    rm.id,
                    rm.materiel_id,
                    rm.quantity,
                    rm.is_optional,
                    rm.note,
                    m.name,
                    m.description,
                    m.image_url,
                    m.category,
                    FALSE as is_owned
                FROM recipe_materiel rm
                INNER JOIN materiel m ON rm.materiel_id = m.id
                WHERE rm.recipe_id = %s AND m.is_active = TRUE
                ORDER BY rm.is_optional ASC, m.name ASC
            """, (recipe_id,))
        
        materiel = cur.fetchall()
        return materiel
    finally:
        conn.close()



# ========== ROUTES ADMIN - MATÉRIEL ==========

@app.get("/admin/materiel", response_model=List[Materiel])
def get_all_materiel_admin(current_user: str = Depends(get_current_user)):
    """Récupérer tout le matériel pour l'admin (inclut les inactifs)"""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, name, description, category, image_url, is_active,
                   created_at::text, updated_at::text
            FROM materiel
            ORDER BY category, name
        """)
        materiel = cur.fetchall()
        return materiel
    finally:
        conn.close()



@app.post("/admin/materiel", response_model=Materiel)
def create_materiel(materiel: MaterielCreate, current_user: str = Depends(get_current_user)):
    """Créer un nouveau matériel (PROTÉGÉ - Admin)"""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        # Vérifier que le nom n'existe pas déjà
        cur.execute("SELECT id FROM materiel WHERE name = %s", (materiel.name,))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="Ce matériel existe déjà")
        
        # Insérer le matériel
        cur.execute("""
            INSERT INTO materiel (name, description, category, image_url, is_active)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, name, description, category, image_url, is_active,
                      created_at::text, updated_at::text
        """, (materiel.name, materiel.description, materiel.category, 
              materiel.image_url, materiel.is_active))
        
        new_materiel = cur.fetchone()
        conn.commit()
        
        return new_materiel
    finally:
        conn.close()

@app.put("/admin/materiel/{materiel_id}", response_model=Materiel)
def update_materiel(materiel_id: int, materiel: MaterielUpdate, current_user: str = Depends(get_current_user)):
    """Mettre à jour un matériel (PROTÉGÉ - Admin)"""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        # Vérifier que le matériel existe
        cur.execute("SELECT id FROM materiel WHERE id = %s", (materiel_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Matériel non trouvé")
        
        # Construire la requête de mise à jour
        update_fields = []
        update_values = []
        
        if materiel.name is not None:
            # Vérifier que le nom n'est pas déjà utilisé
            cur.execute("SELECT id FROM materiel WHERE name = %s AND id != %s", (materiel.name, materiel_id))
            if cur.fetchone():
                raise HTTPException(status_code=400, detail="Ce nom est déjà utilisé")
            update_fields.append("name = %s")
            update_values.append(materiel.name)
        
        if materiel.description is not None:
            update_fields.append("description = %s")
            update_values.append(materiel.description)
        
        if materiel.category is not None:
            update_fields.append("category = %s")
            update_values.append(materiel.category)
        
        if materiel.image_url is not None:
            update_fields.append("image_url = %s")
            update_values.append(materiel.image_url)
        
        if materiel.is_active is not None:
            update_fields.append("is_active = %s")
            update_values.append(materiel.is_active)
        
        if update_fields:
            update_values.append(materiel_id)
            query = f"UPDATE materiel SET {', '.join(update_fields)}, updated_at = CURRENT_TIMESTAMP WHERE id = %s"
            cur.execute(query, update_values)
            conn.commit()
        
        # Récupérer le matériel mis à jour
        cur.execute("""
            SELECT id, name, description, category, image_url, is_active,
                   created_at::text, updated_at::text
            FROM materiel
            WHERE id = %s
        """, (materiel_id,))
        
        return cur.fetchone()
    finally:
        conn.close()

@app.delete("/admin/materiel/{materiel_id}")
def delete_materiel(materiel_id: int, current_user: str = Depends(get_current_user)):
    """Supprimer un matériel (PROTÉGÉ - Admin)"""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        # Vérifier que le matériel existe
        cur.execute("SELECT id FROM materiel WHERE id = %s", (materiel_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Matériel non trouvé")
        
        # Vérifier que le matériel n'est pas utilisé dans des recettes
        cur.execute("SELECT COUNT(*) as count FROM recipe_materiel WHERE materiel_id = %s", (materiel_id,))
        result = cur.fetchone()
        if result['count'] > 0:
            raise HTTPException(
                status_code=409, 
                detail="Impossible de supprimer ce matériel car il est utilisé dans des recettes"
            )
        
        # Supprimer le matériel
        cur.execute("DELETE FROM materiel WHERE id = %s", (materiel_id,))
        conn.commit()
        
        return {"message": "Matériel supprimé avec succès"}
    finally:
        conn.close()

@app.post("/admin/recipes/{recipe_id}/materiel")
def add_materiel_to_recipe(
    recipe_id: int, 
    materiel_list: List[RecipeMaterielBase],
    current_user: str = Depends(get_current_user)
):
    """Associer du matériel à une recette (remplace tous les matériels existants) (PROTÉGÉ - Admin)"""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        # Vérifier que la recette existe
        cur.execute("SELECT id FROM recipes WHERE id = %s", (recipe_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Recette non trouvée")
        
        # Supprimer les associations existantes
        cur.execute("DELETE FROM recipe_materiel WHERE recipe_id = %s", (recipe_id,))
        
        # Ajouter les nouvelles associations
        added_count = 0
        for index, item in enumerate(materiel_list):
            # Vérifier que le matériel existe
            cur.execute("SELECT id FROM materiel WHERE id = %s", (item.materiel_id,))
            if cur.fetchone():
                cur.execute("""
                    INSERT INTO recipe_materiel 
                    (recipe_id, materiel_id, quantity, is_optional, note, display_order)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (recipe_id, item.materiel_id, item.quantity, item.is_optional, item.note, index))
                added_count += 1
        
        conn.commit()
        
        return {"message": f"{added_count} matériel(s) associé(s) à la recette"}
    finally:
        conn.close()

@app.delete("/admin/recipes/{recipe_id}/materiel/{materiel_id}")
def remove_materiel_from_recipe(
    recipe_id: int, 
    materiel_id: int,
    current_user: str = Depends(get_current_user)
):
    """Retirer un matériel d'une recette (PROTÉGÉ - Admin)"""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        cur.execute(
            "DELETE FROM recipe_materiel WHERE recipe_id = %s AND materiel_id = %s",
            (recipe_id, materiel_id)
        )
        conn.commit()
        
        return {"message": "Matériel retiré de la recette"}
    finally:
        conn.close()

# ========== ROUTES UTILISATEUR - MATÉRIEL ==========

@app.get("/users/{user_id}/materiel", response_model=List[UserMaterielDetail])
def get_user_materiel(user_id: int, current_user: dict = Depends(get_current_user)):
    """Récupérer le matériel possédé par un utilisateur - FORMAT ADMIN (PROTÉGÉ)"""
    # Vérifier que l'utilisateur demande son propre matériel ou est admin
    if isinstance(current_user, dict) and current_user.get('type') == 'app_user' and current_user.get('user_id') != user_id:
        raise HTTPException(status_code=403, detail="Accès refusé")
    
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        # Vérifier que l'utilisateur existe
        cur.execute("SELECT id FROM app_users WHERE id = %s", (user_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
        
        # Récupérer le matériel de l'utilisateur
        cur.execute("""
            SELECT 
                um.id,
                um.user_id,
                um.materiel_id,
                um.quantity,
                um.note,
                um.added_at::text,
                m.name,
                m.description,
                m.image_url,
                m.category,
                m.is_active,
                m.created_at::text,
                m.updated_at::text
            FROM user_materiel um
            INNER JOIN materiel m ON um.materiel_id = m.id
            WHERE um.user_id = %s AND m.is_active = TRUE
            ORDER BY m.category, m.name
        """, (user_id,))
        
        results = cur.fetchall()
        
        # FORMAT ADMIN: Champs au premier niveau (format plat)
        materiel_list = []
        for row in results:
            materiel_item = {
                "id": row["id"],
                "user_id": row["user_id"],
                "materiel_id": row["materiel_id"],
                "quantity": row["quantity"],
                "note": row["note"],
                "added_at": row["added_at"],
                # Champs directement au premier niveau (pour admin)
                "name": row["name"],
                "description": row["description"],
                "image_url": row["image_url"],
                "category": row["category"],
                "is_active": row["is_active"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"]
            }
            materiel_list.append(materiel_item)
        
        return materiel_list
    finally:
        conn.close()

@app.get("/users/{user_id}/materiel/app")
def get_user_materiel_app(user_id: int, current_user: dict = Depends(get_current_user)):
    """Récupérer le matériel possédé par un utilisateur - FORMAT FLUTTER (PROTÉGÉ)"""
    # Vérifier que l'utilisateur demande son propre matériel ou est admin
    if isinstance(current_user, dict) and current_user.get('type') == 'app_user' and current_user.get('user_id') != user_id:
        raise HTTPException(status_code=403, detail="Accès refusé")
    
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        # Vérifier que l'utilisateur existe
        cur.execute("SELECT id FROM app_users WHERE id = %s", (user_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
        
        # Récupérer le matériel de l'utilisateur
        cur.execute("""
            SELECT 
                um.id,
                um.user_id,
                um.materiel_id,
                um.quantity,
                um.note,
                um.added_at::text,
                m.name,
                m.description,
                m.image_url,
                m.category,
                m.is_active,
                m.created_at::text,
                m.updated_at::text
            FROM user_materiel um
            INNER JOIN materiel m ON um.materiel_id = m.id
            WHERE um.user_id = %s AND m.is_active = TRUE
            ORDER BY m.category, m.name
        """, (user_id,))
        
        results = cur.fetchall()
        
        # FORMAT FLUTTER: Objet imbriqué
        materiel_list = []
        for row in results:
            materiel_item = {
                "id": row["id"],
                "user_id": row["user_id"],
                "materiel_id": row["materiel_id"],
                "quantity": row["quantity"],
                "note": row["note"],
                "added_at": row["added_at"],
                # Objet imbriqué (pour Flutter)
                "materiel": {
                    "id": row["materiel_id"],
                    "name": row["name"],
                    "description": row["description"],
                    "image_url": row["image_url"],
                    "category": row["category"],
                    "is_active": row["is_active"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"]
                }
            }
            materiel_list.append(materiel_item)
        
        return materiel_list
    finally:
        conn.close()

@app.post("/users/{user_id}/materiel")
def add_user_materiel(
    user_id: int,
    materiel: UserMaterielBase,
    current_user: dict = Depends(get_current_user)
):
    """Ajouter du matériel possédé par un utilisateur (PROTÉGÉ)"""
    # Vérifier que l'utilisateur ajoute son propre matériel ou est admin
    if isinstance(current_user, dict) and current_user.get('type') == 'app_user' and current_user.get('user_id') != user_id:
        raise HTTPException(status_code=403, detail="Accès refusé")
    
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        # Vérifier que l'utilisateur existe
        cur.execute("SELECT id FROM app_users WHERE id = %s", (user_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
        
        # Vérifier que le matériel existe
        cur.execute("SELECT id FROM materiel WHERE id = %s", (materiel.materiel_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Matériel non trouvé")
        
        # Vérifier que l'utilisateur ne possède pas déjà ce matériel
        cur.execute(
            "SELECT id FROM user_materiel WHERE user_id = %s AND materiel_id = %s",
            (user_id, materiel.materiel_id)
        )
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Ce matériel est déjà dans votre liste")
        
        # Ajouter le matériel
        cur.execute("""
            INSERT INTO user_materiel (user_id, materiel_id, quantity, note)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (user_id, materiel.materiel_id, materiel.quantity, materiel.note))
        
        new_id = cur.fetchone()['id']
        conn.commit()
        
        # Récupérer l'entrée complète avec les détails du matériel pour le retour
        cur.execute("""
            SELECT 
                um.id,
                um.user_id,
                um.materiel_id,
                um.quantity,
                um.note,
                um.added_at::text,
                m.name,
                m.description,
                m.image_url,
                m.category,
                m.is_active,
                m.created_at::text,
                m.updated_at::text
            FROM user_materiel um
            INNER JOIN materiel m ON um.materiel_id = m.id
            WHERE um.id = %s
        """, (new_id,))
        
        result = cur.fetchone()
        
        # Formater la réponse pour correspondre au format attendu par Flutter
        return {
            "id": result["id"],
            "user_id": result["user_id"],
            "materiel_id": result["materiel_id"],
            "quantity": result["quantity"],
            "note": result["note"],
            "added_at": result["added_at"],
            "materiel": {
                "id": result["materiel_id"],
                "name": result["name"],
                "description": result["description"],
                "image_url": result["image_url"],
                "category": result["category"],
                "is_active": result["is_active"],
                "created_at": result["created_at"],
                "updated_at": result["updated_at"]
            }
        }
    finally:
        conn.close()


@app.put("/users/{user_id}/materiel/{user_materiel_id}")
def update_user_materiel(
    user_id: int,
    user_materiel_id: int,
    materiel: UserMaterielBase,
    current_user: dict = Depends(get_current_user)
):
    """Modifier le matériel d'un utilisateur (PROTÉGÉ)"""
    # Vérifier que l'utilisateur modifie son propre matériel ou est admin
    if isinstance(current_user, dict) and current_user.get('type') == 'app_user' and current_user.get('user_id') != user_id:
        raise HTTPException(status_code=403, detail="Accès refusé")
    
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        # Vérifier que l'association existe en utilisant l'ID de l'association
        cur.execute(
            "SELECT id FROM user_materiel WHERE id = %s AND user_id = %s",
            (user_materiel_id, user_id)
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Matériel non trouvé pour cet utilisateur")
        
        # Mettre à jour en utilisant l'ID de l'association
        cur.execute("""
            UPDATE user_materiel
            SET quantity = %s, note = %s
            WHERE id = %s AND user_id = %s
        """, (materiel.quantity, materiel.note, user_materiel_id, user_id))
        
        conn.commit()
        
        # Récupérer l'entrée mise à jour avec les détails du matériel
        cur.execute("""
            SELECT 
                um.id,
                um.user_id,
                um.materiel_id,
                um.quantity,
                um.note,
                um.added_at::text,
                m.name,
                m.description,
                m.image_url,
                m.category,
                m.is_active,
                m.created_at::text,
                m.updated_at::text
            FROM user_materiel um
            INNER JOIN materiel m ON um.materiel_id = m.id
            WHERE um.id = %s
        """, (user_materiel_id,))
        
        result = cur.fetchone()
        
        # Formater la réponse pour correspondre au format attendu par Flutter
        return {
            "id": result["id"],
            "user_id": result["user_id"],
            "materiel_id": result["materiel_id"],
            "quantity": result["quantity"],
            "note": result["note"],
            "added_at": result["added_at"],
            "materiel": {
                "id": result["materiel_id"],
                "name": result["name"],
                "description": result["description"],
                "image_url": result["image_url"],
                "category": result["category"],
                "is_active": result["is_active"],
                "created_at": result["created_at"],
                "updated_at": result["updated_at"]
            }
        }
    finally:
        conn.close()




@app.delete("/users/{user_id}/materiel/{user_materiel_id}")
def delete_user_materiel(
    user_id: int,
    user_materiel_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Retirer du matériel possédé par un utilisateur (PROTÉGÉ)"""
    # Vérifier que l'utilisateur supprime son propre matériel ou est admin
    if isinstance(current_user, dict) and current_user.get('type') == 'app_user' and current_user.get('user_id') != user_id:
        raise HTTPException(status_code=403, detail="Accès refusé")
    
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        # Utiliser l'ID de l'association (user_materiel.id) au lieu de materiel_id
        cur.execute(
            "DELETE FROM user_materiel WHERE id = %s AND user_id = %s",
            (user_materiel_id, user_id)
        )
        
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Matériel non trouvé pour cet utilisateur")
        
        conn.commit()
        
        return {"message": "Matériel retiré avec succès"}
    finally:
        conn.close()


@app.get("/users/{user_id}/can-make-recipes")
def get_recipes_user_can_make(user_id: int, current_user: dict = Depends(get_current_user)):
    """Récupérer les recettes que l'utilisateur peut faire avec son matériel (PROTÉGÉ)"""
    # Vérifier l'accès
    if isinstance(current_user, dict) and current_user.get('type') == 'app_user' and current_user.get('user_id') != user_id:
        raise HTTPException(status_code=403, detail="Accès refusé")
    
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        # Utiliser la vue SQL créée dans le schéma
        cur.execute("""
            SELECT 
                r.id as recipe_id,
                r.name as recipe_name,
                COUNT(DISTINCT rm.materiel_id) as total_materiel_needed,
                COUNT(DISTINCT CASE WHEN rm.is_optional = FALSE THEN rm.materiel_id END) as required_materiel,
                COUNT(DISTINCT um.materiel_id) as materiel_owned,
                COUNT(DISTINCT CASE WHEN rm.is_optional = FALSE AND um.materiel_id IS NOT NULL THEN rm.materiel_id END) as required_materiel_owned
            FROM recipes r
            LEFT JOIN recipe_materiel rm ON r.id = rm.recipe_id
            LEFT JOIN user_materiel um ON rm.materiel_id = um.materiel_id AND um.user_id = %s
            GROUP BY r.id, r.name
            HAVING COUNT(DISTINCT CASE WHEN rm.is_optional = FALSE THEN rm.materiel_id END) > 0
            ORDER BY 
                (COUNT(DISTINCT CASE WHEN rm.is_optional = FALSE AND um.materiel_id IS NOT NULL THEN rm.materiel_id END)::FLOAT / 
                 NULLIF(COUNT(DISTINCT CASE WHEN rm.is_optional = FALSE THEN rm.materiel_id END), 0)) DESC
        """, (user_id,))
        
        recipes = cur.fetchall()
        
        result = []
        for recipe in recipes:
            can_make = recipe['required_materiel'] == recipe['required_materiel_owned']
            completion_percentage = (
                int((recipe['required_materiel_owned'] / recipe['required_materiel']) * 100)
                if recipe['required_materiel'] > 0 else 0
            )
            
            result.append({
                'recipe_id': recipe['recipe_id'],
                'recipe_name': recipe['recipe_name'],
                'total_materiel_needed': recipe['total_materiel_needed'],
                'required_materiel': recipe['required_materiel'],
                'materiel_owned': recipe['materiel_owned'],
                'required_materiel_owned': recipe['required_materiel_owned'],
                'can_make': can_make,
                'completion_percentage': completion_percentage
            })
        
        return result
    finally:
        conn.close()

@app.get("/users/{user_id}/suggested-materiel")
def get_suggested_materiel(
    user_id: int,
    limit: int = 10,
    current_user: dict = Depends(get_current_user)
):
    """Suggérer du matériel à acheter pour débloquer plus de recettes (PROTÉGÉ)"""
    # Vérifier l'accès
    if isinstance(current_user, dict) and current_user.get('type') == 'app_user' and current_user.get('user_id') != user_id:
        raise HTTPException(status_code=403, detail="Accès refusé")
    
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        # Trouver le matériel manquant qui débloque le plus de recettes
        cur.execute("""
            SELECT 
                m.id as materiel_id,
                m.name as materiel_name,
                m.category as materiel_category,
                m.image_url as materiel_image,
                COUNT(DISTINCT rm.recipe_id) as would_unlock_recipes
            FROM materiel m
            INNER JOIN recipe_materiel rm ON m.id = rm.materiel_id
            LEFT JOIN user_materiel um ON m.id = um.materiel_id AND um.user_id = %s
            WHERE um.materiel_id IS NULL
              AND rm.is_optional = FALSE
              AND m.is_active = TRUE
            GROUP BY m.id, m.name, m.category, m.image_url
            ORDER BY would_unlock_recipes DESC
            LIMIT %s
        """, (user_id, limit))
        
        suggestions = cur.fetchall()
        return suggestions
    finally:
        conn.close()

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv('API_PORT', 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)