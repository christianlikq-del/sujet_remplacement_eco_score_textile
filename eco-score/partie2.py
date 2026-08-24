import json
from pathlib import Path

dossier_data = Path(__file__).parent / "data"


def charger(nom_fichier : str):
    with open(dossier_data / nom_fichier, encoding="utf-8") as f:
        return json.load(f)


# Les 4 fichiers de données, tous les 4 liste de dico IA 
PROCESSES = charger("processes.json") 
MATERIALS = charger("materials.json")#	17 matières
PRODUCTS = charger("products.json")#11 catégories
COUNTRIES = charger("countries.json")#34 pays et régions

# Index element
processes_par_id = {PROCESS["id"]: PROCESS for PROCESS in PROCESSES}
materiaux_par_nom = {MATERIAL["name"]: MATERIAL for MATERIAL in MATERIALS}
materiaux_par_id = {MATERIAL["id"]: MATERIAL for MATERIAL in MATERIALS}
produits_par_id = {PRODUCT["id"]: PRODUCT for PRODUCT in PRODUCTS}
pays_par_code = {COUNTRY["code"]: COUNTRY for COUNTRY in COUNTRIES}
# dico dont clé est id puos va PROCESS lui meme 

# cherche impac en pts (ecs)
def ecs_du_process(process_id:str):
    """Impact d'un procédé en points/kg. Champ impacts.ecs de processes.json."""
    return processes_par_id[process_id]["impacts"]["ecs"]


# définition des constantes (notice p14) 
Taux_perte_filature = {
    "NaturalFromVegetal":    0.12,   
    "NaturalFromAnimal":     0.12,   
    "ArtificialFromOrganic": 0.12,   
    "Synthetic":             0.03,   
}
Taux_perte_etoffe = { #p 27 et cléva du champ fabric de products json 
    "weaving":                  0.0625,  
    "knitting-mix":             0.0545,  
    "knitting-fully-fashioned": 0.005,   
}
Taux_perte_ennoblissement = 0.0   
Stocks_dormants = 0.15          


# déduction de la masse entrante par masse sortante
def calcul_masses(categorie:str, composition:list, masse_vetement:float): 
    
    PRODUCT = produits_par_id[categorie]

    # Etape confection : chutes de decoupe  + stocks dormants
    PCR_WASTE = PRODUCT["making"]["pcrWaste"] # sous dico, on veut pcrWaste (float)
    masse_etoffe = masse_vetement / (1 - PCR_WASTE) / (1 - Stocks_dormants)
#masse_etoffe = masse_vetement / (1 - PCR_WASTE) / Stocks_dormants
    # Etape ennoblissement : pas dz perte
    masse_etoffe = masse_etoffe / (1 - Taux_perte_ennoblissement)

    # Etape tissage ou tricotage
    FABRIC = PRODUCT["fabric"] # str, 3 categories possibles
    masse_fil = masse_etoffe / (1 - Taux_perte_etoffe[FABRIC])

    # Etape filature : chaque matiere a son propre fil, ie son propre taux
    masses_fils = {}
    masses_matieres = {}
    for nom, taux in composition:
        MATERIAL = materiaux_par_nom[nom] #cherche la fiche complete de "nom" dans index
        Taux_filature = Taux_perte_filature[MATERIAL["origin"]] #idem, MATERIAL["origin"] : str 
        masses_fils[nom] = taux * masse_fil
        masses_matieres[nom] = masses_fils[nom] / (1 - Taux_filature)

    return {
        "vetement": masse_vetement,
        "etoffe": masse_etoffe, #tissage/ennoblissement
        "fil": masse_fil, #trico
        "fils": masses_fils, #filature
        "matieres": masses_matieres, # clé: matière et va : masse fibre brute
    }

# Tests sur calcul_masses()
print("test calcul_masse")
print(len(PROCESSES), "procédés chargés")
print(ecs_du_process(materiaux_par_nom["Coton"]["processId"]), "pts/kg pour le coton")
print()

# Test 1 : t-shirt 155 g, 60% coton 40% polyester
m = calcul_masses("tshirt", [("Coton", 0.6), ("Polyester", 0.4)], 0.155)
print("Test 1 — t-shirt 155 g, 60 coton / 40 polyester")
print("  etoffe        ", round(m["etoffe"] * 1000, 2), "g")
print("  fil           ", round(m["fil"] * 1000, 2), "g")
for nom, masse in m["matieres"].items():
    print("   ", nom, round(masse * 1000, 2), "g")


