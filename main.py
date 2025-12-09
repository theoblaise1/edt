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
    # Format ID HTML : MM/DD/YYYY (ex: 12/10/2025 pour le 10 dec)
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
    print("🚀 Démarrage du bot (MODE DEBUG)...")
    
    chrome_options = Options()
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080") 
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    
    target_date_id = get_tomorrow_date_id()
    print(f"ℹ️ Date cible (ID HTML) : {target_date_id}")
    
    try:
        driver.get(URL_EDT)
        wait = WebDriverWait(driver, 30) # Augmenté à 30s
        
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
        
        print("⏳ Chargement du calendrier (Attente 15s)...")
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "Jour")))
        time.sleep(60) # Pause longue

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # --- DEBUG COLONNE JOUR ---
        day_col = soup.find("div", id=f"I_Du_j_{target_date_id}")
        
        if not day_col:
            # Essai inversion jour/mois
            inv_date = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
            day_col = soup.find("div", id=f"I_Du_j_{inv_date}")
            if day_col:
                print(f"⚠️ ATTENTION : Format de date inversé détecté ! ID trouvé : {inv_date}")
            else:
                # DEBUG : AFFICHER LES IDs DISPONIBLES
                print("❌ Colonne introuvable. Voici les 5 premiers IDs de jours trouvés dans le code :")
                jours_trouves = soup.find_all("div", class_="Jour")
                for j in jours_trouves[:5]:
                    # Cherche l'ID dans la div parente ou enfant
                    print(f"   - {j.get('id')} ou classe: {j.get('class')}")
                
                return f"⚠️ **Debug** : Colonne {target_date_id} introuvable."

        style = day_col.get('style', '')
        left_match = re.search(r'left\s*:\s*([\d\.]+)', style)
        if not left_match: return "Erreur technique: Position jour introuvable."
        
        target_left = float(left_match.group(1))
        print(f"✅ Colonne du jour trouvée ! Position LEFT : {target_left}%")
        
        # --- RECHERCHE COURS ---
        courses_found = []
        all_courses = soup.find_all("div", class_="Case")
        print(f"ℹ️ Nombre total de blocs 'Case' trouvés : {len(all_courses)}")
        
        nb_checked = 0
        for course in all_courses:
            if not course.find(class_="TChdeb"): 
                continue 
            
            c_style = course.get('style', '')
            c_match = re.search(r'left\s*:\s*([\d\.]+)', c_style)
            
            if c_match:
                c_pos = float(c_match.group(1))
                diff = abs(c_pos - target_left)
                
                # DEBUG : Afficher quelques cours ignorés pour comprendre
                if nb_checked < 3 and diff > 1.0:
                    print(f"   -> Ignoré (Pos: {c_pos}% vs Cible: {target_left}%)")
                    nb_checked += 1

                if diff < 1.0: # Tolérance 1%
                    print(f"   -> ✅ MATCH ! (Pos: {c_pos}%)")
                    heure = course.find(class_="TChdeb").get_text(strip=True)
                    matiere = course.find(class_="TCProf").get_text(" ", strip=True)
                    salle = course.find(class_="TCSalle").get_text(strip=True)
                    courses_found.append(f"⏰ **{heure}**\n📚 {matiere}\n📍 {salle}")

        if courses_found:
            courses_found.sort()
            return f"📅 **Emploi du temps pour demain ({get_tomorrow_human()})**\n\n" + "\n-------------------\n".join(courses_found)
        else:
            return f"📅 **Demain ({get_tomorrow_human()})** : Aucun cours détecté (Malgré {len(all_courses)} blocs analysés)."

    except Exception as e:
        return f"❌ Erreur Bot : {str(e)}"
    finally:
        driver.quit()

if __name__ == "__main__":
    msg = scrape_edt()
    print("--- MESSAGE FINAL ---")
    print(msg)
    send_discord(msg)
