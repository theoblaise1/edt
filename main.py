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

# --- CONFIGURATION (Via Secrets GitHub) ---
URL_EDT = "https://ws-edt-cd.wigorservices.net/"
USERNAME = os.environ["EPSI_USER"]
PASSWORD = os.environ["EPSI_PASS"]
DISCORD_WEBHOOK = os.environ["DISCORD_URL"]

def get_tomorrow_date_id():
    """Format pour l'ID HTML (MM/DD/YYYY selon votre site)"""
    tomorrow = datetime.now() + timedelta(days=1)
    return tomorrow.strftime("%m/%d/%Y")

def get_tomorrow_human():
    """Format lisible (DD/MM/YYYY)"""
    tomorrow = datetime.now() + timedelta(days=1)
    return tomorrow.strftime("%d/%m/%Y")

def send_discord(message):
    data = {"content": message}
    try:
        requests.post(DISCORD_WEBHOOK, json=data)
        print("✅ Message envoyé sur Discord.")
    except Exception as e:
        print(f"❌ Erreur Discord : {e}")

def scrape_edt():
    print("🚀 Démarrage du bot...")
    
    # Options Chrome pour le mode serveur (Headless)
    chrome_options = Options()
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080") 
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    
    # ID de la date cible (Demain)
    target_date_id = get_tomorrow_date_id()
    
    try:
        driver.get(URL_EDT)
        wait = WebDriverWait(driver, 20)
        
        # --- 1. CONNEXION ---
        print("🔑 Connexion...")
        # Gestion des ID variables (username/user/login...)
        try:
            user_field = wait.until(EC.presence_of_element_located((By.ID, "username")))
            pass_field = driver.find_element(By.ID, "password")
        except:
            user_field = driver.find_element(By.NAME, "username")
            pass_field = driver.find_element(By.NAME, "password")

        user_field.send_keys(USERNAME)
        pass_field.send_keys(PASSWORD)
        pass_field.submit()
        
        # --- 2. CHARGEMENT CALENDRIER ---
        print("⏳ Chargement du calendrier...")
        # On attend l'affichage des colonnes "Jour"
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "Jour")))
        time.sleep(60) # Pause de sécurité pour le chargement des scripts JS

        # --- 3. ANALYSE (SCRAPING) ---
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        print(f"🔍 Recherche de la colonne pour l'ID : I_Du_j_{target_date_id}")
        
        # On cherche la colonne du jour spécifique (ex: I_Du_j_12/10/2025)
        day_col = soup.find("div", id=f"I_Du_j_{target_date_id}")
        
        if not day_col:
            return f"📅 **Demain ({get_tomorrow_human()})** : La colonne du jour est introuvable (Peut-être faut-il changer de semaine ?)"

        # On récupère la position CSS "left" de cette colonne
        style = day_col.get('style', '')
        left_match = re.search(r'left\s*:\s*([\d\.]+)', style)
        
        if not left_match: 
            return "⚠️ Erreur technique : Impossible de lire la position du jour."
        
        target_left = float(left_match.group(1))
        
        # On cherche tous les cours qui ont la même position "left"
        courses_found = []
        all_courses = soup.find_all("div", class_="Case")
        
        for course in all_courses:
            # Si la case n'a pas d'heure de début, ce n'est pas un cours
            if not course.find(class_="TChdeb"): 
                continue 
            
            c_style = course.get('style', '')
            c_match = re.search(r'left\s*:\s*([\d\.]+)', c_style)
            
            if c_match:
                c_pos = float(c_match.group(1))
                # On compare la position avec une tolérance de 1%
                if abs(c_pos - target_left) < 1.0:
                    heure = course.find(class_="TChdeb").get_text(strip=True)
                    # Nettoyage du texte prof/matière
                    matiere_brute = course.find(class_="TCProf").get_text(" ", strip=True) if course.find(class_="TCProf") else "Matière inconnue"
                    salle = course.find(class_="TCSalle").get_text(strip=True)
                    
                    courses_found.append(f"⏰ **{heure}**\n📚 {matiere_brute}\n📍 {salle}")

        # --- 4. RÉSULTAT ---
        if courses_found:
            courses_found.sort() # Trie simple
            return f"📅 **Emploi du temps pour demain ({get_tomorrow_human()})**\n\n" + "\n-------------------\n".join(courses_found)
        else:
            return f"📅 **Demain ({get_tomorrow_human()})** : Aucun cours détecté ! 🎉 (Repos ou bug d'affichage)"

    except Exception as e:
        return f"❌ Erreur critique du Bot : {str(e)}"
    finally:
        driver.quit()

if __name__ == "__main__":
    msg = scrape_edt()
    print(msg) # Pour les logs GitHub
    send_discord(msg)