#etape 1 de ACV
def impact_unitaire_matiere(nom_matiere:str):#"nom_matiere"
    """Impact d'une fibre en points/kg.

    si matiere vierge, on lit directement l'impact du procede.
    si matiere recyclee, on fait CFF (Circular Footprint Formula):
        I = (1 - R1) x EV + R1 x ( A x E_recycled + (1 - A) x EV x Qsin/Qp )
    on pose R1 = 1 pour une fibre recyclee, R1 = 0 sinon.
    """
    MATERIAL = materiaux_par_nom[nom_matiere] #fiche de la mat
    ECS = ecs_du_process(MATERIAL["processId"]) #cherche le score 
    CFF = MATERIAL["cff"]
    if CFF is None: #ie pas de cff dc vierge, on regarde dans la fiche 
        return ECS      # matiere vierge

    # matiere recyclee : on partage avec la matiere vierge evitee
    A = CFF["manufacturerAllocation"]      # cle de partage
    Q = CFF["recycledQualityRatio"]        # perte de qualite au recyclage
    MATERIAL_VIERGE = materiaux_par_id[MATERIAL["recycledFrom"]] #recycledFrom contient l'identifiant de la matière vierge
    EV = ecs_du_process(MATERIAL_VIERGE["processId"]) #ilpact matiere primaire 

    return A * ECS + (1 - A) * EV * Q

#Impact de l'etape 1 de l'ACV, les matieres premieres, en points.
def impact_matieres(masses):
    total = 0
    for nom, masse in masses["matieres"].items():
        total = total + masse * impact_unitaire_matiere(nom)
    return total

#text etape 1 
# Les 17 impacts unitaires
print("text etape 1")
print("Impacts unitaires (pts/kg)")
for nom in sorted(materiaux_par_nom):
    print("  ", nom, round(impact_unitaire_matiere(nom), 1))
print()

# Test 1 : t-shirt 155 g, 60 coton / 40 polyester
m = calcul_masses("tshirt", [("Coton", 0.6), ("Polyester", 0.4)], 0.155)
print("Test 1 — t-shirt 155 g, 60 coton / 40 polyester")
for nom, masse in m["matieres"].items():
    unitaire = impact_unitaire_matiere(nom)
    print("  ", nom, round(masse * 1000, 2), "g x",
          round(unitaire, 1), "pts/kg =", round(masse * unitaire, 2), "pts")
print("   TOTAL", round(impact_matieres(m), 2), "pts")
print()

# étape 2 de l'ACV

Elec_filature = {
    "NaturalFromVegetal":    4.0,   # filature naturelle
    "NaturalFromAnimal":     4.0,
    "ArtificialFromOrganic": 4.0,
    "Synthetic":             1.5,   # filage pour synthqs
}

def impact_filature(masses:dict, categorie:str, code_pays:str):

    #Quantite_elec = (Titrage / 50) x Constante x masse de fil
    #I_filature = Quantite_elec x I_elec
    TITRAGE = produits_par_id[categorie]["yarnSize"]
    # produits_par_id[categorie] renvoie la fiche de la categorie (dico ici).
    # ["yarnSize"] extrait le titrage.

    # electricite consommee (selon mat)depend de la fibre
    kwh = 0 #initialisation 
    for nom, masse_fil in masses["fils"].items():#.items() donne cle et valeur chaque tour
        #   nom: str   ex: "Coton"
        #   masse_fil : float ex:0.13308 
        ORIGIN = materiaux_par_nom[nom]["origin"]
        kwh =kwh + (TITRAGE / 50) * Elec_filature[ORIGIN] * masse_fil
    # impact du mix electrique du pays de fabrication
    COUNTRY = pays_par_code[code_pays]
    ECS_ELEC = ecs_du_process(COUNTRY["electricityProcessId"])
    # COUNTRY["electricityProcessId"]=str : l'id du procede,de prodct d'elct du pays 
    # ecs_du_process va chercher ce procede dans processes.json et renvoie son champ impacts.ecs.
    return kwh * ECS_ELEC #impact en pts

# text etape 2 ACV
print()
print("text etape 2 — filature")

