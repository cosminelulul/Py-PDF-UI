# Py-PDF-UI

![Windows](https://img.shields.io/badge/Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white)
![Linux](https://img.shields.io/badge/Linux-Debian%20%7C%20Ubuntu-E95420?style=for-the-badge&logo=linux&logoColor=white)
![Status](https://img.shields.io/badge/Status-Finished-brightgreen?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)

Aplicație desktop destinată prelucrării cu PDF-uri și imagini: exportă pagini ca PNG, creează PDF din imagini, îmbină, împarte, elimină pagini și comprimă fișiere PDF.

Tot ce faci rămâne **local**: fișierele tale nu sunt încărcate nicăieri, iar aplicația nu folosește internetul.

## Cuprins

- [Ce poate face](#ce-poate-face)
- [Descărcare și pornire](#descărcare-și-pornire)
- [Instrumentele în detaliu](#instrumentele-în-detaliu)
- [Lista de fișiere](#lista-de-fișiere)
- [Opțiuni](#opțiuni)
- [Performanță și siguranța fișierelor](#performanță-și-siguranța-fișierelor)
- [Rulare din sursă](#Rulare-din-sursă)
- [Limitări](#limitări)
- [Structura proiectului](#structura-proiectului)
- [Licență](#Licență)



## Ce poate face

| Instrument | Ce face |
|---|---|
| **PDF → PNG** | Exportă fiecare pagină a unuia sau mai multor PDF-uri ca imagine PNG, la 72–300 DPI. |
| **IMG → PDF** | Creează un singur PDF din imagini (PNG, JPG, BMP, WebP, TIFF, GIF), cu control al compresiei. |
| **Îmbinare PDF** | Unește mai multe PDF-uri într-unul singur, în ordinea din listă. |
| **Împărțire PDF** | Taie un PDF pe pagini, la fiecare N pagini sau pe intervale. |
| **Elimină pagini** | Șterge paginile nedorite dintr-un PDF. |
| **Comprimare** | Micșorează PDF-urile (imagini și structură), pe trei niveluri. |

În plus:

- **Drag & drop** de fișiere și foldere din Explorer.
- **Listă editabilă**: bifezi ce procesezi, reordonezi prin tragere, scoți rânduri.
- **Buton Oprește** și confirmare la închiderea ferestrei cât timp lucrează ceva.
- **Folosește mai multe nuclee** pentru operațiile grele și nu are nevoie de instalare.
- Interfață în **română, engleză, spaniolă și franceză**; temă **întunecată sau luminoasă** cu tranziție lină; **culoare de accent** la alegere, cu disc de culoare și introducere HEX/RGB.

## Descărcare și pornire

1. Deschide pagina **[Releases](../../releases/latest)** a acestui depozit.
2. Descarcă `PDF-Toolkit.exe`.
3. Rulează-l.

Cerințe: Windows 10/11, pe 64 de biți.

Setările tale (limbă, temă, culoare de accent etc.) se păstrează în `%APPDATA%\PDF Toolkit\settings.json`. Pentru a dezinstala, șterge executabilul și acel folder.

## Instrumentele în detaliu

### PDF → PNG

- **Rezoluție**: 72–300 DPI (implicit 156 DPI, adică o pagină A4 de ≈ 1290 × 1824 px). Sub slider se vede dimensiunea rezultată.
- Un PDF cu o singură pagină produce `nume.png`, lângă PDF. Un PDF cu mai multe pagini produce un folder `nume/` cu `nume_001.png`, `nume_002.png` etc.
- Paginile se randează în paralel, pe mai multe nuclee.
- Dacă o pagină ar ieși prea mare pentru memoria disponibilă (de exemplu un plan A0 la 300 DPI pe un calculator cu puțină memorie), aplicația te anunță înainte să înceapă și îți cere o rezoluție mai mică.

### IMG → PDF

- Acceptă `.png`, `.jpg`, `.jpeg`, `.bmp`, `.webp`, `.tiff`, `.tif`, `.gif`. **Ordinea din listă este ordinea paginilor.**
- **Nume fișier**: implicit `output`, salvat ca `output.pdf` lângă prima imagine din listă.
- **Rată implicită de comprimare PDF** (0–100%, pași de 5%, implicit **70%**):

  | Rată | Efect |
  |---|---|
  | **0%** | Fără pierderi. JPEG-urile intră în PDF exact cum sunt (octet cu octet), iar celelalte formate se păstrează fără pierderi. Excepție: JPEG-urile cu orientare EXIF oglindită trebuie recodificate (la calitate 95). |
  | 1–100% | Imaginile se recodifică JPEG cu calitate de la 95 la 30 (calitate ≈ 95 − 0,65 × rată). **30%** ≈ calitate 76, **70%** = calitate 50, **100%** = calitate 30. |

  Un JPEG deja mic nu este niciodată făcut mai mare. Valoarea aleasă se salvează și devine implicită data viitoare.
- Orientarea EXIF a pozelor este respectată, transparența se așază pe fundal alb, JPEG-urile CMYK sunt convertite în RGB, iar imaginile gri pe 16 biți sunt scalate corect. La GIF-urile animate se folosește primul cadru.
- Pagina PDF are dimensiunea imaginii la **100 DPI** (o poză de 4000 px lățime dă o pagină de ≈ 40 inch). Peste limita de 200 inch din specificația PDF, rezoluția scade automat.
- PDF-ul se scrie imagine cu imagine, deci memoria folosită rămâne mică și la sute de imagini.

### Îmbinare PDF

- Unește PDF-urile bifate, în ordinea din listă. Același fișier poate apărea de mai multe ori.
- **Nume fișier**: implicit `merged`, salvat ca `merged.pdf` lângă primul PDF.

### Împărțire PDF

Trei moduri:

| Mod | Rezultat |
|---|---|
| **Fiecare pagină** | Un PDF pentru fiecare pagină. |
| **La N pagini** | PDF-uri de câte N pagini (ultimul poate fi mai scurt). |
| **Intervale** | Câte un PDF pentru fiecare interval, de exemplu `1-3, 5, 8-` (`8-` înseamnă „până la final"). |

Rezultatele ajung într-un folder nou `nume_split/`. Numele conțin pagina sau intervalul, completat cu zerouri (`Manual_07.pdf`, `Manual_01-03.pdf`).

### Elimină pagini

- Scrie paginile de eliminat: `2, 5-7, 10-` (`10-` înseamnă până la final, `-3` înseamnă de la început până la pagina 3).
- Rezultatul este `nume_edited.pdf`, lângă original. Originalul rămâne neatins.
- Nu poți elimina toate paginile unui PDF.

### Comprimare

| Nivel | Calitate imagini | Latura maximă a imaginilor |
|---|---|---|
| **Ușor** | JPEG 85 | 2600 px |
| **Echilibrat** | JPEG 70 | 1700 px |
| **Puternic** | JPEG 50 | 1200 px |

- Imaginile sunt recodificate și redimensionate, iar structura PDF-ului este optimizată fără pierderi (fluxuri de conținut, obiecte duplicate sau neutilizate). O imagine folosită pe mai multe pagini se prelucrează o singură dată.
- Imaginile cu transparență sau cu paletă de culori nu sunt atinse.
- Rezultatul este `nume_compressed.pdf`, dar **se păstrează doar dacă e cu cel puțin 1% mai mic**. Altfel nu se creează niciun fișier și vezi mesajul „deja optimizat".
- La mai multe fișiere, acestea se comprimă în paralel.

## Lista de fișiere

- **Bifa** de la fiecare rând alege ce se procesează; **Selectează tot** / **Deselectează** acționează pe toată lista.
- La **IMG → PDF** și **Îmbinare**, rândurile au mâner de tragere și butoane sus/jos. Tragi un rând ca să-l muți (cu **Ctrl** apăsat, rândul se **copiază** la poziția aleasă), iar numărul de pagină sau de document se actualizează.
- Fiecare rând arată mărimea fișierului, iar la PDF-uri (mai puțin la Comprimare) și numărul de pagini.
- **X** scoate un rând din listă (nu șterge fișierul de pe disc).
- **Drag & drop**: dacă tragi un folder, devine folderul de lucru; dacă tragi fișiere de tipul potrivit, se adaugă în listă. Chenarul zonei devine roșu pentru fișiere neacceptate. Dacă ții fișierele deasupra unui instrument din bara laterală, aplicația trece singură la el după o jumătate de secundă.

## Opțiuni

Butonul **Opțiuni** din bara laterală deschide panoul de setări.

| Setare | Ce face |
|---|---|
| **Mărime text** | 11–20, se aplică imediat. |
| **Mod întunecat** | Comută între tema întunecată și cea luminoasă, cu o tranziție lină. |
| **Culoare de accent** | Schimbă culoarea de accent (implicit albastru). Vezi mai jos. |
| **Limbă** | Română, English, Español, Français. |


### Culoarea de accent

Apasă butonul cu culoarea curentă pentru a deschide selectorul.

- Alegi culoarea de pe **disc** (nuanță și saturație), iar luminozitatea cu sliderul.
- Sau o **scrii de la tastatură**, în oricare dintre forme:
  - HEX: `#12B886`, `12b886` sau varianta scurtă `#1b8`;
  - RGB: în cele trei câmpuri **R**, **G**, **B** (0–255), ori `18, 184, 134` / `rgb(18, 184, 134)` lipite în câmpul HEX.
- Săgețile sus/jos din câmpurile R/G/B schimbă valoarea cu 1 (cu **Shift**, cu 10).
- Valorile invalide se marchează cu roșu și blochează butonul **Aplică**. **Enter** aplică, **Escape** anulează, **Resetează** revine la albastrul implicit.
- Dacă alegi o culoare prea deschisă sau prea închisă, aplicația o ajustează puțin ca să rămână vizibilă pe fundal, iar textul de pe butoane rămâne citibil.


## Performanță și siguranța fișierelor

- **Mai multe nuclee**: PDF → PNG, Comprimare și IMG → PDF (la mai multe imagini) rulează în procese separate, lăsând un nucleu liber pentru interfață. Numărul de procese ține cont și de memoria liberă. Pe parcursul unei operații vezi în Managerul de activități mai multe procese `PDF-Toolkit.exe`, ceea ce este normal.
- **Interfață fluidă**: la redimensionarea ferestrei, lista nu se mai redesenează la fiecare pas, ci o singură dată la final.
- **Scriere atomică**: rezultatele se scriu întâi într-un fișier temporar (`.part`) și sunt mutate la numele final doar când sunt complete. O oprire sau o eroare nu lasă fișiere pe jumătate scrise.
- **Oprește**: oprește imediat operația. Rezultatele deja terminate rămân (de exemplu paginile PNG gata), iar cele neterminate sunt șterse.
- **Mesaje clare** pentru PDF-uri deteriorate sau protejate cu parolă, imagini corupte, lipsă de memorie sau de spațiu pe disc, nume de fișier invalide.
- Variabila de mediu `PDFTOOLKIT_WORKERS` controlează procesele de lucru: `1` dezactivează procesele suplimentare, iar un număr `N` forțează `N` procese.

## Limitări

- **PDF-urile protejate cu parolă** nu sunt acceptate (aplicația spune clar asta). PDF-urile protejate doar prin restricții (parolă de proprietar, fără parolă de deschidere) se deschid, iar rezultatul nu păstrează acele restricții.
- **Comprimarea** modifică imaginile (nivelurile Echilibrat și Puternic produc pierderi vizibile pe imaginile detaliate). Nu schimbă fonturile și nici conținutul vectorial, în afară de comprimarea fluxurilor.
- Nu există OCR și nu se poate edita textul din PDF.
- Pe un calculator cu puțină memorie, paginile foarte mari (planuri, afișe) la rezoluții mari sunt refuzate cu un mesaj, nu încercate pe riscul blocării aplicației.
- Drag & drop necesită biblioteca `tkinterdnd2` (inclusă în executabil). Fără ea, aplicația funcționează, dar fără tragere de fișiere.

## Rulare din sursă

### Cerințe & biblioteci folosite

| Componentă                                               |
| -------------------------------------------------------- |
| Python                                                   |
| [customtkinter](https://pypi.org/project/customtkinter/) |
| [Pillow](https://pypi.org/project/pillow/)               |
| [pypdfium2](https://pypi.org/project/pypdfium2/)         |
| [pypdf](https://pypi.org/project/pypdf/)                 |
| [tkinterdnd2](https://pypi.org/project/tkinterdnd2/)     |

Python trebuie să includă `tkinter`. Installer-ul de pe python.org pentru Windows îl include implicit; pe Debian/Ubuntu instalează-l cu `sudo apt install python3-tk`.

### Pași

```bash
git clone https://github.com/cosminelulul/Py-PDF-UI.git
cd </Py-PDF-UI>
python -m venv .venv
```

Activează mediul virtual:

```bash
.venv\Scripts\activate          # Windows (cmd)
.venv\Scripts\Activate.ps1      # Windows (PowerShell)
source .venv/bin/activate       # Linux / macOS
```

Apoi instalează dependențele și pornește aplicația:

```bash
pip install -r requirements.txt
python app.py
```

Aplicația este dezvoltată pentru Windows și Linux . 

## Structura proiectului

```
PyAPDF-Ui
│   app.py
├───icons
└───scripts
    ├───etc
    │       colorpicker.py -- Dialogul cu roata de culoare pentru accent
    │       colors.py --  Matematica culorilor: HEX/RGB, contrast, paleta de accent
    │       paths.py -- Căi care funcționează și din sursă, și din executabil
    │       settings.py --  Citirea și scrierea setărilor
    │       uiperf.py  -- Utilitare de performanță pentru interfață (redimensionare, throttle)
    │
    └───pdfcore
            errors.py -- Excepții și mesaje de eroare
            files.py -- Nume de fișiere, scriere atomică, sortare naturală
            images.py --  Pregătirea imaginilor pentru PDF
            pages.py --  Interpretarea intervalelor de pagini
            pdfium_util.py -- Acces la PDFium (nu e thread-safe, deci protejat cu lock)
            pdfwriter.py -- Scriitor PDF în flux, cu memorie constantă
            runner.py -- Procese de lucru, progres, anulare
            sysinfo.py -- Nuclee și memorie liberă, alegerea numărului de procese
            tasks.py --  Operațiile: PDF → PNG, IMG → PDF, Îmbinare, Împărțire, Eliminare, Comprimare

```

## Licență
Vezi [Licență](LICENSE)
