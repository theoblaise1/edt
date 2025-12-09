import os
import time
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import re
import locale

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options

# --- CONFIGURATION ---
URL_EDT = "https://ws-edt-cd.wigorservices.net/"
USERNAME = os.environ["EPSI_USER"]
PASSWORD = os.environ["EPSI_PASS"]
DISCORD_WEBHOOK = os.environ["DISCORD_URL"]

# Dictionnaire de traduction car GitHub Actions est souvent en Anglais par défaut
MOIS_FR = {
    1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril", 5: "Mai", 6: "Juin",
    7: "Juillet", 8: "Août", 9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre"
}
JOURS_FR = {
    0: "Lundi", 1: "Mardi", 2: "Mercredi", 3: "Jeudi", 4: "Vendredi", 5: "Samedi", 6: "Dimanche"
}

def get_target_text():
    """Génère le texte à chercher, ex: 'Mercredi 10 Décembre'"""
    tomorrow = datetime.now() + timedelta(days=1)
    
    jour_nom = JOURS_FR[tomorrow.weekday()]
    jour_num = tomorrow.strftime("%d") # 10
    mois_nom = MOIS_FR[tomorrow.month]
    
    # Format exact du site : "Mercredi 10 Décembre"
    return f"{jour_nom} {jour_num} {mois_nom}"

def send_discord(message):
    data = {"content": message}
    try:
        requests.post(DISCORD_WEBHOOK, json=data)
        print("✅ Message envoyé sur Discord.")
    except Exception as e:
        print(f"❌ Erreur Discord : {e}")

def scrape_edt():
    print("🚀 Démarrage du bot (Mode VISUEL)...")
    
    chrome_options = Options()
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080") 
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    
    target_text = get_target_text()
    print(f"🎯 Texte cible à trouver : '{target_text}'")
    
    try:
        driver.get(URL_EDT)
        wait = WebDriverWait(driver, 30)
        
        # --- LOGIN ---
        print("🔑 Connexion...")
        try:
            user_field = wait.until(EC.presence_of_element_located((By.ID, "username")))
            pass_field = driver.find_element(By.ID, "password")
        except:
            user_field = driver.find_element(By.NAME, "username")
            pass_field = driver.find_element(By.NAME, "password")

        user_field.send_keys(USERNAME)
        pass_field.send_keys(PASSWORD)
        pass_field.submit()
        
        # --- ATTENTE ---
        print("⏳ Chargement du calendrier (20s)...")
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "Jour")))
        time.sleep(20) # On laisse le temps au carrousel de se placer

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # 1. Trouver l'en-tête du jour (La case grise "Mercredi 10...")
        day_headers = soup.find_all("div", class_="Jour")
        target_left = None
        
        for header in day_headers:
            # Le texte est souvent dans une <td> avec class TCJour
            text_container = header.find(class_="TCJour")
            if text_container and target_text.lower() in text_container.get_text().lower():
                # BINGO ! On a trouvé la colonne
                style = header.get('style', '')
                left_match = re.search(r'left\s*:\s*([\d\.]+)', style)
                if left_match:
                    target_left = float(left_match.group(1))
                    print(f"✅ Colonne '{target_text}' trouvée à la position : {target_left}%")
                    break
        
        if target_left is None:
            return f"📅 **Demain ({target_text})** : Colonne introuvable. (Peut-être le WE ou pas de cours affichés ?)"

        # 2. Récupérer les cours alignés
        courses_found = []
        all_courses = soup.find_all("div", class_="Case")
        
        for course in all_courses:
            if not course.find(class_="TChdeb"): 
                continue 
            
            c_style = course.get('style', '')
            c_match = re.search(r'left\s*:\s*([\d\.]+)', c_style)
            
            if c_match:
                c_pos = float(c_match.group(1))
                # Comparaison de la position (Tolérance stricte car on a la vraie valeur)
                if abs(c_pos - target_left) < 0.5:
                    heure = course.find(class_="TChdeb").get_text(strip=True)
                    # Nettoyage
                    raw_prof = course.find(class_="TCProf")
                    matiere = " ".join(raw_prof.get_text().split()) if raw_prof else "Info inconnue"
                    salle = course.find(class_="TCSalle").get_text(strip=True)
                    
                    # Icônes
                    icon = "📘"
                    if "Anglais" in matiere: icon = "🇬🇧"
                    if "Examen" in matiere or "Controle" in matiere: icon = "⚠️ **EXAMEN**"
                    
                    courses_found.append(f"{icon} **{heure}**\n**{matiere}**\n📍 {salle}")

        # --- ENVOI ---
        if courses_found:
            courses_found.sort() # Trie par heure
            return f"📅 **Emploi du temps : {target_text}**\n\n" + "\n\n".join(courses_found)
        else:
            return f"📅 **Demain ({target_text})** : Pas de cours ! (Grasse mat' 🛌)"

    except Exception as e:
        return f"❌ Erreur Script : {str(e)}"
    finally:
        driver.quit()

if __name__ == "__main__":
    msg = scrape_edt()
    print(msg)
    send_discord(msg)