# test etape 2 — filature
m2 = calcul_masses("tshirt", [("Polyester recyclé", 1.0)], 0.150)
print("filature :", round(impact_filature(m2, "tshirt", "CN"), 2), "pts   (Ecobalyse 16.20)")
kwh = (40 / 50) * 1.5 * m2["fils"]["Polyester recyclé"]
print("kWh      :", round(kwh, 4), "  (Ecobalyse 0.26)")
print("fin test etape 2")

# étape 3 tricotage 
Elec_tricotage = {
    "knitting-mix":             2.4,
    "knitting-fully-fashioned": 1.68,
}

# parametres du tissage
Constante_tissage = 0.0003145   # kWh par duites.m
Embuvage = 1.08  # taux d'embuvage et de retrait de 8 %

#Impact de l'etape tissage ou tricotage, en points.
def impact_tissage(masses:dict, categorie:list, code_pays:str):#code_pays=code ISO
    PRODUCT = produits_par_id[categorie]#fiche complete de la catégorie 
    FABRIC = PRODUCT["fabric"]#champ qui decide quelle formule appliquer
    if FABRIC == "weaving": #cas 1 tissage
        # tissage : la masse d'etoffe est en grammes dans la formule
        TITRAGE = PRODUCT["yarnSize"] # Titrage x MasseSortante(g) x 0,0003145 / (1,08 x 2)
        masse_etoffe_g = masses["etoffe"] * 1000 #convertion en kg 
        kwh = TITRAGE * masse_etoffe_g * Constante_tissage / (Embuvage * 2)
    else:
        # tricotage : une constante par kg de fil
        kwh = Elec_tricotage[FABRIC] * masses["fil"] #Elec_tricotage[FABRIC]=2.4 ou 1.68
    

    # impact du mix electrique du pays de fabrication
    COUNTRY = pays_par_code[code_pays]
    ECS_ELEC = ecs_du_process(COUNTRY["electricityProcessId"])
    return kwh * ECS_ELEC 

# test etape 3 — tissage / tricotage
# ID 1 : T-shirt basique blanc, 100 % coton, Bangladesh, 150 g ie tricotage
# ID 19 : Jean brut selvedge, 100 % coton, Turquie, 680 g ie tissage

m1 = calcul_masses("tshirt", [("Coton", 1.0)], 0.150)
print("ID 1  t-shirt coton, Bangladesh :",
      round(impact_tissage(m1, "tshirt", "BD"), 2), "pts   (tricotage)")

m19 = calcul_masses("jean", [("Coton", 1.0)], 0.680)
print("ID 19 jean coton, Turquie       :",
      round(impact_tissage(m19, "jean", "TR"), 2), "pts   (tissage)")
print()
print("  t-shirt : fil", round(m1["fil"] * 1000, 1), "g x 2.4 kWh/kg =",
      round(2.4 * m1["fil"], 3), "kWh")
print("  jean    : etoffe", round(m19["etoffe"] * 1000, 1), "g ->",
      round(40 * m19["etoffe"] * 1000 * 0.0003145 / 2.16, 3), "kWh")
print("fin test etape 3")

#code étape 4 : enno 
Conso_ennoblissement = {
    "degraissage":  (0.30, 13.50),
    "blanchiment":  (0.20,  5.40),
    "lavage_synth": (0.20, 10.80),
    "teinture":     (1.00, 24.30),
    "apprets":      (0.60, 13.50),
}
# dict[str, tuple[float, float]]
#   cles    = nom du procede, invente par nous (str)
#   valeurs = un TUPLE de deux nombres (float, float)
def impact_ennoblissement(masses:dict, composition:list, code_pays:str):

    #proportion pour chaque fammille 
    part_synthetique = 0
    part_naturelle = 0
    for nom, taux in composition:
        ORIGIN = materiaux_par_nom[nom]["origin"]
        # type str "NaturalFromVegetal", "Synthetic", "ArtificialFromOrganic"
        # ORIGIN dans materials.json.
        if ORIGIN == "Synthetic":
            part_synthetique = part_synthetique + taux
        elif ORIGIN.startswith("Natural"):# si ORIGIN commen par "Natural...."
            part_naturelle = part_naturelle + taux
    #precd appliqué
    taux_procedes = {
        "degraissage":  part_naturelle, #1 si matiere naturelle, 0 sinon 
        "blanchiment":  1 - part_synthetique, #0 si synthetique, 1 sinon
        "lavage_synth": part_synthetique,#1 si synthetique, 0 sinon 
        "teinture":     1.0,
        "apprets":      1.0,
    }
    #somme 
    kwh_par_kg = 0
    mj_par_kg = 0
    for procede, taux in taux_procedes.items():
        # procede=str ex:"teinture"
        # taux=float ex:1.0
        ELEC, CHALEUR = Conso_ennoblissement[procede]
        # ex:Conso_ennoblissement["teinture"] = 1.00, 24.30)
        kwh_par_kg = kwh_par_kg + taux * ELEC
        mj_par_kg = mj_par_kg + taux * CHALEUR

    kwh = kwh_par_kg * masses["etoffe"]
    mj = mj_par_kg * masses["etoffe"]

    #conversion en pts
    COUNTRY = pays_par_code[code_pays]
    # type dico lu dans countries.json.
    ECS_ELEC = ecs_du_process(COUNTRY["electricityProcessId"])
    # pts electricite 
    ECS_CHALEUR = ecs_du_process(COUNTRY["heatProcessId"])
    return kwh * ECS_ELEC + mj * ECS_CHALEUR
   
