#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
emob_cluster_timeseries.py (überarbeitet)
===========================
Erzeugt CSV-Zeitreihen für die TOP-Energy®-Komponente
»Elektromobilität« aus mehreren Cluster-JSON-Dateien.
Die zeitliche Auflösung wird über eine zentrale Konfigurationsdatei
("config.json") gewählt (Standard: stündlich).

Funktionsweise angepasst: initial volle Kapazität und Subtraktion von
Abwesenheitsfenstern; Energiebedarf im letzten verfügbaren Zeitschritt
vor Abfahrt. Zeitreihe nur für das angegebene Jahr mit Nullwerten
in den ersten und letzten beiden Tagen.
"""
from __future__ import annotations
import json
import logging
from datetime import date, datetime, time, timedelta as td
from pathlib import Path
from typing import Dict, Any, List
import random

import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------
WD = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]  # Monday = 0 … Sunday = 6

# Standardpfad zur zentralen Konfigurationsdatei
DEFAULT_CONFIG = "config.json"

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def hhmm(txt: str) -> time:
    try:
        return datetime.strptime(txt, "%H:%M").time()
    except ValueError as e:
        raise ValueError(
            f"Ungültiges Zeitformat '{txt}'. Erwartet: HH:MM") from e


def days_of_year(year: int):
    d = date(year, 1, 1)
    while d.year == year:
        yield d
        d += td(days=1)

# ---------------------------------------------------------------------------
# Validierung
# ---------------------------------------------------------------------------


def validate_cluster_config(cfg: Dict[str, Any], cluster_name: str) -> None:
    """Prüft die Cluster-spezifische Konfiguration ohne Jahr."""
    keys = ["cluster_name", "fahrzeuge"]
    for k in keys:
        if k not in cfg:
            raise ValueError(
                f"Cluster '{cluster_name}': Fehlender Schlüssel '{k}'")
    if not isinstance(cfg["cluster_name"], str) or not cfg["cluster_name"].strip():
        raise ValueError(
            f"Cluster '{cluster_name}': 'cluster_name' muss nicht-leerer String sein")
    if not isinstance(cfg["fahrzeuge"], list) or not cfg["fahrzeuge"]:
        raise ValueError(
            f"Cluster '{cluster_name}': 'fahrzeuge' muss Liste sein")
    for i, v in enumerate(cfg["fahrzeuge"]):
        validate_vehicle(v, i, cluster_name)


def validate_vehicle(vehicle: Dict[str, Any], index: int, cluster_name: str) -> None:
    req = ["name", "anzahl", "akku_kapazitaet_kwh",
           "verbrauch_kwh_pro_km", "wochenplan"]
    for k in req:
        if k not in vehicle:
            raise ValueError(
                f"Cluster '{cluster_name}', Fahrzeug {index}: Fehlender Schlüssel '{k}'")
    if not isinstance(vehicle["anzahl"], int) or vehicle["anzahl"] <= 0:
        raise ValueError(
            f"Cluster '{cluster_name}', Fahrzeug {index}: 'anzahl' muss positiv sein")
    if not isinstance(vehicle["akku_kapazitaet_kwh"], (int, float)) or vehicle["akku_kapazitaet_kwh"] <= 0:
        raise ValueError(
            f"Cluster '{cluster_name}', Fahrzeug {index}: 'akku_kapazitaet_kwh' muss positiv sein")
    if not isinstance(vehicle["verbrauch_kwh_pro_km"], (int, float)) or vehicle["verbrauch_kwh_pro_km"] <= 0:
        raise ValueError(
            f"Cluster '{cluster_name}', Fahrzeug {index}: 'verbrauch_kwh_pro_km' muss positiv sein")

    # Validierung der Zeitverzerrung (optional)
    if "zeitverzerrung" in vehicle:
        tz = vehicle["zeitverzerrung"]
        if not isinstance(tz, dict):
            raise ValueError(
                f"Cluster '{cluster_name}', Fahrzeug {index}: 'zeitverzerrung' muss dict sein")
        if "typ" in tz and tz["typ"] not in ["normal", "uniform"]:
            raise ValueError(
                f"Cluster '{cluster_name}', Fahrzeug {index}: 'zeitverzerrung.typ' muss 'normal' oder 'uniform' sein")
        if "stddev_minuten" in tz and (not isinstance(tz["stddev_minuten"], (int, float)) or tz["stddev_minuten"] < 0):
            raise ValueError(
                f"Cluster '{cluster_name}', Fahrzeug {index}: 'zeitverzerrung.stddev_minuten' muss >= 0 sein")
        if "max_abweichung_minuten" in tz and (not isinstance(tz["max_abweichung_minuten"], (int, float)) or tz["max_abweichung_minuten"] < 0):
            raise ValueError(
                f"Cluster '{cluster_name}', Fahrzeug {index}: 'zeitverzerrung.max_abweichung_minuten' muss >= 0 sein")

    validate_weekly_plan(vehicle["wochenplan"],
                         f"Cluster '{cluster_name}', Fahrzeug {index}")


def validate_weekly_plan(plan: Dict[str, Any], ctx: str) -> None:
    if not isinstance(plan, dict):
        raise ValueError(f"{ctx}: Wochenplan muss dict sein")
    for day, entry in plan.items():
        if day not in WD:
            raise ValueError(f"{ctx}: Ungültiger Wochentag '{day}'")
        validate_day_entry(entry, f"{ctx}, {day}")


def validate_day_entry(entry: Dict[str, Any], ctx: str) -> None:
    if not isinstance(entry, dict):
        raise ValueError(f"{ctx}: Eintrag muss dict sein")
    modes = ["steht", "tour", "mehrtagstour", "nicht_verfügbar"]
    found = [m for m in modes if m in entry]
    if len(found) != 1:
        raise ValueError(
            f"{ctx}: Genau einer der Modi {modes} muss gesetzt sein")
    m = found[0]
    if m in ("steht", "nicht_verfügbar"):
        if entry[m] is not True:
            raise ValueError(f"{ctx}: '{m}' muss true sein")
    elif m == "tour":
        validate_tour_entry(entry[m], ctx)
    else:
        validate_multiday_entry(entry[m], ctx)


def validate_tour_entry(tour: Dict[str, Any], ctx: str) -> None:
    for k in ("km", "abfahrt", "rueckkehr"):
        if k not in tour:
            raise ValueError(f"{ctx}: Tour fehlt '{k}'")
    if not isinstance(tour["km"], (int, float)) or tour["km"] < 0:
        raise ValueError(f"{ctx}: 'km' muss >=0 sein")
    hhmm(tour["abfahrt"])
    hhmm(tour["rueckkehr"])


def validate_multiday_entry(entry: Dict[str, Any], ctx: str) -> None:
    for k in ("km", "abfahrt", "rueckkehr_uhr"):
        if k not in entry:
            raise ValueError(f"{ctx}: Mehrtagestour fehlt '{k}'")
    if not isinstance(entry["km"], (int, float)) or entry["km"] < 0:
        raise ValueError(f"{ctx}: 'km' muss >=0 sein")
    hhmm(entry["abfahrt"])
    hhmm(entry["rueckkehr_uhr"])
    if "tage_später" in entry:
        if not isinstance(entry["tage_später"], int) or entry["tage_später"] < 0:
            raise ValueError(f"{ctx}: 'tage_später' muss >=0 sein")

# ---------------------------------------------------------------------------
# Zeitverzerrung
# ---------------------------------------------------------------------------


def generate_time_deviations(n_vehicles: int, config: Dict[str, Any] = None) -> List[int]:
    """
    Generiert Zeitabweichungen in Minuten für n Fahrzeuge.

    Args:
        n_vehicles: Anzahl Fahrzeuge
        config: Konfiguration der Zeitverzerrung
            - typ: "normal" (Normalverteilung) oder "uniform" (Gleichverteilung)
            - stddev_minuten: Standardabweichung in Minuten (für normal)
            - max_abweichung_minuten: Maximale Abweichung in Minuten (für uniform)
            - seed: Random seed für Reproduzierbarkeit

    Returns:
        Liste von Zeitabweichungen in Minuten
    """
    if config is None:
        config = {}

    typ = config.get("typ", "normal")
    seed = config.get("seed")

    if seed is not None:
        np.random.seed(seed)
        random.seed(seed)

    if typ == "uniform":
        max_dev = config.get("max_abweichung_minuten", 15)
        deviations = np.random.uniform(-max_dev, max_dev, n_vehicles)
    else:  # normal
        stddev = config.get("stddev_minuten", 10)
        max_dev = config.get("max_abweichung_minuten", 30)
        deviations = np.random.normal(0, stddev, n_vehicles)
        # Begrenze auf max_abweichung
        deviations = np.clip(deviations, -max_dev, max_dev)

    return [int(round(dev)) for dev in deviations]


def apply_time_deviation(base_time: time, deviation_minutes: int) -> time:
    """
    Wendet eine Zeitabweichung auf eine Basiszeit an.

    Args:
        base_time: Ursprüngliche Zeit
        deviation_minutes: Abweichung in Minuten (kann negativ sein)

    Returns:
        Neue Zeit mit angewandter Abweichung
    """
    # Konvertiere zu datetime für einfache Arithmetik
    base_dt = datetime.combine(date.today(), base_time)
    new_dt = base_dt + td(minutes=deviation_minutes)
    return new_dt.time()

# ---------------------------------------------------------------------------
# Hauptlogik
# ---------------------------------------------------------------------------


def build_cluster_timeseries(
    cfg: Dict[str, Any], cluster_name: str, year: int, freq: str = "1h"
) -> pd.DataFrame:
    logger.info(f"Erstelle Zeitreihe Cluster {cluster_name} Jahr {year}")

    freq_delta = pd.Timedelta(freq)

    # Zeitreihe nur für das angegebene Jahr erstellen
    idx = pd.date_range(
        f"{year}-01-01 00:00",
        f"{year + 1}-01-01 00:00",
        freq=freq,
        inclusive="left",
    )
    df = pd.DataFrame(
        0.0,
        index=idx,
        columns=["available_capacity_kWh", "energy_demand_kWh", "rest_energy_kWh"],
    )

    # Berechne die ersten und letzten beiden Tage des Jahres
    first_jan = date(year, 1, 1)
    second_jan = date(year, 1, 2)
    dec_30 = date(year, 12, 30)
    dec_31 = date(year, 12, 31)

    exclusion_days = {first_jan, second_jan, dec_30, dec_31}

    for group in cfg["fahrzeuge"]:
        n = group["anzahl"]
        cap = group["akku_kapazitaet_kwh"]
        cons = group["verbrauch_kwh_pro_km"]
        plan = group["wochenplan"]
        zeitverzerrung_config = group.get("zeitverzerrung", {})

        # Nur Kapazität für Tage hinzufügen, die nicht in den Ausschlussbereichen liegen
        for day in days_of_year(year):
            if day not in exclusion_days:
                start_ts = pd.Timestamp.combine(day, time.min)
                end_ts = start_ts + td(days=1) - freq_delta
                df.loc[start_ts:end_ts, "available_capacity_kWh"] += cap * n

        # Verarbeite nur Tage außerhalb der Ausschlussbereiche
        for day in days_of_year(year):
            if day in exclusion_days:
                continue

            e = plan.get(WD[day.weekday()], {"steht": True})
            if e.get("steht"):
                continue

            if e.get("nicht_verfügbar"):
                start_ts = pd.Timestamp.combine(day, time.min)
                end_ts = start_ts + td(days=1) - freq_delta
                df.loc[start_ts:end_ts, "available_capacity_kWh"] -= cap * n
            elif "tour" in e:
                _handle_tour_sub_with_deviation(
                    df,
                    day,
                    e["tour"],
                    n,
                    cap,
                    cons,
                    year,
                    zeitverzerrung_config,
                    freq,
                )
            else:
                _handle_multiday_sub_with_deviation(
                    df,
                    day,
                    e.get("mehrtagstour", {}),
                    n,
                    cap,
                    cons,
                    year,
                    zeitverzerrung_config,
                    freq,
                )

        df["available_capacity_kWh"] = df["available_capacity_kWh"].clip(
            lower=0)

    # NEUE LOGIK: Energiebedarf in der letzten Zeile und Restenergie in der ersten Zeile jedes Kapazitätsblocks setzen
    _set_energy_demand_at_block_end(df)
    _set_rest_energy_at_block_start(df)

    out = df.reset_index(names="timestamp").assign(
        Datum=lambda d: d["timestamp"].dt.date.astype(str),
        Zeit=lambda d: d["timestamp"].dt.strftime("%H:%M")
    )
    return out[["Datum", "Zeit", "available_capacity_kWh", "energy_demand_kWh", "rest_energy_kWh"]]


def _set_energy_demand_at_block_end(df: pd.DataFrame) -> None:
    """
    Verschiebt den Energiebedarf an das Ende der jeweiligen Kapazitätsblöcke.

    Diese Funktion identifiziert zusammenhängende Blöcke mit verfügbarer Kapazität > 0
    und verschiebt den gesamten Energiebedarf an die letzte Zeile jedes Blocks.
    """
    # Erstelle eine Kopie des ursprünglichen Energiebedarfs
    original_demand = df["energy_demand_kWh"].copy()

    # Setze den Energiebedarf zurück
    df["energy_demand_kWh"] = 0.0

    # Identifiziere Blöcke mit verfügbarer Kapazität > 0
    has_capacity = df["available_capacity_kWh"] > 0

    # Finde die Übergänge zwischen Blöcken
    capacity_diff = has_capacity.astype(int).diff()

    # Block-Starts: Übergang von 0 zu 1 (False zu True)
    block_starts = df.index[capacity_diff == 1]

    # Block-Ends: Übergang von 1 zu 0 (True zu False) - aber wir brauchen den letzten Index VOR dem Übergang
    block_end_indices = capacity_diff == -1
    if block_end_indices.any():
        # Verschiebe die Indices um 1 zurück, um die letzte Zeile MIT Kapazität zu bekommen
        block_ends = df.index[block_end_indices.shift(-1, fill_value=False)]
    else:
        block_ends = pd.Index([])

    # Behandle den Fall, wenn das erste Element bereits Kapazität hat
    if len(df) > 0 and has_capacity.iloc[0]:
        block_starts = pd.Index([df.index[0]]).union(block_starts)

    # Behandle den Fall, wenn das letzte Element noch Kapazität hat
    if len(df) > 0 and has_capacity.iloc[-1]:
        block_ends = block_ends.union(pd.Index([df.index[-1]]))

    # Für jeden Block: summiere den Energiebedarf und setze ihn an das Ende
    for i in range(len(block_starts)):
        if i < len(block_ends):
            start = block_starts[i]
            end = block_ends[i]

            # Summiere den Energiebedarf in diesem Block
            block_mask = (df.index >= start) & (df.index <= end) & has_capacity
            total_demand = original_demand[block_mask].sum()

            # Setze den gesamten Bedarf an die letzte Position des Blocks MIT Kapazität
            if total_demand > 0:
                df.at[end, "energy_demand_kWh"] = total_demand


def _set_rest_energy_at_block_start(df: pd.DataFrame) -> None:
    """
    Verschiebt die Restenergie an den Anfang der jeweiligen Kapazitätsblöcke.

    Diese Funktion identifiziert zusammenhängende Blöcke mit verfügbarer Kapazität > 0
    und verschiebt die gesamte Restenergie an die erste Zeile jedes Blocks.
    """
    # Erstelle eine Kopie der ursprünglichen Restenergie
    original_rest = df["rest_energy_kWh"].copy()

    # Setze die Restenergie zurück
    df["rest_energy_kWh"] = 0.0

    # Identifiziere Blöcke mit verfügbarer Kapazität > 0
    has_capacity = df["available_capacity_kWh"] > 0

    # Finde die Übergänge zwischen Blöcken
    capacity_diff = has_capacity.astype(int).diff()

    # Block-Starts: Übergang von 0 zu 1 (False zu True)
    block_starts = df.index[capacity_diff == 1]

    # Block-Ends: Übergang von 1 zu 0 (True zu False) - aber wir brauchen den letzten Index VOR dem Übergang
    block_end_indices = capacity_diff == -1
    if block_end_indices.any():
        # Verschiebe die Indices um 1 zurück, um die letzte Zeile MIT Kapazität zu bekommen
        block_ends = df.index[block_end_indices.shift(-1, fill_value=False)]
    else:
        block_ends = pd.Index([])

    # Behandle den Fall, wenn das erste Element bereits Kapazität hat
    if len(df) > 0 and has_capacity.iloc[0]:
        block_starts = pd.Index([df.index[0]]).union(block_starts)

    # Behandle den Fall, wenn das letzte Element noch Kapazität hat
    if len(df) > 0 and has_capacity.iloc[-1]:
        block_ends = block_ends.union(pd.Index([df.index[-1]]))

    # Für jeden Block: summiere die Restenergie und setze sie an den Anfang
    for i in range(len(block_starts)):
        if i < len(block_ends):
            start = block_starts[i]
            end = block_ends[i]

            # Summiere die Restenergie in diesem Block
            block_mask = (df.index >= start) & (df.index <= end) & has_capacity
            total_rest = original_rest[block_mask].sum()

            # Setze die gesamte Restenergie an die erste Position des Blocks MIT Kapazität
            if total_rest > 0:
                df.at[start, "rest_energy_kWh"] = total_rest
# ---------------------------------------------------------------------------
# Abwesenheits-Handler mit korrektem Energiebedarf und Zeitverzerrung
# ---------------------------------------------------------------------------


def _handle_tour_sub_with_deviation(
    df: pd.DataFrame,
    day: date,
    t: Dict[str, Any],
    n: int,
    cap: float,
    cons: float,
    year: int,
    zeitverzerrung_config: Dict[str, Any],
    freq: str,
) -> None:
    """Behandelt Tagestouren mit Zeitverzerrung für einzelne Fahrzeuge."""
    km = float(t["km"])
    base_leave = hhmm(t["abfahrt"])
    base_ret = hhmm(t["rueckkehr"])

    # Generiere Zeitabweichungen für alle Fahrzeuge
    leave_deviations = generate_time_deviations(n, zeitverzerrung_config)
    return_deviations = generate_time_deviations(n, zeitverzerrung_config)

    freq_delta = pd.Timedelta(freq)
    year_start = pd.Timestamp(f"{year}-01-01")
    year_end = pd.Timestamp(f"{year + 1}-01-01") - freq_delta

    # Verarbeite jedes Fahrzeug einzeln
    for i in range(n):
        actual_leave = apply_time_deviation(base_leave, leave_deviations[i])
        actual_ret = apply_time_deviation(base_ret, return_deviations[i])

        lt = pd.Timestamp.combine(day, actual_leave)
        bd = day if actual_ret > actual_leave else day + td(days=1)
        rt = pd.Timestamp.combine(bd, actual_ret)

        # Stelle sicher, dass alle Timestamps im Jahr liegen
        if lt < year_start or rt > year_end:
            continue

        try:
            # Reduziere verfügbare Kapazität während Abwesenheit
            end_time = rt - freq_delta
            if end_time >= lt:
                mask = (df.index >= lt) & (df.index <= end_time)
                df.loc[mask, "available_capacity_kWh"] -= cap

            # GEÄNDERT: Energiebedarf wird später am Block-Ende gesetzt
            # Sammle den Energiebedarf zunächst dort wo er ursprünglich gesetzt würde
            ts_req = lt.floor(freq) - freq_delta
            if ts_req >= year_start and ts_req in df.index:
                df.at[ts_req, "energy_demand_kWh"] += km * cons

            # Restenergie bei Rückkehr
            rt_floor = rt.floor(freq)
            if rt_floor <= year_end and rt_floor in df.index:
                df.at[rt_floor, "rest_energy_kWh"] += max(cap - km * cons, 0.0)

        except Exception as e:
            logger.warning(f"Fehler bei Tour-Verarbeitung für Tag {day}: {e}")
            continue


def _handle_multiday_sub_with_deviation(
    df: pd.DataFrame,
    day: date,
    t: Dict[str, Any],
    n: int,
    cap: float,
    cons: float,
    year: int,
    zeitverzerrung_config: Dict[str, Any],
    freq: str,
) -> None:
    """Behandelt Mehrtagestouren mit Zeitverzerrung für einzelne Fahrzeuge."""
    km = float(t.get("km", 0))
    base_leave = hhmm(t.get("abfahrt", "00:00"))
    base_ret = hhmm(t.get("rueckkehr_uhr", "00:00"))
    offset = int(t.get("tage_später", 0))

    # Generiere Zeitabweichungen für alle Fahrzeuge
    leave_deviations = generate_time_deviations(n, zeitverzerrung_config)
    return_deviations = generate_time_deviations(n, zeitverzerrung_config)

    freq_delta = pd.Timedelta(freq)
    year_start = pd.Timestamp(f"{year}-01-01")
    year_end = pd.Timestamp(f"{year + 1}-01-01") - freq_delta

    # Verarbeite jedes Fahrzeug einzeln
    for i in range(n):
        actual_leave = apply_time_deviation(base_leave, leave_deviations[i])
        actual_ret = apply_time_deviation(base_ret, return_deviations[i])

        lt = pd.Timestamp.combine(day, actual_leave)
        bd = day + td(days=offset) if offset else (day if actual_ret >
                                                   actual_leave else day + td(days=1))
        rt = pd.Timestamp.combine(bd, actual_ret)

        # Stelle sicher, dass alle Timestamps im Jahr liegen
        if lt < year_start or rt > year_end:
            continue

        try:
            # Reduziere verfügbare Kapazität während Abwesenheit
            end_time = rt - freq_delta
            if end_time >= lt:
                mask = (df.index >= lt) & (df.index <= end_time)
                df.loc[mask, "available_capacity_kWh"] -= cap

            # GEÄNDERT: Energiebedarf wird später am Block-Ende gesetzt
            # Sammle den Energiebedarf zunächst dort wo er ursprünglich gesetzt würde
            ts_req = lt.floor(freq) - freq_delta
            if ts_req >= year_start and ts_req in df.index:
                df.at[ts_req, "energy_demand_kWh"] += km * cons

            # Restenergie bei Rückkehr
            rt_floor = rt.floor(freq)
            if rt_floor <= year_end and rt_floor in df.index:
                df.at[rt_floor, "rest_energy_kWh"] += max(cap - km * cons, 0.0)

        except Exception as e:
            logger.warning(
                f"Fehler bei Mehrtagestour-Verarbeitung für Tag {day}: {e}")
            continue


# Behalte die alten Funktionen für Rückwärtskompatibilität
def _handle_tour_sub(
    df: pd.DataFrame,
    day: date,
    t: Dict[str, Any],
    n: int,
    cap: float,
    cons: float,
    year: int,
    freq: str,
) -> None:
    """Fallback-Funktion ohne Zeitverzerrung."""
    _handle_tour_sub_with_deviation(df, day, t, n, cap, cons, year, {}, freq)


def _handle_multiday_sub(
    df: pd.DataFrame,
    day: date,
    t: Dict[str, Any],
    n: int,
    cap: float,
    cons: float,
    year: int,
    freq: str,
) -> None:
    """Fallback-Funktion ohne Zeitverzerrung."""
    _handle_multiday_sub_with_deviation(df, day, t, n, cap, cons, year, {}, freq)

# ---------------------------------------------------------------------------
# Hauptprogramm
# ---------------------------------------------------------------------------

def main() -> int:
    config_path = Path(DEFAULT_CONFIG)
    if not config_path.is_file():
        logger.error(f"Konfigurationsdatei {config_path} nicht gefunden")
        return 1

    try:
        main_cfg = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Fehler beim Lesen der Konfigurationsdatei: {e}")
        return 1

    year = main_cfg.get("jahr")
    if not isinstance(year, int) or not (2000 <= year <= 3000):
        logger.error("Ung\u00fcltiges oder fehlendes 'jahr' in der Konfiguration")
        return 1

    freq = str(main_cfg.get("freq", "1h"))

    try:
        d = Path(__file__).parent
        files = sorted(d.glob("cluster_*.json"))
        if not files:
            logger.warning("Keine cluster_*.json Dateien gefunden")
            return 0

        for f in files:
            logger.info(f"Verarbeite Datei: {f.name}")
            cfg = json.loads(f.read_text(encoding="utf-8"))
            validate_cluster_config(cfg, f.stem)
            dfc = build_cluster_timeseries(cfg, cfg["cluster_name"], year, freq)
            output_file = d / f"{year}_{cfg['cluster_name']}_emob_timeseries.csv"
            dfc.to_csv(output_file, sep=";", decimal=",", index=False)
            logger.info(f"Zeitreihe erfolgreich erstellt: {output_file.name}")

    except Exception as e:
        logger.error(f"Fehler: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return 1
    return 0


if __name__ == "__main__":
    exit(main())
