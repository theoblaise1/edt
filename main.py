import os
import time
import requests
import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from ics import Calendar, Event

# --- CONFIGURATION ---
URL_EDT = "https://ws-edt-cd.wigorservices.net/"
USERNAME = os.environ.get("EPSI_USER")
PASSWORD = os.environ.get("EPSI_PASS")

MOIS_FR = {
    1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril", 5: "Mai", 6: "Juin",
    7: "Juillet", 8: "Août", 9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre"
}
JOURS_FR = {
    0: "Lundi", 1: "Mardi", 2: "Mercredi", 3: "Jeudi", 4: "Vendredi", 5: "Samedi", 6: "Dimanche"
}

def scrape_edt():
    if not USERNAME or not PASSWORD:
        print("❌ Erreur : Identifiants manquants.")
        return

    chrome_options = Options()
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    cal = Calendar()
    
    try:
        driver.get(URL_EDT)
        wait = WebDriverWait(driver, 30)
        
        # LOGIN
        user_field = wait.until(EC.presence_of_element_located((By.ID, "username")))
        pass_field = driver.find_element(By.ID, "password")
        user_field.send_keys(USERNAME)
        pass_field.send_keys(PASSWORD)
        pass_field.submit()
        
        print("⏳ Chargement du calendrier...")
        time.sleep(20) 

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        all_courses = soup.find_all("div", class_="Case")

        # On traite les 7 prochains jours
        for i in range(7):
            target_date = datetime.now() + timedelta(days=i)
            target_text = f"{JOURS_FR[target_date.weekday()]} {target_date.strftime('%d')} {MOIS_FR[target_date.month]}"
            
            # Trouver la position de la colonne du jour
            target_left = None
            day_headers = soup.find_all("div", class_="Jour")
            for header in day_headers:
                if target_text.lower() in header.get_text().lower():
                    style = header.get('style', '')
                    match = re.search(r'left\s*:\s*([\d\.]+)', style)
                    if match:
                        target_left = float(match.group(1))
                        break
            
            if target_left is None:
                continue

            # Extraction des cours pour ce jour
            for course in all_courses:
                c_style = course.get('style', '')
                c_match = re.search(r'left\s*:\s*([\d\.]+)', c_style)
                
                if c_match and abs(float(c_match.group(1)) - target_left) < 0.5:
                    if not course.find(class_="TChdeb"): continue
                    
                    heure_raw = course.find(class_="TChdeb").get_text(strip=True) # ex: "08:30"
                    matiere = " ".join(course.find(class_="TCProf").get_text().split()) if course.find(class_="TCProf") else "Cours"
                    salle = course.find(class_="TCSalle").get_text(strip=True) if course.find(class_="TCSalle") else "N/A"
                    
                    # Création de l'événement iCal
                    e = Event()
                    e.name = matiere
                    e.location = salle
                    
                    # Gestion des horaires (approximation fin de cours +1h30 si non précisé)
                    h, m = map(int, heure_raw.split(':'))
                    start_dt = target_date.replace(hour=h, minute=m, second=0)
                    e.begin = start_dt
                    e.duration = {"hours": 1, "minutes": 30} 
                    
                    cal.events.add(e)

        # Sauvegarde du fichier
        with open("mon_edt.ics", "w") as f:
            f.writelines(cal.serialize_iter())
        print("✅ Fichier mon_edt.ics généré avec succès.")

    finally:
        driver.quit()

if __name__ == "__main__":
    scrape_edt()