# test etape 4 — ennoblissement
# ID 1 : T-shirt basique blanc, 100 % coton, Bangladesh, 150 g
print("test etape 4 enno")
compo1 = [("Coton", 1.0)]
m1 = calcul_masses("tshirt", compo1, 0.150)
print("ID 1 t-shirt coton, Bangladesh    :",
      round(impact_ennoblissement(m1, compo1, "BD"), 2), "pts")

# ID 3 : T-shirt technique, 88 polyester / 12 elasthanne, Vietnam, 130 g
compo3 = [("Polyester", 0.88), ("Elasthane", 0.12)]
m3 = calcul_masses("tshirt", compo3, 0.130)
print("ID 3 t-shirt synthetique, Vietnam :",
      round(impact_ennoblissement(m3, compo3, "VN"), 2), "pts")
print("fin test etape 4 enno")

#étape 5 : confection
Minutes_confection = {
    "very-low":  5,     # Tres faible, moins de 5 mi
    "low":       15,    # Faible, entre 5 et 15 min
    "medium":    30,    # Moyenne, entre 15 et 30 min
    "high":      60,    # Elevee, entre 30 min et 1 h
    "very-high": 120,   # Tres elevee, > d'1 h
}
#   cles : complexite de products.json (str)
#   valeurs :temps confections 

Elec_utls_par_minute = 0.029 #notice

def impact_confection(categorie:list, code_pays:str):

    COMPLEXITY = produits_par_id[categorie]["making"]["complexity"]
    # produits_par_id[categorie] renvoie la fiche de la categorie (dico), 
    # ["making"] extrait aussi un dico et["complexity"] la valeur qu'on veiut
    kwh = Minutes_confection[COMPLEXITY] * Elec_utls_par_minute
    # Minutes_confection[COMPLEXITY]= temps complexité
    COUNTRY = pays_par_code[code_pays] # pays_par_code[]=dico dont clé = code ISO pays 
    ECS_ELEC = ecs_du_process(COUNTRY["electricityProcessId"])
    #COUNTRY["electricityProcessId"] renvoie un id , COUNTRY = fiche info du pays 
    #ecs_du_process(COUNTRY["electricityProcessId"]) : fct crée pour obtenir l'impact en pts
    return kwh * ECS_ELEC

#test étape 5: confection 
print("debut test 5 confection")

print("t-shirt, Chine :", round(impact_confection("tshirt", "CN"), 2), "pts   (Ecobalyse 26.75)")
print("jean, Turquie  :", round(impact_confection("jean", "TR"), 2), "pts")
print("manteau, Chine :", round(impact_confection("manteau", "CN"), 2), "pts")

print()
COUNTRY = pays_par_code["CN"]
print("  complexite t-shirt :", produits_par_id["tshirt"]["making"]["complexity"])
print("  minutes            :", Minutes_confection["low"])
print("  kWh                :", round(Minutes_confection["low"] * Elec_utls_par_minute, 4), "  (Ecobalyse 0.44)")
print("  procede elec       :", processes_par_id[COUNTRY["electricityProcessId"]]["displayName"])
print("  pts par kWh        :", round(ecs_du_process(COUNTRY["electricityProcessId"]), 2))

print("fin test etape 5 confection ")

