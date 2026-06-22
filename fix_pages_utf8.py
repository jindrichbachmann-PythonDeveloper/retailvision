from pathlib import Path

path = Path(r"app\web\pages.py")
backup = Path(r"app\web\pages_before_utf_fix.py")

raw = path.read_bytes()
backup.write_bytes(raw)

text = raw.decode("utf-8", errors="replace")

def repair_mojibake_once(s: str) -> str:
    try:
        return s.encode("cp1252", errors="ignore").decode("utf-8", errors="ignore")
    except Exception:
        return s

def score(s: str) -> int:
    bad = ["Ã", "â", "Ĺ", "Å", "Ä", " "]
    return sum(s.count(x) for x in bad)

current = text
for _ in range(3):
    fixed = repair_mojibake_once(current)
    if not fixed or score(fixed) >= score(current):
        break
    current = fixed

replacements = {
    "PĹ™ipravenoâ€¦": "Připraveno…",
    "PĹ™ihlásit se": "Přihlásit se",
    "PĹ™ihlášení": "Přihlášení",
    "ZaloĹžit účet": "Založit účet",
    "Zapomenuté heslo": "Zapomenuté heslo",
    "Poznámka": "Poznámka",
    "Analýza hodinek": "Analýza hodinek",
    "Kamera vypnutá": "Kamera vypnutá",
    "globální proměnné": "globální proměnné",
    "černého boxu": "černého boxu",
    "Aktuální složka": "Aktuální složka",
    "Fakturační složka nastavena na": "Fakturační složka nastavena na",
    "Posílám fakturační CSV účetní za": "Posílám fakturační CSV účetní za",
    "CSV odesláno účetní": "CSV odesláno účetní",
    "Chyba při ukládání složky": "Chyba při ukládání složky",
    "Chyba při posílání CSV účetní": "Chyba při posílání CSV účetní",
    "Zadej cestu ke složce.": "Zadej cestu ke složce.",
    "Zadej platný rok a měsíc (1–12).": "Zadej platný rok a měsíc (1–12).",
    "Načíst objednávky": "Načíst objednávky",
    "Archivovat staré objednávky": "Archivovat staré objednávky",
    "Objednávka": "Objednávka",
    "Zákazník": "Zákazník",
    "Položky objednávky": "Položky objednávky",
    "Celkem": "Celkem",
    "Stav": "Stav",
    "Označit jako odesláno": "Označit jako odesláno",
    "Opravdu chcete vyprázdnit košík?": "Opravdu chcete vyprázdnit košík?",
    "Košík vyprázdněn.": "Košík vyprázdněn.",
    "Vyber aspoň jeden obrázek.": "Vyber aspoň jeden obrázek.",
    "Odesílám obrázky na server…": "Odesílám obrázky na server…",
    "Fotka pořízena, posílám na analýzu…": "Fotka pořízena, posílám na analýzu…",
}

for old, new in replacements.items():
    current = current.replace(old, new)

path.write_text(current, encoding="utf-8", newline="\n")
print("Hotovo.")
print("Záloha:", backup)
print("Zkontroluj výskyty rozbitých znaků:")
for token in ["Ã", "â", "Ĺ", "Å", "Ä", " "]:
    c = current.count(token)
    if c:
        print(f"{token}: {c}x")