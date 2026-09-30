"""Lapisan SENSE.

Simulasi dan hardware nyata bisa ditukar lewat env SENSOR=sim|hw
tanpa mengubah logika Think (sesuai mitigasi risiko di slide rencana).
"""
import os
import random
import time


class SimulatedSensor:
    """Mensimulasikan HC-SR04 di langit-langit slot, menghadap ke bawah.

    Lantai kosong ~ 33-40 cm, atap mobil ~ 5-9 cm.
    Ada noise dan outlier ekstrem (5%) supaya debounce terlihat bekerja.
    Fase kosong/terisi bergantian tiap SIM_PERIOD detik (deterministik = enak untuk demo).
    Offset per slot (SIM_OFFSET) membuat A1, A2, A3 tidak berubah serempak.
    """

    def __init__(self):
        self.period = float(os.getenv("SIM_PERIOD", "12"))
        self.offset = float(os.getenv("SIM_OFFSET", "0"))
        self.t0 = time.time()

    def read_cm(self):
        phase = int((time.time() - self.t0 + self.offset) // self.period)
        occupied = phase % 2 == 1
        base = random.uniform(5, 9) if occupied else random.uniform(33, 40)
        if random.random() < 0.05:
            base = random.choice([2.0, 400.0, 0.0])  # outlier
        return round(base, 1)


class HCSR04Sensor:
    """Hanya dipakai bila suatu saat ada sensor asli di Raspberry Pi."""

    def __init__(self):
        from gpiozero import DistanceSensor  # import lazy: tidak perlu di container sim
        self.s = DistanceSensor(
            echo=int(os.getenv("ECHO_PIN", "24")),
            trigger=int(os.getenv("TRIG_PIN", "23")),
            max_distance=2,
        )

    def read_cm(self):
        return round(self.s.distance * 100, 1)


def get_sensor():
    return HCSR04Sensor() if os.getenv("SENSOR", "sim") == "hw" else SimulatedSensor()