# impacts unit des accessoires, pts/pc relevé à main sur ecobalyse
Impact_accessoire = {
    "d56bb0d5-7999-4b8b-b076-94d79099b56a":  0.27,   # bouton plastique 1 g
    "0c903fc7-279b-4375-8cfa-ca8133b8e973": 22.03,   # bouton metal 3 g
    "0e8ea799-9b06-490c-a925-37564746c454": 73.44,   # zip court 10 g
    "86b877ff-0d59-482f-bb34-3ff306b07496": 367.0,   # zip long 50 g
}
Nom_accessoire = {
    "d56bb0d5-7999-4b8b-b076-94d79099b56a": "bouton plastique",
    "0c903fc7-279b-4375-8cfa-ca8133b8e973": "bouton metal",
    "0e8ea799-9b06-490c-a925-37564746c454": "zip court",
    "86b877ff-0d59-482f-bb34-3ff306b07496": "zip long",
}
def impact_accessoires(categorie):
    total = 0
    for TRIM in produits_par_id[categorie]["trims"]:# produits_par_id[categorie] renvoie la fiche de la categorie (dico)
        total = total + TRIM["quantity"] * Impact_accessoire[TRIM["id"]]
        #["trims"]liste accessoires trim = accessoires
        #TRIM = dico avec cle= id de l'accessoires et va=qté de l'accessoires
    return total

# test etape 6 — accessoires
print("début test 6 accessoires")
for categorie in ["tshirt", "chemise", "jean", "manteau", "pull", "chaussettes"]:
    print(categorie, round(impact_accessoires(categorie), 2), "pts")

#etape 7 distribution 
Distance_distribution = 500   # km
#deiux choix dans processes.json :
# 46e96f29-9ca5-5475-bb3c-6397f43b7a5b  transport routier=15,46
# 3db67ae7-c169-5837-8e0a-3c3c31ffda67  camion non specifie France=20,60

# retrouve le procede par nom
Process_camion_france = None
for PROCESS in PROCESSES:
    if PROCESS["displayName"] == "Transport en camion non spécifié France":
        Process_camion_france = PROCESS["id"]
#Process_camion_france = "3db67ae7-c169-5837-8e0a-3c3c31ffda67"

def impact_distribution(masse_vetement):
    #impact distri pts
    #I = masse(kg) / 1000 x D_camion x I_camion
    tonnes = masse_vetement / 1000
    ECS_CAMION = ecs_du_process(Process_camion_france) #I_camion 
    return tonnes * Distance_distribution * ECS_CAMION

# test etape 7 — distribution
print("debut test 7 distribution")
print()

print("procede  :", processes_par_id[Process_camion_france]["displayName"])
print("impact   :", ecs_du_process(Process_camion_france), "pts/t.km")
print("distance :", Distance_distribution, "km")
print()

# (ID, designation, masse en kg)
vetements_test = [
    (1,  "T-shirt basique blanc", 0.150),
    (19, "Jean brut selvedge",    0.680),
    (31, "Manteau laine",         1.450),
]

for ID, designation, masse in vetements_test:
    print("ID", ID, "-", designation.ljust(24),
          masse * 1000, "g ", round(impact_distribution(masse), 3), "pts")

print()
print("fin test 7 distribution")

# coef_durabilité
c_durabilite_min=0.67
c_durabilite_max=1.45

def i_largeur_gamme(nb_ref):
    if nb_ref > 16000:
        return 0.0
    raise NotImplementedError(
        #ttes ref = 100 000 par dft
    )

def indice_reparation(prix, cout_reparation, service_reparation):
    #I_reparation = 0,66 x I1 + 0,33 x I2
    #I1 : rapport cout de reparation / prix neuf. 100 % sous 33 %, 0 % au-dela de 100 %, lineaire entre.
    #I2 : 100 % si la marque propose un service de reparation labellise.
    r = cout_reparation / prix
    if r < 0.33:
        I_1 = 1.0
    elif r > 1.0:
        I_1 = 0.0
    else:
        I_1 = (1.0 - r) / (1.0 - 0.33)
    if service_reparation:
        I_2=1
    else:
        I_2=0
    return 0.66 * I_1 + 0.33 * I_2


