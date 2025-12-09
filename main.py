import os
import time
import requests
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

def send_discord(message):
    data = {"content": message}
    try:
        requests.post(DISCORD_WEBHOOK, json=data)
    except: pass

def scrape_edt():
    print("🚀 Démarrage du SCANNER BRUT...")
    
    chrome_options = Options()
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    # On simule un très grand écran PC pour forcer l'affichage bureau
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    
    try:
        driver.get(URL_EDT)
        print(f"🔗 URL actuelle : {driver.current_url}")
        
        wait = WebDriverWait(driver, 30)
        
        # --- LOGIN ---
        if "login" in driver.current_url or "cas" in driver.current_url:
            print("🔑 Tentative de connexion...")
            try:
                user_field = wait.until(EC.presence_of_element_located((By.ID, "username")))
                pass_field = driver.find_element(By.ID, "password")
                user_field.send_keys(USERNAME)
                pass_field.send_keys(PASSWORD)
                pass_field.submit()
            except:
                print("⚠️ Formulaire de login non standard trouvé.")

        # --- ATTENTE ---
        print("⏳ Attente du chargement complet (20s)...")
        # On attend spécifiquement un élément qui prouve que l'EDT est là
        try:
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "TChdeb"))) # On attend une heure de cours
        except:
            print("⚠️ Attention : Aucun horaire (TChdeb) détecté après 30s.")

        time.sleep(10) # Pause supplémentaire

        # --- DIAGNOSTIC ---
        print("📸 Capture du code source...")
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # 1. Vérifier si on est connectés
        if "Connexion" in soup.get_text():
            return "❌ ÉCHEC : Le bot semble bloqué sur la page de connexion."

        # 2. Lister TOUS les cours visibles
        all_courses = soup.find_all("div", class_="Case")
        
        found_logs = []
        found_logs.append(f"📊 **Rapport de Scan**")
        found_logs.append(f"Nombre de blocs 'Case' trouvés : {len(all_courses)}")
        
        cpt_cours = 0
        buffer_msg = ""
        
        for i, course in enumerate(all_courses):
            # On récupère le style pour voir la position
            style = course.get('style', 'No style')
            
            # Est-ce un vrai cours ?
            heure_div = course.find(class_="TChdeb")
            prof_div = course.find(class_="TCProf")
            
            if heure_div:
                cpt_cours += 1
                heure = heure_div.get_text(strip=True)
                prof = prof_div.get_text(" ", strip=True) if prof_div else "?"
                left_match = re.search(r'left\s*:\s*([\d\.]+)', style)
                pos = left_match.group(1) if left_match else "?"
                
                line = f"🔹 **Cours {cpt_cours}** : {heure} | Pos: {pos}% | {prof[:30]}..."
                print(line) # Log GitHub
                buffer_msg += line + "\n"
            else:
                # C'est probablement une case vide ou un décor
                pass

        if cpt_cours == 0:
            return "❌ Aucun cours trouvé dans le code HTML. Le calendrier est vide ou pas chargé."
        
        return f"✅ **Succès ! Voici tout ce que le bot voit (sans filtrer le jour) :**\n\n{buffer_msg}"

    except Exception as e:
        return f"❌ Crash : {str(e)}"
    finally:
        driver.quit()

if __name__ == "__main__":
    msg = scrape_edt()
    print("--- RAPPORT ---")
    print(msg)
    send_discord(msg[:1900]) # Discord limite à 2000 caractères
