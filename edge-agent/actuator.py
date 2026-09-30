"""Lapisan ACT. LED disimulasikan sebagai teks berwarna di terminal."""
import os

RED, GREEN, RST = "\033[91m", "\033[92m", "\033[0m"


class SimulatedLED:
    def __init__(self, slot_id):
        self.slot_id = slot_id

    def set(self, status):
        if status == "OCCUPIED":
            print(f"{RED}[{self.slot_id}] ACT   -> LED MERAH  | slot OCCUPIED{RST}", flush=True)
        else:
            print(f"{GREEN}[{self.slot_id}] ACT   -> LED HIJAU  | slot FREE{RST}", flush=True)


class GPIOLED:
    def __init__(self, slot_id):
        from gpiozero import LED
        self.red = LED(int(os.getenv("RED_PIN", "17")))
        self.green = LED(int(os.getenv("GREEN_PIN", "27")))

    def set(self, status):
        if status == "OCCUPIED":
            self.green.off()
            self.red.on()
        else:
            self.red.off()
            self.green.on()


def get_led(slot_id):
    return GPIOLED(slot_id) if os.getenv("SENSOR", "sim") == "hw" else SimulatedLED(slot_id)