def coef_durabilite(categorie, prix):
    #c dura entre 0,67 et 1,45.
    #C = 0,67 + (1,45 - 0,67) x (0,5 x I_reparation + 0,5 x I_largeur)
    #comme ds base pas de marque:
    #100 000 references          -> I_largeur = 0
    #sans service -> I2 = 0    
    ECONOMICS = produits_par_id[categorie]["economics"]
    COUT_REPARATION = ECONOMICS["repairCost"]         
    NB_REFERENCES = ECONOMICS["numberOfReferences"]   # defaut 100 000
    BUSINESS = ECONOMICS["business"]                  # defaut sans service
    service = BUSINESS.endswith("with-services")
    I_reparation = indice_reparation(prix, COUT_REPARATION, service)
    I_largeur = i_largeur_gamme(NB_REFERENCES)
    return c_durabilite_min + (c_durabilite_max - c_durabilite_min) * (
        0.5 * I_reparation + 0.5 * I_largeur 
    )

# test — coefficient de durabilite
print("debut test durabilite")
print()

# verification va par dft de products.json
print("valeurs economiques par categorie")
for PRODUCT in PRODUCTS:
    E = PRODUCT["economics"]
    print("  ", PRODUCT["id"].ljust(18),
          "repairCost", str(E["repairCost"]).rjust(3),
          "| refs", str(E["numberOfReferences"]).rjust(7),
          "|", E["business"])
print()

# (ID, designation, categorie, prix)
vetements_test = [
    (1,  "T-shirt basique blanc", "tshirt",  7.99),
    (2,  "T-shirt coton bio",     "tshirt",  24.90),
    (19, "Jean brut selvedge",    "jean",    119.00),
    (35, "Robe viscose imprimee", "jupe",    39.90),
    (31, "Manteau laine",         "manteau", 349.00),
    (40, "Chaussettes coton",     "chaussettes", 3.99),
]

print("coefficients de durabilite")
for ID, designation, categorie, prix in vetements_test:
    COUT = produits_par_id[categorie]["economics"]["repairCost"]
    ratio = COUT / prix
    c = coef_durabilite(categorie, prix)
    print("  ID", str(ID).rjust(2), designation.ljust(24),
          "prix", str(prix).rjust(7),
          "| repar", str(COUT).rjust(3),
          "| ratio", str(round(ratio, 3)).rjust(6),
          "| C =", round(c, 4))

print()
print("fin test durabilite")


#etape 8 utilisation 


#mix fr car tt produit est lavé en france 
Process_elec_france_bt = "931c9bb0-619a-5f75-b41b-ab8061e2ad92"

# Notice p.44 : conversion entre les deux unites d'energie
MJ_par_kWh = 3.6


def impact_utilisation(masses:dict, categorie:list, c_durabilite:float):
    #I_utilisation = n_cycles x m x I_hors_repassage (pts/kg) + E_utilisation x I_elec
    #E_utilisation = n_cycles x m x E_hors_repassage (kWh/kg) + n_cycles x E_repassage (kWh/vetement)
    #n_cycles = n_cycles_defaut x C_durabilite         
    #MAJUSCULES : lu dans products.json. IA
    USE = produits_par_id[categorie]["use"]
    #USE=dico, ex poir t shirt :
    #   {"daysOfWear": 45, "defaultNbCycles": 45, ...
    NB_CYCLES_DEFAUT = USE["defaultNbCycles"]   #45 pour un t-shirt, 5 pour un manteau,
    IRONING_MJ = USE["ironingElecInMJ"]            
    PROCESS_USE = USE["nonIroningProcessUuid"] #Impact hors repassage
    n_cycles = NB_CYCLES_DEFAUT * c_durabilite
    masse = masses["vetement"] 

    # partie hors electricite : eau, lessive, traitement des eaux usees
    I_HORS_REPASSAGE = ecs_du_process(PROCESS_USE) # pts/kg hors repassage
    impact_hors_elec = n_cycles * masse * I_HORS_REPASSAGE

    # partie electricite : lavage et sechage en kWh/kg, repassage en kWh/vetement
    E_HORS_REPASSAGE = processes_par_id[PROCESS_USE]["elecKwh"]  # kWh/kg hors repassage
    e_repassage = IRONING_MJ / MJ_par_kWh # kWh/vetement
    e_utilisation = n_cycles * masse * E_HORS_REPASSAGE + n_cycles * e_repassage
    I_ELEC = ecs_du_process(Process_elec_france_bt) # pts/kWh mix francais par defaut 
    return impact_hors_elec + e_utilisation * I_ELEC





#etape 9 fin de vie 
Process_fin_de_vie = "ab96b73f-8534-59ad-9f34-a579abe3b023" #mix fr 

