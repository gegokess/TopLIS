# E-Mobility Cluster Timeseries Generator

Ein Python-Tool zur Generierung stündlicher CSV-Zeitreihen für die TOP-Energy®-Komponente "Elektromobilität" aus Cluster-JSON-Konfigurationsdateien.

## 🚀 Features

- **Flexible Konfiguration**: JSON-basierte Cluster-Definitionen mit Fahrzeugflotten
- **Zeitverzerrung**: Realistische Simulation durch Normal- oder Gleichverteilung der Abfahrts-/Rückkehrzeiten
- **Mehrere Fahrzeugtypen**: Verschiedene Akkukapazitäten und Verbrauchswerte pro Cluster
- **Tages- und Mehrtagestouren**: Flexible Tourenplanung mit Wochenplänen
- **Validierung**: Umfassende Eingabevalidierung für robuste Verarbeitung
- **Stündliche Auflösung**: CSV-Export mit Datum, Zeit, verfügbarer Kapazität, Energiebedarf und Restenergie

## 📋 Anforderungen

- Python 3.8+
- pandas
- numpy

## 🛠 Installation

1. Repository klonen:
```bash
git clone https://github.com/yourusername/emob-cluster-timeseries.git
cd emob-cluster-timeseries
```

2. Abhängigkeiten installieren:
```bash
pip install -r requirements.txt
```

## 🎯 Verwendung

### 1. Cluster-Konfiguration erstellen

Erstellen Sie eine JSON-Datei mit dem Prefix `cluster_` (z.B. `cluster_beispiel.json`):

```json
{
  "jahr": 2024,
  "cluster_name": "LIS_Cluster_1",
  "fahrzeuge": [
    {
      "name": "eActros_600",
      "anzahl": 16,
      "akku_kapazitaet_kwh": 600,
      "verbrauch_kwh_pro_km": 1.0,
      "zeitverzerrung": {
        "typ": "normal",
        "stddev_minuten": 30,
        "max_abweichung_minuten": 90,
        "seed": 100
      },
      "wochenplan": {
        "Mo": { "tour": { "km": 300, "abfahrt": "05:00", "rueckkehr": "16:00" } },
        "Di": { "tour": { "km": 300, "abfahrt": "05:00", "rueckkehr": "16:00" } },
        "Mi": { "tour": { "km": 300, "abfahrt": "05:00", "rueckkehr": "16:00" } },
        "Do": { "tour": { "km": 300, "abfahrt": "05:00", "rueckkehr": "16:00" } },
        "Fr": { "tour": { "km": 300, "abfahrt": "05:00", "rueckkehr": "16:00" } },
        "Sa": { "steht": true },
        "So": { "steht": true }
      }
    }
  ]
}
```

### 2. Zeitreihen generieren

```bash
python emob_cluster_timeseries.py
```

Das Script verarbeitet automatisch alle `cluster_*.json` Dateien im aktuellen Verzeichnis und erstellt entsprechende CSV-Dateien.

### 3. Ausgabe

Für jede Cluster-Datei wird eine CSV-Datei erstellt:
- Format: `{Jahr}_{Cluster_Name}_emob_timeseries.csv`
- Beispiel: `2024_LIS_Cluster_1_emob_timeseries.csv`

## 📊 Ausgabeformat

Die CSV-Dateien enthalten folgende Spalten:

| Spalte | Beschreibung |
|--------|--------------|
| `Datum` | Datum (YYYY-MM-DD) |
| `Zeit` | Uhrzeit (HH:MM) |
| `available_capacity_kWh` | Verfügbare Akkukapazität in kWh |
| `energy_demand_kWh` | Energiebedarf in kWh (am Ende jedes Kapazitätsblocks) |
| `rest_energy_kWh` | Restenergie in kWh (am Anfang jedes Kapazitätsblocks) |

## ⚙️ Konfigurationsoptionen

### Fahrzeug-Modi

- **`steht`**: Fahrzeug steht (volle Kapazität verfügbar)
- **`tour`**: Tagestour mit Abfahrt und Rückkehr
- **`mehrtagstour`**: Mehrtägige Tour
- **`nicht_verfügbar`**: Fahrzeug nicht verfügbar (z.B. Wartung)

### Zeitverzerrung

```json
"zeitverzerrung": {
  "typ": "normal",              // "normal" oder "uniform"
  "stddev_minuten": 30,         // Standardabweichung (nur bei "normal")
  "max_abweichung_minuten": 90, // Maximale Abweichung
  "seed": 100                   // Seed für Reproduzierbarkeit
}
```

## 🧪 Beispiele

Das Repository enthält Beispiel-Konfigurationen im `examples/` Verzeichnis:

- `cluster_beispiel_eactros.json`: eActros-Flotte mit Normalverteilung
- `cluster_beispiel_klein.json`: Kleinere Flotte mit Gleichverteilung
- `cluster_beispiel_mixed.json`: Gemischte Flotte verschiedener Fahrzeugtypen

## 🤝 Beitragen

1. Fork des Repositories
2. Feature-Branch erstellen (`git checkout -b feature/AmazingFeature`)
3. Änderungen committen (`git commit -m 'Add some AmazingFeature'`)
4. Branch pushen (`git push origin feature/AmazingFeature`)
5. Pull Request öffnen

## 📝 Lizenz

Dieses Projekt steht unter der MIT-Lizenz - siehe [LICENSE](LICENSE) Datei für Details.

## 🐛 Support

Bei Problemen oder Fragen:
- Issue auf GitHub erstellen
- Dokumentation prüfen
- Beispiele im `examples/` Verzeichnis konsultieren

## 📚 Technische Details

### Algorithmus

1. **Initialisierung**: Volle Akkukapazität für alle Fahrzeuge
2. **Abwesenheitsfenster**: Subtraktion der Kapazität während Touren
3. **Zeitverzerrung**: Individuelle Abweichungen pro Fahrzeug
4. **Energieverteilung**: 
   - Energiebedarf am Ende der Kapazitätsblöcke
   - Restenergie am Anfang der Kapazitätsblöcke
5. **Randbehandlung**: Nullwerte in den ersten und letzten zwei Tagen des Jahres

### Performance

- Speichereffizient durch pandas DataFrame-Operationen
- Skaliert linear mit der Anzahl Fahrzeuge
- Typische Verarbeitungszeit: < 1 Sekunde pro Cluster mit 100 Fahrzeugen