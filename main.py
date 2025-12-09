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
USERNAME = os.environ["EPSI_USER"]
PASSWORD = os.environ["EPSI_PASS"]
DISCORD_WEBHOOK = os.environ["DISCORD_URL"]

def get_tomorrow_date_id():
    # Format ID HTML : MM/DD/YYYY
    tomorrow = datetime.now() + timedelta(days=1)
    return tomorrow.strftime("%m/%d/%Y")

def get_tomorrow_human():
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
    print("🚀 Démarrage du bot (MODE ROBUSTE)...")
    
    chrome_options = Options()
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    # On force une très grande résolution pour éviter le mode mobile qui casse les %
    chrome_options.add_argument("--window-size=1920,1080") 
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    
    # On force aussi la taille via la commande driver (double sécurité)
    driver.set_window_size(1920, 1080)
    
    target_date_id = get_tomorrow_date_id()
    print(f"ℹ️ Date cible : {target_date_id}")
    
    try:
        driver.get(URL_EDT)
        wait = WebDriverWait(driver, 30)
        
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
        
        print("⏳ Chargement du calendrier (Attente 10s)...")
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "Jour")))
        time.sleep(10)

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # 1. Trouver la colonne du jour
        day_col = soup.find("div", id=f"I_Du_j_{target_date_id}")
        
        if not day_col:
            # Plan B : Chercher le jour/mois inversé
            inv_date = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
            day_col = soup.find("div", id=f"I_Du_j_{inv_date}")
            if day_col:
                print(f"⚠️ Format de date inversé détecté !")
            else:
                return f"⚠️ **Erreur** : La colonne du {get_tomorrow_human()} est introuvable sur la page."

        style = day_col.get('style', '')
        left_match = re.search(r'left\s*:\s*([\d\.]+)', style)
        if not left_match: return "Erreur technique: Position jour introuvable."
        
        target_left = float(left_match.group(1))
        print(f"✅ Cible (Mercredi ?) : {target_left}%")
        
        # 2. Scraper les cours avec la logique "Modulo"
        courses_found = []
        all_courses = soup.find_all("div", class_="Case")
        
        for course in all_courses:
            if not course.find(class_="TChdeb"): 
                continue 
            
            c_style = course.get('style', '')
            c_match = re.search(r'left\s*:\s*([\d\.]+)', c_style)
            
            if c_match:
                c_pos = float(c_match.group(1))
                
                # --- LA CORRECTION MAGIQUE ---
                # On ramène tout sur une échelle de 0 à 100% (Modulo)
                # Ex: 128% devient 28%
                pos_normalisee = c_pos % 100
                cible_normalisee = target_left % 100
                
                # On augmente la tolérance à 2.0% car les navigateurs arrondissent différemment
                diff = abs(pos_normalisee - cible_normalisee)
                
                if diff < 2.0:
                    heure = course.find(class_="TChdeb").get_text(strip=True)
                    # On nettoie le texte (enlève les espaces multiples et sauts de ligne)
                    raw_prof = course.find(class_="TCProf")
                    matiere = " ".join(raw_prof.get_text().split()) if raw_prof else "Matière inconnue"
                    salle = course.find(class_="TCSalle").get_text(strip=True)
                    
                    # Petite icone selon le type de cours
                    icon = "🎓"
                    if "Examen" in matiere: icon = "📝"
                    if "Distanciel" in matiere or "Teams" in salle: icon = "💻"
                    
                    courses_found.append(f"{icon} **{heure}**\n**{matiere}**\n📍 {salle}")
                    print(f"   -> Trouvé ! ({heure})")

        if courses_found:
            courses_found.sort() # Remet dans l'ordre chronologique
            return f"📅 **Emploi du temps du {get_tomorrow_human()}**\n\n" + "\n\n".join(courses_found)
        else:
            return f"📅 **Demain ({get_tomorrow_human()})** : Pas de cours détecté (Repos !) 🛌"

    except Exception as e:
        return f"❌ Crash Bot : {str(e)}"
    finally:
        driver.quit()

if __name__ == "__main__":
    msg = scrape_edt()
    print("--- ENVOI DISCORD ---")
    send_discord(msg)