def impact_fin_de_vie(masses:list):
#I_total_FDV = I_FDV_hors_voiture + Complement_FDV_hors_Europe
    return masses["vetement"] * ecs_du_process(Process_fin_de_vie)


# test etape 9 — fin de vie
print("debut test 9 fin de vie")
print()
print("procede :", processes_par_id[Process_fin_de_vie]["displayName"])
print("impact  :", ecs_du_process(Process_fin_de_vie), "pts/kg")
print("fin etape 9 ")

# somme des impcts
def calcul_acv(vetement, masses, c_durabilite):
    return (
        impact_matieres(masses)
        + impact_filature(masses, vetement["categorie"], vetement["pays"])
        + impact_tissage(masses, vetement["categorie"], vetement["pays"])
        + impact_ennoblissement(masses, vetement["composition"], vetement["pays"])
        + impact_confection(vetement["categorie"], vetement["pays"])
        + impact_accessoires(vetement["categorie"])
        + impact_distribution(vetement["masse"])
        + impact_utilisation(masses, vetement["categorie"], c_durabilite)
        + impact_fin_de_vie(masses)
    )
"""
# test — somme ACV
print("debut test calcul_acv")
print()

liste_vet = [
    {"id": 1, "designation": "T-shirt basique blanc", "categorie": "tshirt",
     "composition": [("Coton", 1.0)], "masse": 0.150, "prix": 7.99, "pays": "BD"},
    {"id": 4, "designation": "T-shirt melange 60/40", "categorie": "tshirt",
     "composition": [("Coton", 0.6), ("Polyester", 0.4)],
     "masse": 0.155, "prix": 9.90, "pays": "CN"},
    {"id": 19, "designation": "Jean brut selvedge", "categorie": "jean",
     "composition": [("Coton", 1.0)], "masse": 0.680, "prix": 119.00, "pays": "TR"},
    {"id": 31, "designation": "Manteau laine", "categorie": "manteau",
     "composition": [("Laine par défaut", 0.8), ("Polyester", 0.2)],
     "masse": 1.450, "prix": 349.00, "pays": "REO"},
    {"id": 40, "designation": "Chaussettes coton", "categorie": "chaussettes",
     "composition": [("Coton", 0.75), ("Polyester", 0.22), ("Elasthane", 0.03)],
     "masse": 0.060, "prix": 3.99, "pays": "CN"},
]

for v in liste_vet:
    masses = calcul_masses(v["categorie"], v["composition"], v["masse"])
    c = coef_durabilite(v["categorie"], v["prix"])

    e1 = impact_matieres(masses)
    e2 = impact_filature(masses, v["categorie"], v["pays"])
    e3 = impact_tissage(masses, v["categorie"], v["pays"])
    e4 = impact_ennoblissement(masses, v["composition"], v["pays"])
    e5 = impact_confection(v["categorie"], v["pays"])
    e6 = impact_accessoires(v["categorie"])
    e7 = impact_distribution(v["masse"])
    e8 = impact_utilisation(masses, v["categorie"], c)
    e9 = impact_fin_de_vie(masses)

    total = calcul_acv(v, masses, c)

    print("ID", str(v["id"]).rjust(2), "-", v["designation"],
          " | ", v["pays"], " | ", v["masse"] * 1000, "g | C =", round(c, 3))
    print("    matieres      ", str(round(e1, 2)).rjust(9), "pts", str(round(e1 / total * 100, 1)).rjust(5) + "%")
    print("    filature      ", str(round(e2, 2)).rjust(9), "pts", str(round(e2 / total * 100, 1)).rjust(5) + "%")
    print("    tissage       ", str(round(e3, 2)).rjust(9), "pts", str(round(e3 / total * 100, 1)).rjust(5) + "%")
    print("    ennoblissement", str(round(e4, 2)).rjust(9), "pts", str(round(e4 / total * 100, 1)).rjust(5) + "%")
    print("    confection    ", str(round(e5, 2)).rjust(9), "pts", str(round(e5 / total * 100, 1)).rjust(5) + "%")
    print("    accessoires   ", str(round(e6, 2)).rjust(9), "pts", str(round(e6 / total * 100, 1)).rjust(5) + "%")
    print("    distribution  ", str(round(e7, 2)).rjust(9), "pts", str(round(e7 / total * 100, 1)).rjust(5) + "%")
    print("    utilisation   ", str(round(e8, 2)).rjust(9), "pts", str(round(e8 / total * 100, 1)).rjust(5) + "%")
    print("    fin de vie    ", str(round(e9, 2)).rjust(9), "pts", str(round(e9 / total * 100, 1)).rjust(5) + "%")
    print("    TOTAL ACV     ", str(round(total, 2)).rjust(9), "pts")
    print()

print("fin test calcul_acv")
"""

