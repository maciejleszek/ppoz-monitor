"""Słownik branżowy ochrony przeciwpożarowej.

Ogłoszenie trafia do bazy, jeśli jego tytuł/opis/zamawiający zawiera któreś
z haseł poniżej ALBO jego kod CPV zaczyna się od jednego z prefiksów CPV.

Dopasowanie jest niewrażliwe na wielkość liter i polskie znaki
("Przeciwpożarowy" == "przeciwpozarowy"). Aby dodać własne hasło, dopisz
parę (fragment_bez_polskich_znaków, "Etykieta") do odpowiedniej listy.
"""

import re

_PL = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")


def normalize(text: str) -> str:
    """Małe litery + zamiana polskich znaków na ASCII."""
    return (text or "").translate(_PL).lower()


# ── Hasła dopasowywane jako fragment tekstu ─────────────────────────────────
# (fragment po normalizacji, etykieta pokazywana w interfejsie)
SUBSTRING_KEYWORDS: list[tuple[str, str]] = [
    ("przeciwpozar", "PPOŻ"),
    ("ppoz", "PPOŻ"),
    ("p.poz", "PPOŻ"),
    ("pozarow", "instalacje pożarowe"),        # pożarowa/-e/-ych, pożarów
    ("pozaru", "instalacje pożarowe"),         # np. "sygnalizacji pożaru"
    ("pozarn", "pożarnictwo"),                 # straż pożarna, sprzęt pożarniczy
    ("hydrant", "hydranty"),
    ("tryskacz", "tryskacze"),
    ("zraszacz", "zraszacze"),
    ("oddymi", "oddymianie"),
    ("klapy dymowe", "klapy dymowe"),
    ("klap dymowych", "klapy dymowe"),
    ("klapa dymowa", "klapy dymowe"),
    ("kurtyny dymowe", "kurtyny dymowe"),
    ("kurtyn dymowych", "kurtyny dymowe"),
    ("gasnic", "gaśnice / instal. gaśnicze"),  # gaśnice, gaśnicze, gaśniczych
    ("gaszeni", "systemy gaszenia"),
    ("dzwiekowy system ostrzegawczy", "DSO"),
    ("ognioodporn", "bierna ochrona ppoż"),
    ("ogniochronn", "bierna ochrona ppoż"),
    ("przegrody ogniowe", "bierna ochrona ppoż"),
    ("przegrod ogniowych", "bierna ochrona ppoż"),
    ("drzwi przeciwpozarowe", "drzwi ppoż"),
    ("czujki dymu", "detekcja dymu"),
    ("czujek dymu", "detekcja dymu"),
    ("czujka dymu", "detekcja dymu"),
    ("detektor dymu", "detekcja dymu"),
    ("detektory dymu", "detekcja dymu"),
    ("detekcji dymu", "detekcja dymu"),
    ("wykrywania dymu", "detekcja dymu"),
    ("pianotworcz", "środki pianotwórcze"),
    ("oswietlenie awaryjne", "oświetlenie awaryjne"),
    ("oswietlenia awaryjnego", "oświetlenie awaryjne"),
    ("ewakuacyjn", "ewakuacja"),               # szerokie — usuń, jeśli za dużo trafień
]

# ── Skróty dopasowywane jako całe słowo (granice wyrazu) ────────────────────
WORD_KEYWORDS: list[tuple[str, str]] = [
    ("ssp", "SSP"),   # system sygnalizacji pożarowej
    ("dso", "DSO"),   # dźwiękowy system ostrzegawczy
    ("sug", "SUG"),   # stałe urządzenia gaśnicze
    ("osp", "OSP"),   # ochotnicza straż pożarna (częsty zamawiający)
]

# ── Prefiksy kodów CPV (Wspólny Słownik Zamówień) ───────────────────────────
CPV_PREFIXES: list[tuple[str, str]] = [
    ("35111", "CPV: sprzęt gaśniczy"),
    ("35110", "CPV: sprzęt gaśniczy i ratunkowy"),
    ("316251", "CPV: systemy wykrywania pożaru"),
    ("316252", "CPV: systemy alarmu pożarowego"),
    ("45312100", "CPV: instalowanie alarmów ppoż"),
    ("45343", "CPV: roboty ppoż"),
    ("4448", "CPV: urządzenia gaśnicze"),
    ("50413200", "CPV: serwis sprzętu gaśniczego"),
    ("75251", "CPV: usługi pożarnicze"),
    ("71317100", "CPV: doradztwo ppoż"),
    ("45216121", "CPV: obiekty straży pożarnej"),
    ("24951220", "CPV: środki gaśnicze"),
]

_CPV_RE = re.compile(r"\d{8}-\d")
_WORD_RES = [(re.compile(rf"\b{re.escape(w)}\b"), label) for w, label in WORD_KEYWORDS]


def extract_cpv(raw) -> list[str]:
    """Wyciąga wszystkie kody CPV (########-#) z pola tekstowego."""
    if not raw:
        return []
    if isinstance(raw, (list, tuple)):
        raw = " ".join(str(x) for x in raw)
    return list(dict.fromkeys(_CPV_RE.findall(str(raw))))


def match_keywords(text: str, cpv_codes: list[str] | None = None) -> list[str]:
    """Zwraca listę etykiet dopasowanych do tekstu/kodów CPV (pusta = pomiń)."""
    norm = normalize(text)
    labels: list[str] = []

    for fragment, label in SUBSTRING_KEYWORDS:
        if fragment in norm and label not in labels:
            labels.append(label)

    for pattern, label in _WORD_RES:
        if label not in labels and pattern.search(norm):
            labels.append(label)

    for code in cpv_codes or []:
        digits = code.split("-")[0]
        for prefix, label in CPV_PREFIXES:
            if digits.startswith(prefix) and label not in labels:
                labels.append(label)

    return labels
