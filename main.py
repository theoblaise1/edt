import os
import time
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import re

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options

# --- CONFIGURATION ---
URL_EDT = "https://ws-edt-cd.wigorservices.net/"
USERNAME = os.environ.get("EPSI_USER")
PASSWORD = os.environ.get("EPSI_PASS")

# Liste des webhooks pour l'envoi groupé
WEBHOOKS = [
    os.environ.get("DISCORD_URL"),
    os.environ.get("DISCORD_URL_GAUTHIER")
    os.environ.get("STOAT_URL")
]

# Dictionnaire de traduction (GitHub Actions est souvent en Anglais)
MOIS_FR = {
    1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril", 5: "Mai", 6: "Juin",
    7: "Juillet", 8: "Août", 9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre"
}
JOURS_FR = {
    0: "Lundi", 1: "Mardi", 2: "Mercredi", 3: "Jeudi", 4: "Vendredi", 5: "Samedi", 6: "Dimanche"
}

def get_target_text():
    """Génère le texte à chercher, ex: 'Mardi 17 Février'"""
    tomorrow = datetime.now() + timedelta(days=1)
    
    jour_nom = JOURS_FR[tomorrow.weekday()]
    jour_num = tomorrow.strftime("%d")
    mois_nom = MOIS_FR[tomorrow.month]
    
    return f"{jour_nom} {jour_num} {mois_nom}"

def send_discord(message):
    """Envoie le message à tous les webhooks configurés"""
    payload = {"content": message}
    for url in WEBHOOKS:
        if not url:
            print("⚠️ Un des Webhooks est vide (variable d'environnement manquante).")
            continue
        try:
            response = requests.post(url, json=payload)
            if response.status_code == 204:
                print(f"✅ Message envoyé avec succès à : {url[:30]}...")
            else:
                print(f"⚠️ Erreur lors de l'envoi ({response.status_code})")
        except Exception as e:
            print(f"❌ Erreur critique Discord : {e}")

def scrape_edt():
    print("🚀 Démarrage du bot (Mode Headless)...")
    
    if not USERNAME or not PASSWORD:
        return "❌ Erreur : Identifiants EPSI manquants dans les variables d'environnement."

    chrome_options = Options()
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080") 
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    
    target_text = get_target_text()
    print(f"🎯 Recherche des cours pour : '{target_text}'")
    
    try:
        driver.get(URL_EDT)
        wait = WebDriverWait(driver, 30)
        
        # --- LOGIN ---
        print("🔑 Connexion au portail...")
        try:
            user_field = wait.until(EC.presence_of_element_located((By.ID, "username")))
            pass_field = driver.find_element(By.ID, "password")
        except:
            user_field = driver.find_element(By.NAME, "username")
            pass_field = driver.find_element(By.NAME, "password")

        user_field.send_keys(USERNAME)
        pass_field.send_keys(PASSWORD)
        pass_field.submit()
        
        # --- ATTENTE CHARGEMENT ---
        print("⏳ Chargement du calendrier (20s)...")
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "Jour")))
        time.sleep(20) 

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # 1. Trouver l'en-tête du jour cible
        day_headers = soup.find_all("div", class_="Jour")
        target_left = None
        
        for header in day_headers:
            text_container = header.find(class_="TCJour")
            if text_container and target_text.lower() in text_container.get_text().lower():
                style = header.get('style', '')
                left_match = re.search(r'left\s*:\s*([\d\.]+)', style)
                if left_match:
                    target_left = float(left_match.group(1))
                    print(f"✅ Colonne trouvée à la position : {target_left}%")
                    break
        
        if target_left is None:
            return f"📅 **Demain ({target_text})** : Aucun cours trouvé sur l'EDT."

        # 2. Récupérer les cours de cette colonne
        courses_found = []
        all_courses = soup.find_all("div", class_="Case")
        
        for course in all_courses:
            if not course.find(class_="TChdeb"): 
                continue 
            
            c_style = course.get('style', '')
            c_match = re.search(r'left\s*:\s*([\d\.]+)', c_style)
            
            if c_match:
                c_pos = float(c_match.group(1))
                # Tolérance de positionnement
                if abs(c_pos - target_left) < 0.5:
                    heure = course.find(class_="TChdeb").get_text(strip=True)
                    raw_prof = course.find(class_="TCProf")
                    matiere = " ".join(raw_prof.get_text().split()) if raw_prof else "Matière inconnue"
                    salle = course.find(class_="TCSalle").get_text(strip=True)
                    
                    icon = "📘"
                    if "Anglais" in matiere: icon = "🇬🇧"
                    if any(word in matiere.lower() for word in ["examen", "controle", "quizz"]): 
                        icon = "⚠️ **EXAMEN**"
                    
                    courses_found.append(f"{icon} **{heure}**\n**{matiere}**\n📍 {salle}")

        # --- MISE EN FORME ---
        if courses_found:
            courses_found.sort() 
            return f"📅 **Emploi du temps : {target_text}**\n\n" + "\n\n".join(courses_found)
        else:
            return f"📅 **Demain ({target_text})** : Pas de cours prévus ! 🛌"

    except Exception as e:
        return f"❌ Erreur lors du scraping : {str(e)}"
    finally:
        driver.quit()

if __name__ == "__main__":
    resultat = scrape_edt()
    print(resultat)
    send_discord(resultat)