#cpmts hors acv 
coef_dechet = 5000 #pts/KG

# Tableau 2 p.11 : probabilite de finir en dechet hors Europe
p_dechet_synthetique = 0.121
p_dechet_autre = 0.049


def complement_export(masse:float, composition:list):#masse du vet 
   
    k = 0
    for nom, taux in composition:
        if materiaux_par_nom[nom]["origin"] == "Synthetic":
            k = k + taux
    if k > 0.5:
        proba = p_dechet_synthetique
    else:
        proba = p_dechet_autre

    return proba * masse * coef_dechet



coef_microfibres = 1000 #pts/KG

Ref_microfibres = {
    "Synthetic":             0.82,
    "NaturalFromVegetal":    0.25,
    "NaturalFromAnimal":     0.39,
    "ArtificialFromOrganic": 0.33,
}


def complement_microfibres(masse:float, composition:list):#masse du vet 
    somme = 0
    for nom, taux in composition:
        ORIGIN = materiaux_par_nom[nom]["origin"]
        somme= somme + Ref_microfibres[ORIGIN] * taux * masse * coef_microfibres
    return somme


def calcul_hors_acv(vetement:dict):
    return (complement_export(vetement["masse"], vetement["composition"])
            + complement_microfibres(vetement["masse"], vetement["composition"]))


# calcul de leco score 
def calcul_ecoscore(vetement:dict):#esc= (acv+hors acv )/ c dura 
    masses = calcul_masses(
        vetement["categorie"], vetement["composition"], vetement["masse"]
    )
    c = coef_durabilite(vetement["categorie"], vetement["prix"])

    acv = calcul_acv(vetement, masses, c)
    hors_acv = calcul_hors_acv(vetement)

    return (acv + hors_acv) / c



import pandas as pd

# Pays hors perimetre textile d'Ecobalyse, remplaces par leur region
# (notice p.42 : « il faut choisir la region du pays »)
pays_subs = {
    "PT": "REO",   # Portugal  -> Europe de l'Ouest
    "IT": "REO",   # Italie    -> Europe de l'Ouest
    "ID": "RAS",   # Indonesie -> Asie
}

# lit la base excel et renvoie liste de dico, convertit g en kg et % en fract de 1
def charger_base(chemin="base_50_vetements_vf.xlsx"):
    #datafrm
    df = pd.read_excel(chemin, sheet_name="Base 50 vetements", header=1)

    liste_vetements = []
    for i in range(len(df)):#parcours chaque ligne du df 
        ligne = df.iloc[i] #donne ligne position i 
        # "Coton / Polyester" et "60 / 40" donne [("Coton", 0.6), ("Polyester", 0.4)]
        noms = str(ligne["Matieres"]).split("/") #casting
        pourcentages = str(ligne["Pourcentages (%)"]).split("/")

        composition = []
        for k in range(len(noms)):
            nom = noms[k].strip()# en elevant les espaces dvt et arr
            taux = float(pourcentages[k]) / 100 #comprios 0 et 1 
            composition.append((nom, taux))#tuple 

        # certains pays sont hors du perimetre textile
        pays = ligne["Code pays"]
        if pays in pays_subs:
            pays = pays_subs[pays]

        produit= {
            "id": int(ligne["ID"]),
            "designation": ligne["Designation"],
            "categorie": ligne["Categorie Ecobalyse"],
            "composition": composition,
            "pays": pays,
            "masse": ligne["Poids estime (g)"] / 1000,
            "prix": ligne["Prix (EUR)"],
        }
        liste_vetements.append(produit)

    return liste_vetements


print("debut calcul eco score 50 vetements")
print()

liste_vetements = charger_base()

resultats = []
for v in liste_vetements:
    score = calcul_ecoscore(v)
    resultats.append((v["id"], v["designation"], score))
    print("ID", v["id"], "-", v["designation"], ":", round(score, 1), "pts")

print()
print(len(resultats), "scores calcules")
print()


